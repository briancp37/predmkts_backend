"""Custom exception classes for user feature API endpoints.

These exceptions provide consistent error responses across the API:
- Each exception maps to a specific HTTP status code
- Error responses use format: {"detail": str, "code": str, ...extra}
"""

from typing import Any

from fastapi import HTTPException, status


class APIError(HTTPException):
    """Base class for API errors with consistent response format."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"
    message: str = "An internal error occurred"

    def __init__(
        self,
        message: str | None = None,
        code: str | None = None,
        **extra: Any,
    ) -> None:
        """Initialize the API error.

        Args:
            message: Human-readable error message. Defaults to class message.
            code: Machine-readable error code. Defaults to class code.
            **extra: Additional fields to include in the error response.
        """
        self._message = message or self.message
        self._code = code or self.code

        detail: dict[str, Any] = {
            "message": self._message,
            "code": self._code,
        }
        detail.update(extra)

        super().__init__(status_code=self.status_code, detail=detail)


class NotFoundError(APIError):
    """Resource not found error (404).

    Used when a requested resource does not exist or the user does not have
    access to it.
    """

    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"
    message = "Resource not found"


class DuplicateError(APIError):
    """Duplicate resource error (400).

    Used when attempting to create a resource that already exists,
    such as adding a market to watchlist that's already there.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    code = "ALREADY_EXISTS"
    message = "Resource already exists"


class TierLimitExceededError(APIError):
    """Tier limit exceeded error (403).

    Used when a user attempts to exceed their tier's resource limit,
    such as adding more tracked traders than allowed.
    """

    status_code = status.HTTP_403_FORBIDDEN
    code = "TIER_LIMIT_EXCEEDED"
    message = "Tier limit exceeded"

    def __init__(
        self,
        message: str | None = None,
        limit: int | None = None,
        count: int | None = None,
        **extra: Any,
    ) -> None:
        """Initialize tier limit exceeded error.

        Args:
            message: Human-readable error message.
            limit: The user's tier limit.
            count: Current count of resources.
            **extra: Additional fields.
        """
        if limit is not None:
            extra["limit"] = limit
        if count is not None:
            extra["count"] = count
        super().__init__(message=message, **extra)


class UnauthorizedError(APIError):
    """Unauthorized error (401).

    Used when authentication is required but missing or invalid.
    """

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"
    message = "Authentication required"

    def __init__(
        self,
        message: str | None = None,
        **extra: Any,
    ) -> None:
        """Initialize unauthorized error with WWW-Authenticate header."""
        super().__init__(message=message, **extra)
        # Add standard OAuth2 header for 401 responses
        self.headers = {"WWW-Authenticate": "Bearer"}


class ValidationError(APIError):
    """Validation error (400).

    Used when request data fails validation, such as an invalid market ID.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    code = "VALIDATION_ERROR"
    message = "Validation failed"
