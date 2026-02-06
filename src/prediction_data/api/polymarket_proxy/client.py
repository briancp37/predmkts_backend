"""Polymarket API proxy client with retry logic, rate limiting, and circuit breaker.

Provides a unified client for proxying requests to Polymarket's CLOB, Gamma, and Data APIs
with built-in resilience patterns including:
- Exponential backoff retry on transient failures
- Rate limiting to stay under Polymarket limits
- Circuit breaker to prevent cascading failures
- Response caching with configurable TTL
- Stale-while-error: returns cached data on transient failures

Rate limits (from CLAUDE.md):
- CLOB API: 9,000 req/10s overall
- Data API: 1,000 req/10s overall, /trades: 200/10s
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import time
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


class ProxyCache:
    """In-memory cache for proxied responses.

    Supports cache-aside pattern with TTL and stale-while-revalidate.
    Cache keys are generated from endpoint + params hash.
    """

    def __init__(self, default_ttl: int = 30, max_size: int = 10000) -> None:
        """Initialize the cache.

        Args:
            default_ttl: Default TTL in seconds.
            max_size: Maximum number of entries before eviction.
        """
        self._cache: dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def _make_key(self, endpoint: str, params: dict[str, Any] | None = None) -> str:
        """Generate cache key from endpoint and params."""
        key_parts = [endpoint]
        if params:
            # Sort params for consistent hashing
            sorted_params = sorted(params.items())
            params_str = str(sorted_params)
            params_hash = hashlib.md5(params_str.encode()).hexdigest()[:12]
            key_parts.append(params_hash)
        return ":".join(key_parts)

    def get(
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
        entry = self._cache.get(key)

        if entry is None:
            self._misses += 1
            return None, "MISS"

        if entry.is_expired():
            if entry.is_stale():
                self._hits += 1
                return entry.data, "STALE"
            # Too old, remove it
            del self._cache[key]
            self._misses += 1
            return None, "MISS"

        self._hits += 1
        return entry.data, "HIT"

    def set(
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
        # Evict if over max size
        if len(self._cache) >= self._max_size:
            self._evict_expired()
            if len(self._cache) >= self._max_size:
                # Still over, remove oldest entries
                self._evict_oldest(len(self._cache) - self._max_size + 100)

        key = self._make_key(endpoint, params)
        ttl = ttl or self._default_ttl
        now = time.monotonic()
        self._cache[key] = CacheEntry(data=data, expires_at=now + ttl)

    def invalidate(self, pattern: str | None = None) -> int:
        """Invalidate cache entries matching pattern.

        Args:
            pattern: Key prefix to match (None = clear all).

        Returns:
            Number of entries removed.
        """
        if pattern is None:
            count = len(self._cache)
            self._cache.clear()
            return count

        keys_to_remove = [k for k in self._cache if k.startswith(pattern)]
        for key in keys_to_remove:
            del self._cache[key]
        return len(keys_to_remove)

    def _evict_expired(self) -> None:
        """Remove all expired entries."""
        keys_to_remove = [k for k, v in self._cache.items() if v.is_expired()]
        for key in keys_to_remove:
            del self._cache[key]

    def _evict_oldest(self, count: int) -> None:
        """Remove the oldest entries."""
        if count <= 0:
            return
        sorted_keys = sorted(self._cache.keys(), key=lambda k: self._cache[k].created_at)
        for key in sorted_keys[:count]:
            del self._cache[key]

    @property
    def stats(self) -> dict[str, int | float]:
        """Return cache statistics."""
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": (
                round(self._hits / (self._hits + self._misses) * 100, 1)
                if (self._hits + self._misses) > 0
                else 0.0
            ),
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
    ) -> None:
        """Initialize the proxy client.

        Args:
            cache_ttl: Default cache TTL in seconds.
            timeout: Request timeout in seconds.
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

        # Cache
        self._cache = ProxyCache(default_ttl=self._cache_ttl)

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
            cached, status = self._cache.get(cache_key, params)
            if cached is not None and status != "MISS":
                return cached, status

        url = f"{self._clob_url}{endpoint}"

        try:
            response = await self._request_with_retry(
                "GET", url, "clob", endpoint, params=params
            )
            response.raise_for_status()

            data = response.json()

            if not skip_cache:
                self._cache.set(cache_key, params, data, ttl=cache_ttl)

            return data, "MISS"

        except (CircuitOpenError, UpstreamRateLimitError, ProxyError) as e:
            # Try to return stale cached data on transient failures
            if stale_on_error and not skip_cache:
                stale_data, stale_status = self._cache.get(cache_key, params)
                if stale_data is not None:
                    self._logger.info(
                        "Returning stale cached data after error",
                        api="clob",
                        endpoint=endpoint,
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
            cached, status = self._cache.get(cache_key, params)
            if cached is not None and status != "MISS":
                return cached, status

        url = f"{self._data_url}{endpoint}"

        try:
            response = await self._request_with_retry(
                "GET", url, "data", endpoint, params=params
            )
            response.raise_for_status()

            data = response.json()

            if not skip_cache:
                self._cache.set(cache_key, params, data, ttl=cache_ttl)

            return data, "MISS"

        except (CircuitOpenError, UpstreamRateLimitError, ProxyError) as e:
            # Try to return stale cached data on transient failures
            if stale_on_error and not skip_cache:
                stale_data, stale_status = self._cache.get(cache_key, params)
                if stale_data is not None:
                    self._logger.info(
                        "Returning stale cached data after error",
                        api="data",
                        endpoint=endpoint,
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
            cached, status = self._cache.get(cache_key, params)
            if cached is not None and status != "MISS":
                return cached, status

        url = f"{self._gamma_url}{endpoint}"

        try:
            response = await self._request_with_retry(
                "GET", url, "gamma", endpoint, params=params
            )
            response.raise_for_status()

            data = response.json()

            if not skip_cache:
                self._cache.set(cache_key, params, data, ttl=cache_ttl)

            return data, "MISS"

        except (CircuitOpenError, UpstreamRateLimitError, ProxyError) as e:
            # Try to return stale cached data on transient failures
            if stale_on_error and not skip_cache:
                stale_data, stale_status = self._cache.get(cache_key, params)
                if stale_data is not None:
                    self._logger.info(
                        "Returning stale cached data after error",
                        api="gamma",
                        endpoint=endpoint,
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

    def invalidate_cache(self, pattern: str | None = None) -> int:
        """Invalidate cache entries.

        Args:
            pattern: Key prefix to match (None = clear all).

        Returns:
            Number of entries removed.
        """
        return self._cache.invalidate(pattern)

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
        await _proxy_client.__aexit__(None, None, None)
        _proxy_client = None
