"""API middleware for request logging and tracing."""

import time
import uuid
from collections.abc import Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from prediction_data.api.auth.service import decode_token
from prediction_data.core.logging import get_logger

logger = get_logger(__name__)

# Paths that should have sensitive fields excluded from logging
SENSITIVE_PATHS = {"/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/refresh"}

# Threshold for slow request logging (in seconds)
SLOW_REQUEST_THRESHOLD_SECONDS = 1.0


def _get_request_id(request: Request) -> str:
    """Get or generate a request ID for tracing."""
    return request.headers.get("X-Request-ID") or str(uuid.uuid4())


def _extract_user_id(request: Request) -> str | None:
    """Extract user ID from JWT token in Authorization header.

    Returns None if no valid token or auth header is present.
    Exceptions are swallowed to avoid blocking requests due to logging.
    """
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split(" ", 1)[1]
        payload = decode_token(token)
        if payload is None:
            return None

        return payload.get("sub")
    except Exception:
        # Don't let logging failures affect request processing
        return None


def _sanitize_path(path: str) -> str:
    """Return path for logging, noting if it's a sensitive endpoint."""
    return path


def _is_sensitive_path(path: str) -> bool:
    """Check if the path is a sensitive endpoint."""
    return path in SENSITIVE_PATHS


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for comprehensive request/response logging.

    Logs each request with:
    - method, path, status_code, duration_ms
    - user_id (if authenticated)
    - request_id for distributed tracing

    Features:
    - Adds X-Request-ID header to all responses
    - Logs slow requests (> 1s) at WARNING level
    - Logs errors at ERROR level
    - Excludes sensitive data (passwords, tokens) from logs
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Any]
    ) -> Response:
        """Process request with logging."""
        request_id = _get_request_id(request)
        user_id = _extract_user_id(request)
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"

        # Store request_id in request state for access in exception handlers
        request.state.request_id = request_id

        # Start timing
        start_time = time.perf_counter()

        # Log request start (debug level to avoid excessive logging)
        logger.debug(
            "Request started",
            request_id=request_id,
            method=method,
            path=path,
            client_ip=client_ip,
            user_id=user_id,
        )

        # Process request
        response: Response
        try:
            response = await call_next(request)
        except Exception:
            # Calculate duration even on exception
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log at error level for unhandled exceptions
            logger.error(
                "Request failed with unhandled exception",
                request_id=request_id,
                method=method,
                path=path,
                client_ip=client_ip,
                user_id=user_id,
                duration_ms=round(duration_ms, 2),
            )
            raise

        # Calculate duration
        duration_ms = (time.perf_counter() - start_time) * 1000
        status_code = response.status_code

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        # Build log context
        log_context: dict[str, Any] = {
            "request_id": request_id,
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            "client_ip": client_ip,
        }

        if user_id:
            log_context["user_id"] = user_id

        # Note if this is a sensitive endpoint (but don't log the content)
        if _is_sensitive_path(path):
            log_context["sensitive"] = True

        # Determine log level based on status and duration
        if status_code >= 500:
            logger.error("Request completed with server error", **log_context)
        elif status_code >= 400:
            logger.warning("Request completed with client error", **log_context)
        elif duration_ms > SLOW_REQUEST_THRESHOLD_SECONDS * 1000:
            logger.warning("Slow request completed", **log_context)
        else:
            logger.info("Request completed", **log_context)

        return response
