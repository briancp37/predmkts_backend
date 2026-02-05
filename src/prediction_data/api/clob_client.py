"""Polymarket CLOB API client for real-time order book data.

Provides async functions to fetch bid/ask data from the CLOB API for
enriching market responses with real-time pricing information.

Note: Unlike the bronze layer CLOB client (which uses L2 auth for trades),
these order book endpoints are public and do not require authentication.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from prediction_data.core.logging import get_logger

if TYPE_CHECKING:
    pass

# CLOB API base URL
CLOB_API_BASE_URL = "https://clob.polymarket.com"

# Rate limit: 500 req/10s (from docs), so max ~50 req/s
# We'll be conservative and limit to 30 req/s
RATE_LIMIT_REQUESTS_PER_SECOND = 30

# Maximum tokens per batch request
MAX_BATCH_SIZE = 500

# Default cache TTL in seconds
DEFAULT_CACHE_TTL = 30


@dataclass
class OrderLevel:
    """Single level in the order book (bid or ask)."""

    price: float
    size: float


@dataclass
class OrderBookSummary:
    """Order book summary with best bid/ask extracted."""

    token_id: str
    bid: float | None = None
    ask: float | None = None
    spread: float | None = None
    spread_percent: float | None = None
    spread_cents: float | None = None
    timestamp: str | None = None

    @classmethod
    def from_api_response(cls, token_id: str, data: dict[str, Any]) -> OrderBookSummary:
        """Create OrderBookSummary from CLOB API response.

        Extracts best bid (highest) and best ask (lowest) from the order book.

        Args:
            token_id: The token ID this order book belongs to.
            data: Raw API response for a single order book.

        Returns:
            OrderBookSummary with computed spread values.
        """
        bids = data.get("bids", [])
        asks = data.get("asks", [])
        timestamp = data.get("timestamp")

        # Extract best bid (highest price in bids)
        best_bid: float | None = None
        if bids:
            best_bid = max(float(level["price"]) for level in bids)

        # Extract best ask (lowest price in asks)
        best_ask: float | None = None
        if asks:
            best_ask = min(float(level["price"]) for level in asks)

        # Calculate spread metrics
        spread: float | None = None
        spread_percent: float | None = None
        spread_cents: float | None = None

        if best_bid is not None and best_ask is not None:
            spread = best_ask - best_bid
            spread_cents = spread * 100  # Convert to cents (prices are 0-1)

            # Calculate spread percent based on midpoint
            midpoint = (best_bid + best_ask) / 2
            if midpoint > 0:
                spread_percent = (spread / midpoint) * 100

        return cls(
            token_id=token_id,
            bid=best_bid,
            ask=best_ask,
            spread=spread,
            spread_percent=spread_percent,
            spread_cents=spread_cents,
            timestamp=timestamp,
        )


@dataclass
class CacheEntry:
    """Cached order book data with TTL tracking."""

    data: OrderBookSummary
    expires_at: float


class ClobApiClient:
    """Async client for Polymarket CLOB API order book data.

    Provides methods to fetch real-time bid/ask data for market enrichment.
    Includes response caching and rate limiting.

    Example:
        async with ClobApiClient() as client:
            # Single token
            summary = await client.get_order_book("token_123")

            # Batch tokens
            summaries = await client.get_order_books(["token_1", "token_2"])
    """

    def __init__(
        self,
        *,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        rate_limit_per_second: float = RATE_LIMIT_REQUESTS_PER_SECOND,
        timeout: float = 10.0,
    ) -> None:
        """Initialize the CLOB API client.

        Args:
            cache_ttl: Cache TTL in seconds (default 30).
            rate_limit_per_second: Maximum requests per second.
            timeout: Request timeout in seconds.
        """
        self._cache_ttl = cache_ttl
        self._rate_limit_per_second = rate_limit_per_second
        self._timeout = timeout
        self._cache: dict[str, CacheEntry] = {}
        self._last_request_time: float = 0.0
        self._request_interval = 1.0 / rate_limit_per_second
        self._http_client: httpx.AsyncClient | None = None
        self._logger: structlog.stdlib.BoundLogger = get_logger(__name__)

    async def __aenter__(self) -> ClobApiClient:
        """Enter async context manager."""
        self._http_client = httpx.AsyncClient(
            base_url=CLOB_API_BASE_URL,
            timeout=httpx.Timeout(self._timeout),
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
                "ClobApiClient must be used as async context manager: "
                "async with ClobApiClient() as client: ..."
            )
        return self._http_client

    async def _rate_limit(self) -> None:
        """Apply rate limiting by sleeping if necessary."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._request_interval:
            await asyncio.sleep(self._request_interval - elapsed)
        self._last_request_time = time.monotonic()

    def _get_cached(self, token_id: str) -> OrderBookSummary | None:
        """Get cached order book if not expired.

        Args:
            token_id: Token ID to look up.

        Returns:
            Cached OrderBookSummary if valid, None otherwise.
        """
        entry = self._cache.get(token_id)
        if entry is None:
            return None

        now = time.monotonic()
        if now >= entry.expires_at:
            # Cache expired, remove it
            del self._cache[token_id]
            return None

        return entry.data

    def _set_cached(self, summary: OrderBookSummary) -> None:
        """Cache an order book summary.

        Args:
            summary: The OrderBookSummary to cache.
        """
        now = time.monotonic()
        self._cache[summary.token_id] = CacheEntry(
            data=summary,
            expires_at=now + self._cache_ttl,
        )

    def _clean_expired_cache(self) -> None:
        """Remove expired entries from cache."""
        now = time.monotonic()
        expired_keys = [
            key for key, entry in self._cache.items() if now >= entry.expires_at
        ]
        for key in expired_keys:
            del self._cache[key]

    async def get_order_book(self, token_id: str) -> OrderBookSummary | None:
        """Fetch order book for a single token.

        Args:
            token_id: The token ID to fetch.

        Returns:
            OrderBookSummary with bid/ask data, or None if fetch failed.
        """
        # Check cache first
        cached = self._get_cached(token_id)
        if cached is not None:
            self._logger.debug("CLOB cache hit", token_id=token_id)
            return cached

        client = self._ensure_client()
        await self._rate_limit()

        try:
            self._logger.debug("Fetching CLOB order book", token_id=token_id)
            response = await client.get("/book", params={"token_id": token_id})
            response.raise_for_status()

            data = response.json()
            summary = OrderBookSummary.from_api_response(token_id, data)

            # Cache the result
            self._set_cached(summary)

            self._logger.debug(
                "Fetched CLOB order book",
                token_id=token_id,
                bid=summary.bid,
                ask=summary.ask,
            )
            return summary

        except httpx.HTTPStatusError as e:
            self._logger.warning(
                "CLOB API error",
                token_id=token_id,
                status_code=e.response.status_code,
                error=str(e),
            )
            return None
        except Exception as e:
            self._logger.warning(
                "CLOB request failed",
                token_id=token_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    async def get_order_books(
        self, token_ids: list[str]
    ) -> dict[str, OrderBookSummary]:
        """Fetch order books for multiple tokens.

        Uses the batch /books endpoint for efficiency. Tokens that are
        cached will be returned from cache.

        Args:
            token_ids: List of token IDs to fetch.

        Returns:
            Dict mapping token_id to OrderBookSummary. Missing tokens
            (due to errors) will not be in the result.
        """
        if not token_ids:
            return {}

        results: dict[str, OrderBookSummary] = {}
        uncached_token_ids: list[str] = []

        # Check cache for each token
        for token_id in token_ids:
            cached = self._get_cached(token_id)
            if cached is not None:
                results[token_id] = cached
            else:
                uncached_token_ids.append(token_id)

        if not uncached_token_ids:
            self._logger.debug(
                "CLOB batch cache hit", token_count=len(token_ids)
            )
            return results

        self._logger.debug(
            "CLOB batch fetch",
            cached=len(results),
            uncached=len(uncached_token_ids),
        )

        # Fetch uncached tokens in batches
        client = self._ensure_client()

        for i in range(0, len(uncached_token_ids), MAX_BATCH_SIZE):
            batch = uncached_token_ids[i : i + MAX_BATCH_SIZE]
            await self._rate_limit()

            try:
                # Build request body as array of objects
                request_body = [{"token_id": tid} for tid in batch]

                self._logger.debug(
                    "Fetching CLOB order books batch",
                    batch_size=len(batch),
                    batch_index=i // MAX_BATCH_SIZE,
                )

                response = await client.post("/books", json=request_body)
                response.raise_for_status()

                data = response.json()

                # Parse each order book in the response
                # Response is an array of OrderBookSummary objects
                for book_data in data:
                    asset_id = book_data.get("asset_id")
                    if asset_id:
                        summary = OrderBookSummary.from_api_response(asset_id, book_data)
                        results[asset_id] = summary
                        self._set_cached(summary)

                self._logger.debug(
                    "Fetched CLOB order books batch",
                    batch_size=len(batch),
                    results_count=len(data) if isinstance(data, list) else 0,
                )

            except httpx.HTTPStatusError as e:
                self._logger.warning(
                    "CLOB batch API error",
                    batch_size=len(batch),
                    status_code=e.response.status_code,
                    error=str(e),
                )
            except Exception as e:
                self._logger.warning(
                    "CLOB batch request failed",
                    batch_size=len(batch),
                    error=str(e),
                    error_type=type(e).__name__,
                )

        # Periodically clean expired cache entries
        self._clean_expired_cache()

        return results

    def clear_cache(self) -> None:
        """Clear all cached order book data."""
        self._cache.clear()

    @property
    def cache_size(self) -> int:
        """Return current number of cached entries."""
        return len(self._cache)


# Singleton instance for dependency injection
_clob_client: ClobApiClient | None = None


async def get_clob_client() -> ClobApiClient:
    """Get the global CLOB API client.

    Creates a new client if one doesn't exist. The client is created
    as a singleton and should be used throughout the application.

    Returns:
        Initialized ClobApiClient.

    Note:
        In production, this should be managed by FastAPI's lifespan
        events to properly close the client on shutdown.
    """
    global _clob_client
    if _clob_client is None:
        _clob_client = ClobApiClient()
        await _clob_client.__aenter__()
    return _clob_client


async def close_clob_client() -> None:
    """Close the global CLOB API client.

    Should be called during application shutdown.
    """
    global _clob_client
    if _clob_client is not None:
        await _clob_client.__aexit__(None, None, None)
        _clob_client = None
