"""Polymarket API proxy client with retry logic, rate limiting, and circuit breaker.

Provides a unified client for proxying requests to Polymarket's CLOB, Gamma, and Data APIs
with built-in resilience patterns including:
- Exponential backoff retry on transient failures
- Rate limiting to stay under Polymarket limits
- Circuit breaker to prevent cascading failures
- Response caching with configurable TTL (Redis or in-memory)
- Stale-while-error: returns cached data on transient failures

Rate limits (from CLAUDE.md):
- CLOB API: 9,000 req/10s overall
- Data API: 1,000 req/10s overall, /trades: 200/10s
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx
import structlog

from prediction_data.api.polymarket_proxy.exceptions import (
    CircuitOpenError,
    ProxyError,
    UpstreamRateLimitError,
)
from prediction_data.core.config import get_settings
from prediction_data.core.logging import get_logger


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """Circuit breaker for API failure protection.

    When too many failures occur, the circuit "opens" and prevents
    further requests for a cooldown period. After cooldown, it enters
    "half-open" state to test if the service has recovered.
    """

    failure_threshold: int = 5  # Failures before opening
    recovery_timeout: float = 30.0  # Seconds before trying again
    half_open_max_calls: int = 3  # Test calls in half-open state

    state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    failure_count: int = field(default=0, init=False)
    last_failure_time: float = field(default=0.0, init=False)
    half_open_calls: int = field(default=0, init=False)

    def record_success(self) -> None:
        """Record a successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                # Recovery confirmed, close circuit
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_calls = 0
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = time.monotonic()

        if self.state == CircuitState.HALF_OPEN:
            # Recovery failed, reopen circuit
            self.state = CircuitState.OPEN
            self.half_open_calls = 0
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def can_execute(self) -> bool:
        """Check if a request can be executed."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if cooldown has passed
            elapsed = time.monotonic() - self.last_failure_time
            if elapsed >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False

        # HALF_OPEN state
        return True


@dataclass
class CacheEntry:
    """Cached response with TTL tracking."""

    data: dict[str, Any]
    expires_at: float
    created_at: float = field(default_factory=time.monotonic)

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return time.monotonic() >= self.expires_at

    def is_stale(self, stale_threshold: float = 60.0) -> bool:
        """Check if cache entry is stale (past TTL but within stale threshold)."""
        now = time.monotonic()
        return self.expires_at <= now < (self.expires_at + stale_threshold)


class CacheBackend(ABC):
    """Abstract base class for cache backends."""

    @abstractmethod
    async def get(self, key: str) -> tuple[dict[str, Any] | None, float | None]:
        """Get cached value.

        Args:
            key: Cache key.

        Returns:
            Tuple of (data or None, expires_at or None).
        """
        pass

    @abstractmethod
    async def set(self, key: str, data: dict[str, Any], ttl: int) -> None:
        """Set cached value.

        Args:
            key: Cache key.
            data: Data to cache.
            ttl: TTL in seconds.
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a cache entry.

        Args:
            key: Cache key.

        Returns:
            True if the entry was deleted.
        """
        pass

    @abstractmethod
    async def delete_pattern(self, pattern: str) -> int:
        """Delete cache entries matching a pattern.

        Args:
            pattern: Key prefix pattern to match.

        Returns:
            Number of entries deleted.
        """
        pass

    @abstractmethod
    async def clear(self) -> int:
        """Clear all cache entries.

        Returns:
            Number of entries cleared.
        """
        pass

    @abstractmethod
    def size(self) -> int:
        """Get current cache size."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the cache backend connection."""
        pass


class InMemoryCacheBackend(CacheBackend):
    """In-memory cache backend using a dictionary."""

    def __init__(self, max_size: int = 10000) -> None:
        self._cache: dict[str, tuple[dict[str, Any], float]] = {}
        self._max_size = max_size

    async def get(self, key: str) -> tuple[dict[str, Any] | None, float | None]:
        entry = self._cache.get(key)
        if entry is None:
            return None, None
        return entry[0], entry[1]

    async def set(self, key: str, data: dict[str, Any], ttl: int) -> None:
        # Evict if over max size
        if len(self._cache) >= self._max_size:
            self._evict_expired()
            if len(self._cache) >= self._max_size:
                self._evict_oldest(len(self._cache) - self._max_size + 100)

        expires_at = time.monotonic() + ttl
        self._cache[key] = (data, expires_at)

    async def delete(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    async def delete_pattern(self, pattern: str) -> int:
        keys_to_remove = [k for k in self._cache if k.startswith(pattern)]
        for key in keys_to_remove:
            del self._cache[key]
        return len(keys_to_remove)

    async def clear(self) -> int:
        count = len(self._cache)
        self._cache.clear()
        return count

    def size(self) -> int:
        return len(self._cache)

    async def close(self) -> None:
        self._cache.clear()

    def _evict_expired(self) -> None:
        now = time.monotonic()
        keys_to_remove = [k for k, (_, exp) in self._cache.items() if exp <= now]
        for key in keys_to_remove:
            del self._cache[key]

    def _evict_oldest(self, count: int) -> None:
        if count <= 0:
            return
        sorted_keys = sorted(self._cache.keys(), key=lambda k: self._cache[k][1])
        for key in sorted_keys[:count]:
            del self._cache[key]


class RedisCacheBackend(CacheBackend):
    """Redis cache backend for distributed caching.

    Requires redis-py[hiredis] package to be installed.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._redis: Any = None  # redis.asyncio.Redis
        self._logger = get_logger(__name__)

    async def _get_client(self) -> Any:
        """Get or create Redis client."""
        if self._redis is None:
            try:
                import redis.asyncio as redis_async  # type: ignore[import-not-found]

                self._redis = redis_async.from_url(
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=False,  # We'll handle encoding ourselves
                )
            except ImportError:
                self._logger.error(
                    "redis package not installed. Install with: pip install redis[hiredis]"
                )
                raise
        return self._redis

    async def get(self, key: str) -> tuple[dict[str, Any] | None, float | None]:
        try:
            client = await self._get_client()
            # Get data and TTL in a pipeline
            pipe = client.pipeline()
            pipe.get(key)
            pipe.ttl(key)
            results = await pipe.execute()

            data_bytes, ttl = results
            if data_bytes is None:
                return None, None

            data = json.loads(data_bytes)
            # Convert TTL to absolute expiration time
            expires_at = time.monotonic() + ttl if ttl > 0 else None
            return data, expires_at

        except Exception as e:
            self._logger.warning(
                "Redis cache get failed, returning miss",
                key=key,
                error=str(e),
            )
            return None, None

    async def set(self, key: str, data: dict[str, Any], ttl: int) -> None:
        try:
            client = await self._get_client()
            data_bytes = json.dumps(data).encode("utf-8")
            await client.setex(key, ttl, data_bytes)
        except Exception as e:
            self._logger.warning(
                "Redis cache set failed",
                key=key,
                error=str(e),
            )

    async def delete(self, key: str) -> bool:
        try:
            client = await self._get_client()
            result = await client.delete(key)
            return bool(result > 0)
        except Exception as e:
            self._logger.warning(
                "Redis cache delete failed",
                key=key,
                error=str(e),
            )
            return False

    async def delete_pattern(self, pattern: str) -> int:
        try:
            client = await self._get_client()
            # Use SCAN to find keys matching the pattern
            count = 0
            cursor = 0
            while True:
                cursor, keys = await client.scan(
                    cursor=cursor,
                    match=f"{pattern}*",
                    count=100,
                )
                if keys:
                    await client.delete(*keys)
                    count += len(keys)
                if cursor == 0:
                    break
            return count
        except Exception as e:
            self._logger.warning(
                "Redis cache delete_pattern failed",
                pattern=pattern,
                error=str(e),
            )
            return 0

    async def clear(self) -> int:
        # Clear only polymarket keys, not the entire Redis
        return await self.delete_pattern("polymarket:")

    def size(self) -> int:
        # Size is not tracked for Redis (would require expensive SCAN)
        return -1

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.close()
            self._redis = None


class ProxyCache:
    """Cache for proxied responses with Redis or in-memory backend.

    Supports cache-aside pattern with TTL and stale-while-revalidate.
    Cache keys follow format: polymarket:{endpoint}:{params_hash}

    Uses Redis if REDIS_URL is configured, otherwise falls back to in-memory.
    """

    # Stale threshold: how long past TTL we'll still return stale data
    STALE_THRESHOLD = 60.0  # seconds

    def __init__(
        self,
        default_ttl: int = 30,
        max_size: int = 10000,
        redis_url: str | None = None,
    ) -> None:
        """Initialize the cache.

        Args:
            default_ttl: Default TTL in seconds.
            max_size: Maximum entries for in-memory cache (ignored for Redis).
            redis_url: Redis connection URL. If None, uses in-memory cache.
        """
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0
        self._logger = get_logger(__name__)

        # Choose backend based on redis_url
        if redis_url:
            self._backend: CacheBackend = RedisCacheBackend(redis_url)
            self._backend_type = "redis"
            self._logger.info("Using Redis cache backend", redis_url=redis_url[:30] + "...")
        else:
            self._backend = InMemoryCacheBackend(max_size=max_size)
            self._backend_type = "memory"
            self._logger.info("Using in-memory cache backend")

    def _make_key(self, endpoint: str, params: dict[str, Any] | None = None) -> str:
        """Generate cache key from endpoint and params.

        Format: polymarket:{endpoint}:{params_hash}
        """
        # Normalize endpoint (remove leading slash)
        normalized_endpoint = endpoint.lstrip("/")

        if params:
            # Sort params for consistent hashing
            sorted_params = sorted(params.items())
            params_str = str(sorted_params)
            params_hash = hashlib.md5(params_str.encode()).hexdigest()[:12]
            return f"polymarket:{normalized_endpoint}:{params_hash}"
        return f"polymarket:{normalized_endpoint}"

    async def get(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        """Get cached value if available.

        Args:
            endpoint: API endpoint path.
            params: Query parameters.

        Returns:
            Tuple of (data or None, cache_status). cache_status is one of:
            "HIT", "MISS", "STALE".
        """
        key = self._make_key(endpoint, params)
        data, expires_at = await self._backend.get(key)

        if data is None:
            self._misses += 1
            self._logger.debug(
                "Cache miss",
                key=key,
                cache_status="MISS",
            )
            return None, "MISS"

        now = time.monotonic()

        # Check if expired
        if expires_at is not None and expires_at <= now:
            # Check if within stale threshold
            if expires_at + self.STALE_THRESHOLD > now:
                self._hits += 1
                self._logger.debug(
                    "Cache stale hit",
                    key=key,
                    cache_status="STALE",
                )
                return data, "STALE"
            # Too old, treat as miss (but don't delete, backend will handle expiry)
            self._misses += 1
            self._logger.debug(
                "Cache expired miss",
                key=key,
                cache_status="MISS",
            )
            return None, "MISS"

        self._hits += 1
        self._logger.debug(
            "Cache hit",
            key=key,
            cache_status="HIT",
        )
        return data, "HIT"

    async def set(
        self,
        endpoint: str,
        params: dict[str, Any] | None,
        data: dict[str, Any],
        ttl: int | None = None,
    ) -> None:
        """Cache a response.

        Args:
            endpoint: API endpoint path.
            params: Query parameters.
            data: Response data to cache.
            ttl: TTL in seconds (uses default if not specified).
        """
        key = self._make_key(endpoint, params)
        ttl = ttl or self._default_ttl
        await self._backend.set(key, data, ttl)
        self._logger.debug(
            "Cache set",
            key=key,
            ttl=ttl,
        )

    async def invalidate(self, pattern: str | None = None) -> int:
        """Invalidate cache entries matching pattern.

        Args:
            pattern: Key prefix to match (None = clear all polymarket keys).

        Returns:
            Number of entries removed.
        """
        if pattern is None:
            count = await self._backend.clear()
        else:
            # Ensure pattern starts with polymarket: prefix
            if not pattern.startswith("polymarket:"):
                pattern = f"polymarket:{pattern}"
            count = await self._backend.delete_pattern(pattern)

        self._logger.info(
            "Cache invalidated",
            pattern=pattern,
            count=count,
        )
        return count

    async def close(self) -> None:
        """Close the cache backend connection."""
        await self._backend.close()

    @property
    def stats(self) -> dict[str, int | float | str]:
        """Return cache statistics."""
        return {
            "size": self._backend.size(),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": (
                round(self._hits / (self._hits + self._misses) * 100, 1)
                if (self._hits + self._misses) > 0
                else 0.0
            ),
            "backend": self._backend_type,
        }


class PolymarketProxyClient:
    """Unified async client for Polymarket API proxying.

    Provides methods to proxy requests to CLOB, Gamma, and Data APIs with:
    - Exponential backoff retry on transient failures
    - Rate limiting per API
    - Circuit breaker per API
    - Response caching

    Example:
        async with PolymarketProxyClient() as client:
            data = await client.get_clob("/book", {"token_id": "123"})
    """

    # Rate limits in requests per second (conservative values)
    CLOB_RATE_LIMIT = 30  # 9000/10s = 900/s, we use 30 for safety
    DATA_RATE_LIMIT = 10  # 1000/10s = 100/s, we use 10 for safety

    # Retry settings
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 0.5  # seconds
    RETRY_MAX_DELAY = 10.0  # seconds

    def __init__(
        self,
        *,
        cache_ttl: int | None = None,
        timeout: float | None = None,
        redis_url: str | None = None,
    ) -> None:
        """Initialize the proxy client.

        Args:
            cache_ttl: Default cache TTL in seconds.
            timeout: Request timeout in seconds.
            redis_url: Redis URL for distributed caching. If None, uses settings or in-memory.
        """
        settings = get_settings()
        self._clob_url = settings.polymarket_clob_url
        self._gamma_url = settings.polymarket_gamma_url
        self._data_url = settings.polymarket_data_url
        self._cache_ttl = cache_ttl or settings.polymarket_proxy_cache_ttl
        self._timeout = timeout or settings.polymarket_proxy_timeout

        self._http_client: httpx.AsyncClient | None = None
        self._logger: structlog.stdlib.BoundLogger = get_logger(__name__)

        # Rate limiting: track last request time per API
        self._last_clob_request: float = 0.0
        self._last_data_request: float = 0.0
        self._clob_interval = 1.0 / self.CLOB_RATE_LIMIT
        self._data_interval = 1.0 / self.DATA_RATE_LIMIT

        # Circuit breakers per API
        self._clob_circuit = CircuitBreaker()
        self._data_circuit = CircuitBreaker()
        self._gamma_circuit = CircuitBreaker()

        # Cache - use Redis if configured, otherwise in-memory
        effective_redis_url = redis_url or settings.redis_url
        self._cache = ProxyCache(
            default_ttl=self._cache_ttl,
            redis_url=effective_redis_url,
        )

    async def __aenter__(self) -> PolymarketProxyClient:
        """Enter async context manager."""
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            follow_redirects=True,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit async context manager."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is initialized."""
        if self._http_client is None:
            raise RuntimeError(
                "PolymarketProxyClient must be used as async context manager: "
                "async with PolymarketProxyClient() as client: ..."
            )
        return self._http_client

    async def _rate_limit(self, api: str) -> None:
        """Apply rate limiting for the specified API."""
        now = time.monotonic()

        if api == "clob":
            elapsed = now - self._last_clob_request
            if elapsed < self._clob_interval:
                await asyncio.sleep(self._clob_interval - elapsed)
            self._last_clob_request = time.monotonic()
        elif api == "data":
            elapsed = now - self._last_data_request
            if elapsed < self._data_interval:
                await asyncio.sleep(self._data_interval - elapsed)
            self._last_data_request = time.monotonic()
        # Gamma API uses same rate limit as CLOB

    def _get_circuit(self, api: str) -> CircuitBreaker:
        """Get circuit breaker for the specified API."""
        if api == "clob":
            return self._clob_circuit
        elif api == "data":
            return self._data_circuit
        else:
            return self._gamma_circuit

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        api: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> httpx.Response:
        """Make a request with exponential backoff retry.

        Args:
            method: HTTP method (GET, POST, etc.).
            url: Full URL to request.
            api: API name for rate limiting/circuit breaker (clob, data, gamma).
            endpoint: The endpoint path for error context.
            params: Query parameters.
            json: JSON body for POST requests.

        Returns:
            Response object.

        Raises:
            CircuitOpenError: If circuit breaker is open.
            UpstreamRateLimitError: If rate limit exhausted after retries.
            ProxyError: On upstream API failures after all retries.
        """
        circuit = self._get_circuit(api)

        if not circuit.can_execute():
            self._logger.warning(
                "Circuit breaker open, blocking request",
                api=api,
                endpoint=endpoint,
                circuit_state=circuit.state.value,
            )
            raise CircuitOpenError(
                message=f"Circuit breaker open for {api} API",
                api=api,
                retry_after=int(circuit.recovery_timeout),
            )

        client = self._ensure_client()
        last_error: Exception | None = None
        last_status_code: int | None = None
        rate_limit_hit = False

        for attempt in range(self.MAX_RETRIES):
            await self._rate_limit(api)

            try:
                self._logger.debug(
                    "Proxy request",
                    method=method,
                    url=url,
                    api=api,
                    endpoint=endpoint,
                    attempt=attempt + 1,
                )

                response = await client.request(method, url, params=params, json=json)
                last_status_code = response.status_code

                # Check for rate limit response
                if response.status_code == 429:
                    rate_limit_hit = True
                    retry_after = response.headers.get("Retry-After", "10")
                    delay = min(float(retry_after), self.RETRY_MAX_DELAY)
                    self._logger.warning(
                        "Rate limited by upstream",
                        api=api,
                        endpoint=endpoint,
                        retry_after=delay,
                        attempt=attempt + 1,
                    )
                    if attempt < self.MAX_RETRIES - 1:
                        await asyncio.sleep(delay)
                        continue
                    # Last attempt hit rate limit - will be raised below

                # Check for server errors (retryable)
                if response.status_code >= 500:
                    response.raise_for_status()

                # Success
                circuit.record_success()
                return response

            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                last_error = e
                circuit.record_failure()

                # Calculate delay with exponential backoff + jitter
                delay = min(
                    self.RETRY_BASE_DELAY * (2**attempt),
                    self.RETRY_MAX_DELAY,
                )
                # Add jitter (±25%)
                delay *= 0.75 + random.random() * 0.5

                self._logger.warning(
                    "Proxy request failed, retrying",
                    api=api,
                    endpoint=endpoint,
                    attempt=attempt + 1,
                    max_retries=self.MAX_RETRIES,
                    delay=delay,
                    error=str(e),
                    error_type=type(e).__name__,
                )

                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(delay)

        # All retries exhausted - log and raise appropriate error
        self._logger.error(
            "Proxy request failed after all retries",
            api=api,
            endpoint=endpoint,
            attempts=self.MAX_RETRIES,
            last_error=str(last_error) if last_error else None,
            last_status_code=last_status_code,
            rate_limit_hit=rate_limit_hit,
        )

        if rate_limit_hit:
            raise UpstreamRateLimitError(
                message=f"Polymarket {api} API rate limit exceeded after {self.MAX_RETRIES} retries",
                api=api,
                retry_after=10,
            )

        # Extract upstream error details if available
        upstream_error: str | None = None
        if last_error is not None and isinstance(last_error, httpx.HTTPStatusError):
            try:
                upstream_error = last_error.response.text[:500]
            except Exception:
                upstream_error = str(last_error)

        raise ProxyError(
            message=f"Polymarket {api} API request failed after {self.MAX_RETRIES} retries",
            upstream_status=last_status_code,
            upstream_error=upstream_error,
            api=api,
            endpoint=endpoint,
        )

    async def get_clob(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        *,
        cache_ttl: int | None = None,
        skip_cache: bool = False,
        stale_on_error: bool = True,
    ) -> tuple[dict[str, Any], str]:
        """Make a GET request to the CLOB API.

        Args:
            endpoint: API endpoint (e.g., "/book", "/prices-history").
            params: Query parameters.
            cache_ttl: Override default cache TTL.
            skip_cache: Skip cache lookup/storage.
            stale_on_error: Return stale cached data on transient failures.

        Returns:
            Tuple of (response_data, cache_status). cache_status is HIT/MISS/STALE.

        Raises:
            CircuitOpenError: If circuit breaker is open.
            UpstreamRateLimitError: If rate limit exhausted.
            ProxyError: On upstream API failures.
        """
        cache_key = f"clob:{endpoint}"

        if not skip_cache:
            cached, status = await self._cache.get(cache_key, params)
            if cached is not None and status != "MISS":
                self._logger.info(
                    "Cache lookup",
                    api="clob",
                    endpoint=endpoint,
                    cache_status=status,
                )
                return cached, status

        url = f"{self._clob_url}{endpoint}"

        try:
            response = await self._request_with_retry(
                "GET", url, "clob", endpoint, params=params
            )
            response.raise_for_status()

            data = response.json()

            if not skip_cache:
                await self._cache.set(cache_key, params, data, ttl=cache_ttl)

            self._logger.info(
                "Cache lookup",
                api="clob",
                endpoint=endpoint,
                cache_status="MISS",
            )
            return data, "MISS"

        except (CircuitOpenError, UpstreamRateLimitError, ProxyError) as e:
            # Try to return stale cached data on transient failures
            if stale_on_error and not skip_cache:
                stale_data, stale_status = await self._cache.get(cache_key, params)
                if stale_data is not None:
                    self._logger.info(
                        "Returning stale cached data after error",
                        api="clob",
                        endpoint=endpoint,
                        cache_status="STALE",
                        error_type=type(e).__name__,
                    )
                    return stale_data, "STALE"
            raise

    async def get_data(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        *,
        cache_ttl: int | None = None,
        skip_cache: bool = False,
        stale_on_error: bool = True,
    ) -> tuple[dict[str, Any], str]:
        """Make a GET request to the Data API.

        Args:
            endpoint: API endpoint (e.g., "/trades", "/top-holders").
            params: Query parameters.
            cache_ttl: Override default cache TTL.
            skip_cache: Skip cache lookup/storage.
            stale_on_error: Return stale cached data on transient failures.

        Returns:
            Tuple of (response_data, cache_status). cache_status is HIT/MISS/STALE.

        Raises:
            CircuitOpenError: If circuit breaker is open.
            UpstreamRateLimitError: If rate limit exhausted.
            ProxyError: On upstream API failures.
        """
        cache_key = f"data:{endpoint}"

        if not skip_cache:
            cached, status = await self._cache.get(cache_key, params)
            if cached is not None and status != "MISS":
                self._logger.info(
                    "Cache lookup",
                    api="data",
                    endpoint=endpoint,
                    cache_status=status,
                )
                return cached, status

        url = f"{self._data_url}{endpoint}"

        try:
            response = await self._request_with_retry(
                "GET", url, "data", endpoint, params=params
            )
            response.raise_for_status()

            data = response.json()

            if not skip_cache:
                await self._cache.set(cache_key, params, data, ttl=cache_ttl)

            self._logger.info(
                "Cache lookup",
                api="data",
                endpoint=endpoint,
                cache_status="MISS",
            )
            return data, "MISS"

        except (CircuitOpenError, UpstreamRateLimitError, ProxyError) as e:
            # Try to return stale cached data on transient failures
            if stale_on_error and not skip_cache:
                stale_data, stale_status = await self._cache.get(cache_key, params)
                if stale_data is not None:
                    self._logger.info(
                        "Returning stale cached data after error",
                        api="data",
                        endpoint=endpoint,
                        cache_status="STALE",
                        error_type=type(e).__name__,
                    )
                    return stale_data, "STALE"
            raise

    async def get_gamma(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        *,
        cache_ttl: int | None = None,
        skip_cache: bool = False,
        stale_on_error: bool = True,
    ) -> tuple[dict[str, Any], str]:
        """Make a GET request to the Gamma API.

        Args:
            endpoint: API endpoint (e.g., "/markets", "/events").
            params: Query parameters.
            cache_ttl: Override default cache TTL.
            skip_cache: Skip cache lookup/storage.
            stale_on_error: Return stale cached data on transient failures.

        Returns:
            Tuple of (response_data, cache_status). cache_status is HIT/MISS/STALE.

        Raises:
            CircuitOpenError: If circuit breaker is open.
            UpstreamRateLimitError: If rate limit exhausted.
            ProxyError: On upstream API failures.
        """
        cache_key = f"gamma:{endpoint}"

        if not skip_cache:
            cached, status = await self._cache.get(cache_key, params)
            if cached is not None and status != "MISS":
                self._logger.info(
                    "Cache lookup",
                    api="gamma",
                    endpoint=endpoint,
                    cache_status=status,
                )
                return cached, status

        url = f"{self._gamma_url}{endpoint}"

        try:
            response = await self._request_with_retry(
                "GET", url, "gamma", endpoint, params=params
            )
            response.raise_for_status()

            data = response.json()

            if not skip_cache:
                await self._cache.set(cache_key, params, data, ttl=cache_ttl)

            self._logger.info(
                "Cache lookup",
                api="gamma",
                endpoint=endpoint,
                cache_status="MISS",
            )
            return data, "MISS"

        except (CircuitOpenError, UpstreamRateLimitError, ProxyError) as e:
            # Try to return stale cached data on transient failures
            if stale_on_error and not skip_cache:
                stale_data, stale_status = await self._cache.get(cache_key, params)
                if stale_data is not None:
                    self._logger.info(
                        "Returning stale cached data after error",
                        api="gamma",
                        endpoint=endpoint,
                        cache_status="STALE",
                        error_type=type(e).__name__,
                    )
                    return stale_data, "STALE"
            raise

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return self._cache.stats

    def get_circuit_status(self) -> dict[str, str]:
        """Get circuit breaker status for all APIs."""
        return {
            "clob": self._clob_circuit.state.value,
            "data": self._data_circuit.state.value,
            "gamma": self._gamma_circuit.state.value,
        }

    async def invalidate_cache(self, pattern: str | None = None) -> int:
        """Invalidate cache entries.

        Args:
            pattern: Key prefix to match (None = clear all).

        Returns:
            Number of entries removed.
        """
        return await self._cache.invalidate(pattern)

    async def health_check(self) -> dict[str, Any]:
        """Check health of Polymarket APIs.

        Returns:
            Dict with health status for each API.
        """
        results: dict[str, Any] = {}

        # Check CLOB API
        try:
            url = f"{self._clob_url}/markets"
            response = await self._ensure_client().get(url, params={"limit": 1})
            results["clob"] = {
                "status": "healthy" if response.status_code == 200 else "degraded",
                "status_code": response.status_code,
                "latency_ms": response.elapsed.total_seconds() * 1000,
            }
        except Exception as e:
            results["clob"] = {"status": "unhealthy", "error": str(e)}

        # Check Data API
        try:
            url = f"{self._data_url}/trades"
            response = await self._ensure_client().get(url, params={"limit": 1})
            results["data"] = {
                "status": "healthy" if response.status_code == 200 else "degraded",
                "status_code": response.status_code,
                "latency_ms": response.elapsed.total_seconds() * 1000,
            }
        except Exception as e:
            results["data"] = {"status": "unhealthy", "error": str(e)}

        # Check Gamma API
        try:
            url = f"{self._gamma_url}/markets"
            response = await self._ensure_client().get(url, params={"limit": 1})
            results["gamma"] = {
                "status": "healthy" if response.status_code == 200 else "degraded",
                "status_code": response.status_code,
                "latency_ms": response.elapsed.total_seconds() * 1000,
            }
        except Exception as e:
            results["gamma"] = {"status": "unhealthy", "error": str(e)}

        return results


# Singleton instance for dependency injection
_proxy_client: PolymarketProxyClient | None = None


async def get_proxy_client() -> PolymarketProxyClient:
    """Get the global Polymarket proxy client.

    Creates a new client if one doesn't exist. The client is created
    as a singleton and should be used throughout the application.

    Returns:
        Initialized PolymarketProxyClient.
    """
    global _proxy_client
    if _proxy_client is None:
        _proxy_client = PolymarketProxyClient()
        await _proxy_client.__aenter__()
    return _proxy_client


async def close_proxy_client() -> None:
    """Close the global Polymarket proxy client.

    Should be called during application shutdown.
    """
    global _proxy_client
    if _proxy_client is not None:
        await _proxy_client._cache.close()
        await _proxy_client.__aexit__(None, None, None)
        _proxy_client = None
