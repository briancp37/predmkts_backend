"""HTTP client with retry logic and error handling."""

import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

from prediction_data.core.logging import get_logger


@dataclass
class RetryConfig:
    """Configuration for HTTP retry behavior.

    Attributes:
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds for exponential backoff.
        max_delay: Maximum delay in seconds between retries.
        jitter_factor: Jitter factor (0-1) to add randomness to delays.
        retry_status_codes: HTTP status codes that trigger a retry.
    """

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter_factor: float = 0.1
    retry_status_codes: frozenset[int] = field(
        default_factory=lambda: frozenset({429, 500, 502, 503, 504})
    )


@dataclass
class TimeoutConfig:
    """Configuration for HTTP timeout settings.

    Attributes:
        connect: Timeout for establishing a connection in seconds.
        read: Timeout for reading response data in seconds.
        total: Total timeout for the entire request in seconds.
    """

    connect: float = 10.0
    read: float = 30.0
    total: float = 60.0

    def to_httpx_timeout(self) -> httpx.Timeout:
        """Convert to httpx Timeout object."""
        return httpx.Timeout(
            connect=self.connect,
            read=self.read,
            write=self.read,  # Use read timeout for write as well
            pool=self.connect,
        )


def _calculate_backoff_delay(
    attempt: int,
    base_delay: float,
    max_delay: float,
    jitter_factor: float,
) -> float:
    """Calculate delay with exponential backoff and jitter.

    Args:
        attempt: Current attempt number (0-indexed).
        base_delay: Base delay in seconds.
        max_delay: Maximum delay in seconds.
        jitter_factor: Jitter factor (0-1) to add randomness.

    Returns:
        Delay in seconds with jitter applied.
    """
    import random

    # Exponential backoff: base_delay * 2^attempt
    delay = min(base_delay * (2**attempt), max_delay)

    # Add jitter: delay * (1 + random(-jitter, +jitter))
    jitter = delay * jitter_factor * (2 * random.random() - 1)
    return float(max(0, delay + jitter))


def _is_retryable_error(exc: Exception, retry_config: RetryConfig) -> bool:
    """Check if an exception is retryable.

    Args:
        exc: The exception to check.
        retry_config: Retry configuration.

    Returns:
        True if the error is retryable, False otherwise.
    """
    # Network/connection errors are retryable
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        return True

    # Timeout errors are retryable
    if isinstance(exc, (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
        return True

    # HTTP status code errors
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in retry_config.retry_status_codes

    return False


class HttpClient:
    """Async HTTP client with retry logic and error handling.

    Provides a wrapper around httpx with:
    - Exponential backoff with jitter for retries
    - Configurable retry on specific status codes (429, 5xx)
    - Configurable retry on network/connection errors
    - Request/response logging with timing metrics

    Example:
        async with HttpClient() as client:
            response = await client.get("https://api.example.com/data")
            data = response.json()
    """

    def __init__(
        self,
        *,
        retry_config: RetryConfig | None = None,
        timeout_config: TimeoutConfig | None = None,
        base_url: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        """Initialize the HTTP client.

        Args:
            retry_config: Retry behavior configuration.
            timeout_config: Timeout settings configuration.
            base_url: Base URL for all requests.
            headers: Default headers for all requests.
        """
        self._retry_config = retry_config or RetryConfig()
        self._timeout_config = timeout_config or TimeoutConfig()
        self._base_url = base_url
        self._headers = headers or {}
        self._client: httpx.AsyncClient | None = None
        self._logger: structlog.stdlib.BoundLogger = get_logger(__name__)

    async def __aenter__(self) -> "HttpClient":
        """Enter async context manager."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=self._timeout_config.to_httpx_timeout(),
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit async context manager."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure client is initialized."""
        if self._client is None:
            raise RuntimeError(
                "HttpClient must be used as async context manager: "
                "async with HttpClient() as client: ..."
            )
        return self._client

    async def request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.).
            url: URL to request (relative to base_url if set).
            **kwargs: Additional arguments passed to httpx.

        Returns:
            HTTP response object.

        Raises:
            httpx.HTTPStatusError: If request fails after all retries.
            httpx.RequestError: If connection fails after all retries.
        """
        client = self._ensure_client()
        last_exception: Exception | None = None

        for attempt in range(self._retry_config.max_retries + 1):
            start_time = time.perf_counter()

            try:
                self._logger.debug(
                    "HTTP request started",
                    method=method,
                    url=url,
                    attempt=attempt + 1,
                    max_attempts=self._retry_config.max_retries + 1,
                )

                response = await client.request(method, url, **kwargs)
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                self._logger.info(
                    "HTTP request completed",
                    method=method,
                    url=url,
                    status_code=response.status_code,
                    elapsed_ms=round(elapsed_ms, 2),
                    attempt=attempt + 1,
                )

                # Raise for error status codes
                response.raise_for_status()
                return response

            except Exception as exc:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                last_exception = exc

                # Check if we should retry
                if not _is_retryable_error(exc, self._retry_config):
                    self._logger.error(
                        "HTTP request failed (non-retryable)",
                        method=method,
                        url=url,
                        error=str(exc),
                        error_type=type(exc).__name__,
                        elapsed_ms=round(elapsed_ms, 2),
                        attempt=attempt + 1,
                    )
                    raise

                # Check if we have retries left
                if attempt >= self._retry_config.max_retries:
                    self._logger.error(
                        "HTTP request failed (retries exhausted)",
                        method=method,
                        url=url,
                        error=str(exc),
                        error_type=type(exc).__name__,
                        elapsed_ms=round(elapsed_ms, 2),
                        attempt=attempt + 1,
                        max_attempts=self._retry_config.max_retries + 1,
                    )
                    raise

                # Calculate delay and retry
                delay = _calculate_backoff_delay(
                    attempt,
                    self._retry_config.base_delay,
                    self._retry_config.max_delay,
                    self._retry_config.jitter_factor,
                )

                self._logger.warning(
                    "HTTP request failed (retrying)",
                    method=method,
                    url=url,
                    error=str(exc),
                    error_type=type(exc).__name__,
                    elapsed_ms=round(elapsed_ms, 2),
                    attempt=attempt + 1,
                    retry_delay_s=round(delay, 2),
                )

                # Use asyncio.sleep for async delay
                import asyncio

                await asyncio.sleep(delay)

        # This should never be reached, but satisfy type checker
        if last_exception is not None:
            raise last_exception
        raise RuntimeError("Unexpected state in retry loop")

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Make a GET request.

        Args:
            url: URL to request.
            **kwargs: Additional arguments passed to httpx.

        Returns:
            HTTP response object.
        """
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Make a POST request.

        Args:
            url: URL to request.
            **kwargs: Additional arguments passed to httpx.

        Returns:
            HTTP response object.
        """
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        """Make a PUT request.

        Args:
            url: URL to request.
            **kwargs: Additional arguments passed to httpx.

        Returns:
            HTTP response object.
        """
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        """Make a DELETE request.

        Args:
            url: URL to request.
            **kwargs: Additional arguments passed to httpx.

        Returns:
            HTTP response object.
        """
        return await self.request("DELETE", url, **kwargs)
