"""Custom exception classes for Polymarket proxy layer.

These exceptions provide consistent error responses for proxy-related failures:
- ProxyError: Base class for all proxy errors (502 Bad Gateway)
- CircuitOpenError: Circuit breaker is open (503 Service Unavailable)
- UpstreamRateLimitError: Polymarket rate limit hit (429 Too Many Requests)
- UpstreamNotFoundError: Resource not found on upstream (404 Not Found)
"""

from typing import Any

from fastapi import status

from prediction_data.api.exceptions import APIError


class ProxyError(APIError):
    """Base class for proxy layer errors (502 Bad Gateway).

    Used when the upstream Polymarket API fails or returns an error.
    Includes upstream details for debugging.
    """

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "PROXY_ERROR"
    message = "Polymarket API request failed"

    def __init__(
        self,
        message: str | None = None,
        upstream_status: int | None = None,
        upstream_error: str | None = None,
        api: str | None = None,
        endpoint: str | None = None,
        **extra: Any,
    ) -> None:
        """Initialize proxy error with upstream context.

        Args:
            message: Human-readable error message.
            upstream_status: HTTP status from upstream API if available.
            upstream_error: Error message from upstream API if available.
            api: Which API failed (clob, data, gamma).
            endpoint: The endpoint that was called.
            **extra: Additional fields.
        """
        if upstream_status is not None:
            extra["upstream_status"] = upstream_status
        if upstream_error is not None:
            extra["upstream_error"] = upstream_error
        if api is not None:
            extra["api"] = api
        if endpoint is not None:
            extra["endpoint"] = endpoint
        super().__init__(message=message, **extra)


class CircuitOpenError(APIError):
    """Circuit breaker is open (503 Service Unavailable).

    Used when too many failures have occurred and the circuit breaker
    is preventing requests to protect against cascading failures.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "SERVICE_UNAVAILABLE"
    message = "Service temporarily unavailable"

    def __init__(
        self,
        message: str | None = None,
        api: str | None = None,
        retry_after: int = 30,
        **extra: Any,
    ) -> None:
        """Initialize circuit open error with retry information.

        Args:
            message: Human-readable error message.
            api: Which API circuit is open (clob, data, gamma).
            retry_after: Seconds until the circuit may close.
            **extra: Additional fields.
        """
        if api is not None:
            extra["api"] = api
        extra["retry_after"] = retry_after
        super().__init__(message=message, **extra)
        self.headers = {"Retry-After": str(retry_after)}


class UpstreamRateLimitError(APIError):
    """Polymarket rate limit exceeded (429 Too Many Requests).

    Used when Polymarket returns a 429 status indicating we've hit
    their rate limits. Includes Retry-After header.
    """

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "UPSTREAM_RATE_LIMITED"
    message = "Polymarket rate limit exceeded"

    def __init__(
        self,
        message: str | None = None,
        api: str | None = None,
        retry_after: int = 10,
        **extra: Any,
    ) -> None:
        """Initialize rate limit error with retry information.

        Args:
            message: Human-readable error message.
            api: Which API hit rate limit (clob, data, gamma).
            retry_after: Seconds to wait before retrying.
            **extra: Additional fields.
        """
        if api is not None:
            extra["api"] = api
        extra["retry_after"] = retry_after
        super().__init__(message=message, **extra)
        self.headers = {"Retry-After": str(retry_after)}


class UpstreamNotFoundError(APIError):
    """Resource not found on upstream (404 Not Found).

    Used when Polymarket returns a 404 for a requested resource,
    such as an invalid token ID or market.
    """

    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"
    message = "Resource not found"

    def __init__(
        self,
        message: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        **extra: Any,
    ) -> None:
        """Initialize not found error with resource context.

        Args:
            message: Human-readable error message.
            resource_type: Type of resource (market, token, etc).
            resource_id: ID of the resource that wasn't found.
            **extra: Additional fields.
        """
        if resource_type is not None:
            extra["resource_type"] = resource_type
        if resource_id is not None:
            extra["resource_id"] = resource_id
        super().__init__(message=message, **extra)
