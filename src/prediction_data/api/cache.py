"""Response caching utilities for the API layer.

Provides:
- Cache-Control header configuration for different endpoint types
- ETag generation and validation for conditional requests
- Cache-related response headers
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from prediction_data.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)

# Cache durations in seconds
CACHE_DURATION_PUBLIC = 60  # 1 minute for public data (markets, traders, events)
CACHE_DURATION_STATIC = 300  # 5 minutes for relatively static data (tags)
CACHE_DURATION_LEADERBOARD = 120  # 2 minutes for leaderboards
CACHE_DURATION_NONE = 0  # No caching for dynamic/authenticated endpoints

# Paths that should have public caching enabled
# These are read-only endpoints that return the same data for all users
PUBLIC_CACHE_PATHS: dict[str, int] = {
    "/api/v1/markets": CACHE_DURATION_PUBLIC,
    "/api/v1/markets/advanced": CACHE_DURATION_PUBLIC,
    "/api/v1/markets/screener": CACHE_DURATION_PUBLIC,
    "/api/v1/markets/tags": CACHE_DURATION_STATIC,
    "/api/v1/traders": CACHE_DURATION_PUBLIC,
    "/api/v1/traders/smart-scores": CACHE_DURATION_LEADERBOARD,
    "/api/v1/traders/leaderboard": CACHE_DURATION_LEADERBOARD,
    "/api/v1/events": CACHE_DURATION_PUBLIC,
    "/api/v1/trades/smart": CACHE_DURATION_PUBLIC,
    "/api/v1/trades/whales": CACHE_DURATION_PUBLIC,
    "/api/v1/tags": CACHE_DURATION_STATIC,  # Event tags cached for 5 minutes
}

# Path prefixes that should have public caching (for dynamic segments)
# Format: (prefix, max_age)
PUBLIC_CACHE_PREFIXES: list[tuple[str, int]] = [
    ("/api/v1/markets/", CACHE_DURATION_PUBLIC),  # market detail, trades, price-history
    ("/api/v1/traders/", CACHE_DURATION_PUBLIC),  # trader detail, trades
    ("/api/v1/events/", CACHE_DURATION_PUBLIC),  # event detail
]

# Paths that should never be cached (authenticated/dynamic)
NO_CACHE_PATHS: set[str] = {
    "/api/v1/auth/",
    "/api/v1/watchlist",
    "/api/v1/tracked-traders",
    "/health",
}


def _get_cache_duration(path: str, method: str) -> int:
    """Determine cache duration for a path.

    Args:
        path: Request path.
        method: HTTP method.

    Returns:
        Cache duration in seconds, or 0 for no caching.
    """
    # Only GET requests should be cached
    if method != "GET":
        return CACHE_DURATION_NONE

    # Check if path is in no-cache list
    for no_cache_prefix in NO_CACHE_PATHS:
        if path.startswith(no_cache_prefix):
            return CACHE_DURATION_NONE

    # Check exact match first
    if path in PUBLIC_CACHE_PATHS:
        return PUBLIC_CACHE_PATHS[path]

    # Check prefix matches
    for prefix, duration in PUBLIC_CACHE_PREFIXES:
        if path.startswith(prefix):
            return duration

    # Default: no caching for unrecognized paths
    return CACHE_DURATION_NONE


def generate_etag(content: bytes) -> str:
    """Generate an ETag from response content.

    Uses MD5 hash for speed (not cryptographic security).

    Args:
        content: Response body bytes.

    Returns:
        ETag string in weak format (W/"hash").
    """
    # Use weak ETags since response may vary with compression
    hash_value = hashlib.md5(content, usedforsecurity=False).hexdigest()[:16]
    return f'W/"{hash_value}"'


def check_etag_match(request: Request, etag: str) -> bool:
    """Check if request's If-None-Match header matches the ETag.

    Args:
        request: The HTTP request.
        etag: The current ETag value.

    Returns:
        True if the ETag matches (client has current version).
    """
    if_none_match = request.headers.get("If-None-Match")
    if not if_none_match:
        return False

    # Handle multiple ETags in If-None-Match
    client_etags = [e.strip() for e in if_none_match.split(",")]

    # Check for wildcard or exact match
    return "*" in client_etags or etag in client_etags


class CacheHeaderMiddleware(BaseHTTPMiddleware):
    """Middleware to add Cache-Control and ETag headers to responses.

    Features:
    - Adds Cache-Control headers based on endpoint type
    - Generates ETags for cacheable responses
    - Handles conditional requests (If-None-Match) for 304 responses
    - Adds Vary header for proper cache key differentiation
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Any]
    ) -> Response:
        """Process request and add caching headers."""
        method = request.method
        path = request.url.path

        # Get cache duration for this endpoint
        cache_duration = _get_cache_duration(path, method)

        # Process the request
        response: Response = await call_next(request)

        # Skip caching for error responses
        if response.status_code >= 400:
            response.headers["Cache-Control"] = "no-store"
            return response

        # Add caching headers based on endpoint type
        if cache_duration > 0:
            # Public endpoint - enable caching
            response.headers["Cache-Control"] = (
                f"public, max-age={cache_duration}, "
                f"stale-while-revalidate={cache_duration // 2}"
            )

            # Add Vary header for proper cache key differentiation
            # Important for CDNs and proxies
            response.headers["Vary"] = "Accept-Encoding"

            # Generate ETag for the response
            # Note: This requires reading the response body which has performance implications
            # For simplicity, we only do this for smaller responses
            if hasattr(response, "body"):
                body = response.body
                if len(body) < 1_000_000:  # Only ETag for responses < 1MB
                    # Ensure body is bytes for hashing
                    body_bytes = bytes(body) if isinstance(body, memoryview) else body
                    etag = generate_etag(body_bytes)
                    response.headers["ETag"] = etag

                    # Check for conditional request
                    if check_etag_match(request, etag):
                        # Client has current version - return 304 Not Modified
                        return Response(
                            status_code=304,
                            headers={
                                "ETag": etag,
                                "Cache-Control": response.headers.get(
                                    "Cache-Control", ""
                                ),
                            },
                        )
        else:
            # Authenticated or dynamic endpoint - no caching
            response.headers["Cache-Control"] = "private, no-cache, no-store"

        return response
