"""FastAPI application entry point."""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from prediction_data.api.auth.router import router as auth_router
from prediction_data.api.cache import CacheHeaderMiddleware
from prediction_data.api.clob_client import close_clob_client
from prediction_data.api.events.router import router as events_router
from prediction_data.api.exceptions import APIError
from prediction_data.api.health import router as health_router
from prediction_data.api.markets.router import router as markets_router
from prediction_data.api.middleware import RequestLoggingMiddleware
from prediction_data.api.polymarket_proxy import router as polymarket_proxy_router
from prediction_data.api.polymarket_proxy.client import close_proxy_client
from prediction_data.api.rate_limit import limiter, rate_limit_exceeded_handler
from prediction_data.api.tags.router import router as tags_router
from prediction_data.api.tracked_traders.router import router as tracked_traders_router
from prediction_data.api.traders.router import router as traders_router
from prediction_data.api.trades.router import router as trades_router
from prediction_data.api.watchlist.router import router as watchlist_router
from prediction_data.core.config import get_settings
from prediction_data.core.logging import get_logger
from prediction_data.db.session import create_tables

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    # Startup: validate security configuration
    settings = get_settings()
    settings.validate_jwt_secret()

    # Startup: create database tables
    await create_tables()
    yield
    # Shutdown: cleanup API clients
    await close_clob_client()
    await close_proxy_client()


API_DESCRIPTION = """
## Overview

REST API for prediction market data and user features. Provides access to market data,
trader analytics, watchlists, and tracked trader activity from Polymarket.

## Authentication

Most endpoints require JWT Bearer token authentication. To authenticate:

1. Register a new account via `POST /api/v1/auth/register`
2. Login via `POST /api/v1/auth/login` to receive access and refresh tokens
3. Include the access token in the `Authorization` header: `Bearer <access_token>`
4. When the access token expires (30 min), use `POST /api/v1/auth/refresh` with your refresh token

## Rate Limits

Rate limits vary by endpoint category:

| Category | Limit | Description |
|----------|-------|-------------|
| Auth endpoints | 10 req/min | Brute force prevention |
| Public endpoints | 100 req/min | Markets, traders, events |
| Authenticated endpoints | 200 req/min | Watchlist, tracked traders |
| CLOB proxy | 50 req/min | Advanced market data (Polymarket proxy) |

Rate limit headers returned with each response:
- `X-RateLimit-Limit`: Request limit for the endpoint
- `X-RateLimit-Remaining`: Remaining requests in current window
- `Retry-After`: Seconds to wait (only on 429 responses)

## Error Handling

All errors return a consistent JSON format:

```json
{
  "detail": "Human-readable error message",
  "code": "ERROR_CODE",
  "status": 400
}
```

Common error codes:
- `NOT_FOUND` (404): Resource not found
- `DUPLICATE_ENTRY` (400): Duplicate watchlist/tracker entry
- `TIER_LIMIT_EXCEEDED` (403): Tracked trader limit reached for your tier
- `UNAUTHORIZED` (401): Invalid or expired credentials
- `RATE_LIMIT_EXCEEDED` (429): Too many requests
- `VALIDATION_ERROR` (422): Invalid request parameters

## Versioning

All API endpoints use URL-based versioning with `/api/v1/` prefix.
Health check endpoints are not versioned (`/health`, `/health/ready`, `/health/live`).
"""

OPENAPI_TAGS = [
    {
        "name": "auth",
        "description": "User authentication and account management. Register, login, "
        "refresh tokens, and manage user profile. Rate limited to 10 req/min per IP.",
    },
    {
        "name": "markets",
        "description": "Prediction market data and search. Browse markets, view details, "
        "trades, and price history. Public endpoints rate limited to 100 req/min. "
        "Advanced endpoints (CLOB data) limited to 50 req/min.",
    },
    {
        "name": "traders",
        "description": "Trader analytics and leaderboards. View trader profiles, positions, "
        "trades, smart scores, and leaderboard rankings. Rate limited to 100 req/min.",
    },
    {
        "name": "watchlist",
        "description": "User market watchlist management. Add, remove, and view watched markets. "
        "Requires authentication. Rate limited to 200 req/min per user.",
    },
    {
        "name": "tracked-traders",
        "description": "Tracked trader management and activity feed. Track wallets to monitor "
        "their trading activity. Tier-based limits apply (free: 5, pro: 50). "
        "Requires authentication. Rate limited to 200 req/min per user.",
    },
    {
        "name": "trades",
        "description": "Smart money and whale trade detection. View high-conviction trades "
        "from smart traders and large whale transactions. Rate limited to 100 req/min.",
    },
    {
        "name": "events",
        "description": "Event data and associated markets. Browse events and their markets. "
        "Rate limited to 100 req/min.",
    },
    {
        "name": "tags",
        "description": "Event tags for filtering. Get available tags like 'Sports', 'Politics', "
        "'Crypto' with event counts. Use these to filter markets and events. "
        "Rate limited to 100 req/min. Cached for 5 minutes.",
    },
    {
        "name": "health",
        "description": "Health check endpoints for monitoring and Kubernetes probes. "
        "Not versioned, not rate limited.",
    },
    {
        "name": "polymarket-proxy",
        "description": "Proxy layer for Polymarket APIs (CLOB, Data, Gamma). "
        "Provides cached access to real-time market data with rate limiting, "
        "circuit breaker protection, and retry logic. Rate limited to 50 req/min.",
    },
]

app = FastAPI(
    title="Prediction Markets API",
    description=API_DESCRIPTION,
    version="0.1.0",
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
)

# Add rate limiter state and exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Request logging middleware - must be added first (outermost)
# so it wraps all other middleware and captures accurate timing
app.add_middleware(RequestLoggingMiddleware)

# Cache header middleware - adds Cache-Control, ETag, and Vary headers
# to public endpoints for better client and CDN caching
app.add_middleware(CacheHeaderMiddleware)

# CORS middleware - configurable via CORS_ORIGINS environment variable
# In production, set CORS_ORIGINS to your frontend domain(s)
_settings = get_settings()
_cors_origins = _settings.cors_origin_list

# Note: allow_credentials=True requires explicit origins, not wildcards
# When using "*", we disable credentials to avoid security issues
_allow_credentials = "*" not in _cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After"],
)

# Include routers
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(markets_router, prefix="/api/v1/markets", tags=["markets"])
app.include_router(traders_router, prefix="/api/v1/traders", tags=["traders"])
app.include_router(watchlist_router, prefix="/api/v1/watchlist", tags=["watchlist"])
app.include_router(
    tracked_traders_router, prefix="/api/v1/tracked-traders", tags=["tracked-traders"]
)
app.include_router(trades_router, prefix="/api/v1/trades", tags=["trades"])
app.include_router(events_router, prefix="/api/v1/events", tags=["events"])
app.include_router(tags_router, prefix="/api/v1/tags", tags=["tags"])
app.include_router(
    polymarket_proxy_router, prefix="/api/v1/proxy", tags=["polymarket-proxy"]
)
app.include_router(health_router, prefix="/health", tags=["health"])


def _get_request_id(request: Request) -> str:
    """Get request ID from state (set by middleware) or header, or generate one.

    Prefers request.state.request_id which is set by RequestLoggingMiddleware,
    ensuring consistency across all logging for a request.
    """
    # First check if middleware set it in request state
    if hasattr(request.state, "request_id"):
        return str(request.state.request_id)
    # Fall back to header or generate new one
    return request.headers.get("X-Request-ID", str(uuid.uuid4()))


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """Handle custom API errors with consistent JSON format.

    Returns consistent error response: {detail: str, code: str, status: int}
    """
    request_id = _get_request_id(request)

    # Log error with request context
    logger.error(
        "API error",
        status_code=exc.status_code,
        code=exc._code,
        message=exc._message,
        path=request.url.path,
        method=request.method,
        request_id=request_id,
    )

    # Build response body
    body: dict[str, Any] = {
        "detail": exc._message,
        "code": exc._code,
        "status": exc.status_code,
    }

    # Include extra fields from the exception detail if it's a dict
    if isinstance(exc.detail, dict):
        for key, value in exc.detail.items():
            if key not in ("message", "code"):
                body[key] = value

    return JSONResponse(
        status_code=exc.status_code,
        content=body,
        headers={"X-Request-ID": request_id, **(exc.headers or {})},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic request validation errors.

    Returns 422 with field-level error details.
    """
    request_id = _get_request_id(request)

    # Extract field-level errors
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        })

    logger.warning(
        "Validation error",
        path=request.url.path,
        method=request.method,
        request_id=request_id,
        errors=errors,
    )

    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation failed",
            "code": "VALIDATION_ERROR",
            "status": 422,
            "errors": errors,
        },
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unhandled exceptions.

    Logs the full exception and returns a safe error response.
    Stack traces are only included if DEBUG is enabled.
    """
    request_id = _get_request_id(request)
    settings = get_settings()

    # Log the full exception with stack trace
    logger.exception(
        "Unhandled exception",
        path=request.url.path,
        method=request.method,
        request_id=request_id,
        exc_type=type(exc).__name__,
    )

    # Build response body
    body: dict[str, Any] = {
        "detail": "An internal error occurred",
        "code": "INTERNAL_ERROR",
        "status": 500,
        "request_id": request_id,
    }

    # Include stack trace in debug mode only
    if settings.debug:
        import traceback

        body["debug"] = {
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "traceback": traceback.format_exc(),
        }

    return JSONResponse(
        status_code=500,
        content=body,
        headers={"X-Request-ID": request_id},
    )


def custom_openapi() -> dict[str, Any]:
    """Generate custom OpenAPI schema with security schemes."""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )

    # Add security scheme for JWT Bearer tokens
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT access token obtained from /api/v1/auth/login. "
            "Tokens expire after 30 minutes. Use /api/v1/auth/refresh to get new tokens.",
        }
    }

    # Add common error response schemas
    openapi_schema["components"]["schemas"]["ErrorResponse"] = {
        "type": "object",
        "properties": {
            "detail": {"type": "string", "description": "Human-readable error message"},
            "code": {"type": "string", "description": "Machine-readable error code"},
            "status": {"type": "integer", "description": "HTTP status code"},
        },
        "required": ["detail", "code", "status"],
        "example": {
            "detail": "Resource not found",
            "code": "NOT_FOUND",
            "status": 404,
        },
    }

    openapi_schema["components"]["schemas"]["RateLimitResponse"] = {
        "type": "object",
        "properties": {
            "detail": {"type": "string"},
            "code": {"type": "string", "enum": ["RATE_LIMIT_EXCEEDED"]},
            "status": {"type": "integer", "enum": [429]},
            "retry_after": {"type": "integer", "description": "Seconds until rate limit resets"},
        },
        "required": ["detail", "code", "status", "retry_after"],
        "example": {
            "detail": "Rate limit exceeded",
            "code": "RATE_LIMIT_EXCEEDED",
            "status": 429,
            "retry_after": 60,
        },
    }

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore[method-assign]

