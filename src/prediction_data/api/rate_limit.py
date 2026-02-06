"""Rate limiting configuration for API endpoints.

Rate limits are defined per endpoint category:
- Auth endpoints: 10 req/min per IP (prevent brute force)
- Public read endpoints: 100 req/min per IP
- Authenticated endpoints: 200 req/min per user
- CLOB proxy endpoints: 50 req/min (stay under Polymarket limits)
"""

from typing import Callable

from fastapi import Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.status import HTTP_429_TOO_MANY_REQUESTS


def get_user_identifier(request: Request) -> str:
    """Get rate limit key based on user ID if authenticated, otherwise IP.

    For authenticated requests, we rate limit by user ID to allow fair usage
    per user regardless of IP. For unauthenticated requests, we use IP.
    """
    # Check for user ID set by authentication middleware
    if hasattr(request.state, "user_id") and request.state.user_id:
        return f"user:{request.state.user_id}"
    return get_remote_address(request)


def get_ip_address(request: Request) -> str:
    """Get client IP address for rate limiting."""
    return get_remote_address(request)


# Create limiter instance with IP-based default
limiter = Limiter(key_func=get_ip_address)

# Rate limit strings for different endpoint categories
AUTH_RATE_LIMIT = "10/minute"  # Strict limit for auth endpoints (brute force prevention)
PUBLIC_RATE_LIMIT = "100/minute"  # Standard limit for public read endpoints
AUTHENTICATED_RATE_LIMIT = "200/minute"  # Higher limit for authenticated users
CLOB_PROXY_RATE_LIMIT = "50/minute"  # Conservative limit for CLOB proxy to stay under Polymarket


def rate_limit_exceeded_handler(request: Request, exc: Exception) -> Response:
    """Custom handler for rate limit exceeded errors.

    Returns a JSON response with proper error format and Retry-After header.
    """
    import json

    # Try to get retry_after from exception, default to 60 seconds
    retry_after = getattr(exc, "retry_after", 60)

    response = Response(
        content=json.dumps({
            "detail": "Rate limit exceeded. Please try again later.",
            "code": "RATE_LIMIT_EXCEEDED",
            "status": HTTP_429_TOO_MANY_REQUESTS,
            "retry_after": retry_after,
        }),
        status_code=HTTP_429_TOO_MANY_REQUESTS,
        media_type="application/json",
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": "See endpoint documentation",
            "X-RateLimit-Remaining": "0",
        },
    )
    return response


def create_auth_rate_limit() -> Callable[..., Callable[..., object]]:
    """Create rate limit decorator for auth endpoints.

    Auth endpoints have the strictest rate limits (10/min) to prevent
    brute force attacks on login/register.
    """
    return limiter.limit(AUTH_RATE_LIMIT)


def create_public_rate_limit() -> Callable[..., Callable[..., object]]:
    """Create rate limit decorator for public read endpoints.

    Public endpoints allow 100 req/min per IP for general API usage.
    """
    return limiter.limit(PUBLIC_RATE_LIMIT)


def create_authenticated_rate_limit() -> Callable[..., Callable[..., object]]:
    """Create rate limit decorator for authenticated endpoints.

    Authenticated endpoints allow 200 req/min per user for higher throughput.
    Uses user ID as the key function for fair per-user limits.
    """
    return limiter.limit(AUTHENTICATED_RATE_LIMIT, key_func=get_user_identifier)


def create_clob_proxy_rate_limit() -> Callable[..., Callable[..., object]]:
    """Create rate limit decorator for CLOB proxy endpoints.

    CLOB proxy endpoints are limited to 50 req/min to stay well under
    Polymarket's rate limits (500 req/10s for /data/trades).
    """
    return limiter.limit(CLOB_PROXY_RATE_LIMIT)
