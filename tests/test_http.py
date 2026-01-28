"""Tests for HTTP client with retry logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from prediction_data.core.http import (
    HttpClient,
    RetryConfig,
    TimeoutConfig,
    _calculate_backoff_delay,
    _is_retryable_error,
)


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_values(self) -> None:
        """RetryConfig should have sensible defaults."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.jitter_factor == 0.1
        assert 429 in config.retry_status_codes
        assert 503 in config.retry_status_codes
        assert 500 in config.retry_status_codes
        assert 502 in config.retry_status_codes
        assert 504 in config.retry_status_codes

    def test_custom_values(self) -> None:
        """RetryConfig should accept custom values."""
        config = RetryConfig(
            max_retries=5,
            base_delay=2.0,
            max_delay=120.0,
            jitter_factor=0.2,
            retry_status_codes=frozenset({429, 503}),
        )
        assert config.max_retries == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 120.0
        assert config.jitter_factor == 0.2
        assert config.retry_status_codes == frozenset({429, 503})


class TestTimeoutConfig:
    """Tests for TimeoutConfig dataclass."""

    def test_default_values(self) -> None:
        """TimeoutConfig should have sensible defaults."""
        config = TimeoutConfig()
        assert config.connect == 10.0
        assert config.read == 30.0
        assert config.total == 60.0

    def test_custom_values(self) -> None:
        """TimeoutConfig should accept custom values."""
        config = TimeoutConfig(connect=5.0, read=15.0, total=30.0)
        assert config.connect == 5.0
        assert config.read == 15.0
        assert config.total == 30.0

    def test_to_httpx_timeout(self) -> None:
        """to_httpx_timeout should create valid httpx.Timeout."""
        config = TimeoutConfig(connect=5.0, read=15.0, total=30.0)
        timeout = config.to_httpx_timeout()
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.connect == 5.0
        assert timeout.read == 15.0


class TestCalculateBackoffDelay:
    """Tests for exponential backoff calculation."""

    def test_first_attempt_uses_base_delay(self) -> None:
        """First attempt should use approximately the base delay."""
        with patch("random.random", return_value=0.5):
            delay = _calculate_backoff_delay(
                attempt=0, base_delay=1.0, max_delay=60.0, jitter_factor=0.0
            )
            assert delay == 1.0

    def test_exponential_increase(self) -> None:
        """Delay should increase exponentially with each attempt."""
        with patch("random.random", return_value=0.5):
            delays = [
                _calculate_backoff_delay(
                    attempt=i, base_delay=1.0, max_delay=60.0, jitter_factor=0.0
                )
                for i in range(5)
            ]
            assert delays == [1.0, 2.0, 4.0, 8.0, 16.0]

    def test_respects_max_delay(self) -> None:
        """Delay should not exceed max_delay."""
        with patch("random.random", return_value=0.5):
            delay = _calculate_backoff_delay(
                attempt=10, base_delay=1.0, max_delay=30.0, jitter_factor=0.0
            )
            assert delay == 30.0

    def test_jitter_adds_variance(self) -> None:
        """Jitter should add variance to the delay."""
        # With random=0, jitter subtracts
        with patch("random.random", return_value=0.0):
            delay_low = _calculate_backoff_delay(
                attempt=0, base_delay=10.0, max_delay=60.0, jitter_factor=0.1
            )
            assert delay_low == 9.0  # 10 - (10 * 0.1 * 1)

        # With random=1, jitter adds
        with patch("random.random", return_value=1.0):
            delay_high = _calculate_backoff_delay(
                attempt=0, base_delay=10.0, max_delay=60.0, jitter_factor=0.1
            )
            assert delay_high == 11.0  # 10 + (10 * 0.1 * 1)

    def test_delay_never_negative(self) -> None:
        """Delay should never be negative even with large jitter."""
        with patch("random.random", return_value=0.0):
            delay = _calculate_backoff_delay(
                attempt=0, base_delay=1.0, max_delay=60.0, jitter_factor=2.0
            )
            assert delay >= 0


class TestIsRetryableError:
    """Tests for retryable error detection."""

    def test_connect_error_is_retryable(self) -> None:
        """Connection errors should be retryable."""
        config = RetryConfig()
        exc = httpx.ConnectError("Connection refused")
        assert _is_retryable_error(exc, config) is True

    def test_connect_timeout_is_retryable(self) -> None:
        """Connect timeout should be retryable."""
        config = RetryConfig()
        exc = httpx.ConnectTimeout("Connection timed out")
        assert _is_retryable_error(exc, config) is True

    def test_read_timeout_is_retryable(self) -> None:
        """Read timeout should be retryable."""
        config = RetryConfig()
        exc = httpx.ReadTimeout("Read timed out")
        assert _is_retryable_error(exc, config) is True

    def test_429_status_is_retryable(self) -> None:
        """429 Too Many Requests should be retryable."""
        config = RetryConfig()
        request = httpx.Request("GET", "https://example.com")
        response = httpx.Response(429, request=request)
        exc = httpx.HTTPStatusError("Rate limited", request=request, response=response)
        assert _is_retryable_error(exc, config) is True

    def test_503_status_is_retryable(self) -> None:
        """503 Service Unavailable should be retryable."""
        config = RetryConfig()
        request = httpx.Request("GET", "https://example.com")
        response = httpx.Response(503, request=request)
        exc = httpx.HTTPStatusError("Service unavailable", request=request, response=response)
        assert _is_retryable_error(exc, config) is True

    def test_500_status_is_retryable(self) -> None:
        """500 Internal Server Error should be retryable."""
        config = RetryConfig()
        request = httpx.Request("GET", "https://example.com")
        response = httpx.Response(500, request=request)
        exc = httpx.HTTPStatusError("Server error", request=request, response=response)
        assert _is_retryable_error(exc, config) is True

    def test_400_status_not_retryable(self) -> None:
        """400 Bad Request should NOT be retryable."""
        config = RetryConfig()
        request = httpx.Request("GET", "https://example.com")
        response = httpx.Response(400, request=request)
        exc = httpx.HTTPStatusError("Bad request", request=request, response=response)
        assert _is_retryable_error(exc, config) is False

    def test_404_status_not_retryable(self) -> None:
        """404 Not Found should NOT be retryable."""
        config = RetryConfig()
        request = httpx.Request("GET", "https://example.com")
        response = httpx.Response(404, request=request)
        exc = httpx.HTTPStatusError("Not found", request=request, response=response)
        assert _is_retryable_error(exc, config) is False

    def test_generic_exception_not_retryable(self) -> None:
        """Generic exceptions should NOT be retryable."""
        config = RetryConfig()
        exc = ValueError("Something went wrong")
        assert _is_retryable_error(exc, config) is False


def _create_mock_response(status_code: int, should_raise: bool = False) -> MagicMock:
    """Create a mock HTTP response."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    if should_raise:
        request = httpx.Request("GET", "https://example.com")
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}", request=request, response=httpx.Response(status_code, request=request)
        )
    return mock_response


class TestHttpClient:
    """Tests for HttpClient class."""

    @pytest.mark.asyncio
    async def test_requires_context_manager(self) -> None:
        """Client should require async context manager usage."""
        client = HttpClient()
        with pytest.raises(RuntimeError, match="must be used as async context manager"):
            await client.get("https://example.com")

    @pytest.mark.asyncio
    async def test_successful_get_request(self) -> None:
        """Successful GET request should return response."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = _create_mock_response(200)
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            async with HttpClient() as client:
                response = await client.get("/test")

            assert response.status_code == 200
            mock_client.request.assert_called_once_with("GET", "/test")

    @pytest.mark.asyncio
    async def test_successful_post_request(self) -> None:
        """Successful POST request should return response."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = _create_mock_response(201)
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            async with HttpClient() as client:
                response = await client.post("/test", json={"key": "value"})

            assert response.status_code == 201
            mock_client.request.assert_called_once_with("POST", "/test", json={"key": "value"})

    @pytest.mark.asyncio
    async def test_retries_on_503(self) -> None:
        """Client should retry on 503 status code."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()

            # First call fails with 503, second succeeds
            error_response = _create_mock_response(503, should_raise=True)
            success_response = _create_mock_response(200)

            mock_client.request = AsyncMock(side_effect=[error_response, success_response])
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            with patch("asyncio.sleep", new_callable=AsyncMock):
                async with HttpClient(retry_config=RetryConfig(max_retries=3)) as client:
                    response = await client.get("/test")

            assert response.status_code == 200
            assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_connection_error(self) -> None:
        """Client should retry on connection errors."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()

            # First call fails with connection error, second succeeds
            success_response = _create_mock_response(200)

            mock_client.request = AsyncMock(
                side_effect=[httpx.ConnectError("Connection refused"), success_response]
            )
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            with patch("asyncio.sleep", new_callable=AsyncMock):
                async with HttpClient(retry_config=RetryConfig(max_retries=3)) as client:
                    response = await client.get("/test")

            assert response.status_code == 200
            assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_exhausts_retries(self) -> None:
        """Client should raise after exhausting retries."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()

            # Always fail with 503
            error_response = _create_mock_response(503, should_raise=True)
            mock_client.request = AsyncMock(return_value=error_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(httpx.HTTPStatusError):
                    async with HttpClient(retry_config=RetryConfig(max_retries=2)) as client:
                        await client.get("/test")

            # Initial attempt + 2 retries = 3 calls
            assert mock_client.request.call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_400(self) -> None:
        """Client should NOT retry on 400 status code."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()

            error_response = _create_mock_response(400, should_raise=True)
            mock_client.request = AsyncMock(return_value=error_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            with pytest.raises(httpx.HTTPStatusError):
                async with HttpClient(retry_config=RetryConfig(max_retries=3)) as client:
                    await client.get("/test")

            # Should only be called once - no retries
            assert mock_client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_base_url_configuration(self) -> None:
        """Client should use configured base_url."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = _create_mock_response(200)
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            async with HttpClient(base_url="https://api.example.com") as client:
                await client.get("/endpoint")

            mock_client_class.assert_called_once()
            call_kwargs = mock_client_class.call_args.kwargs
            assert call_kwargs["base_url"] == "https://api.example.com"

    @pytest.mark.asyncio
    async def test_custom_headers(self) -> None:
        """Client should use configured headers."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = _create_mock_response(200)
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            headers = {"Authorization": "Bearer token123", "X-Custom": "value"}
            async with HttpClient(headers=headers) as client:
                await client.get("/endpoint")

            mock_client_class.assert_called_once()
            call_kwargs = mock_client_class.call_args.kwargs
            assert call_kwargs["headers"] == headers

    @pytest.mark.asyncio
    async def test_put_request(self) -> None:
        """PUT request should work correctly."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = _create_mock_response(200)
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            async with HttpClient() as client:
                response = await client.put("/test", json={"updated": True})

            assert response.status_code == 200
            mock_client.request.assert_called_once_with("PUT", "/test", json={"updated": True})

    @pytest.mark.asyncio
    async def test_delete_request(self) -> None:
        """DELETE request should work correctly."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = _create_mock_response(204)
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            async with HttpClient() as client:
                response = await client.delete("/test/123")

            assert response.status_code == 204
            mock_client.request.assert_called_once_with("DELETE", "/test/123")

    @pytest.mark.asyncio
    async def test_timeout_configuration(self) -> None:
        """Client should use configured timeouts."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = _create_mock_response(200)
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            timeout_config = TimeoutConfig(connect=5.0, read=15.0, total=30.0)
            async with HttpClient(timeout_config=timeout_config) as client:
                await client.get("/endpoint")

            mock_client_class.assert_called_once()
            call_kwargs = mock_client_class.call_args.kwargs
            timeout = call_kwargs["timeout"]
            assert timeout.connect == 5.0
            assert timeout.read == 15.0


class TestHttpClientRetryDelay:
    """Tests for retry delay behavior."""

    @pytest.mark.asyncio
    async def test_uses_exponential_backoff(self) -> None:
        """Client should use exponential backoff between retries."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()

            # Always fail with 503
            error_response = _create_mock_response(503, should_raise=True)
            mock_client.request = AsyncMock(return_value=error_response)
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            sleep_delays: list[float] = []

            async def capture_sleep(delay: float) -> None:
                sleep_delays.append(delay)

            with patch("asyncio.sleep", side_effect=capture_sleep):
                with patch("random.random", return_value=0.5):  # No jitter
                    with pytest.raises(httpx.HTTPStatusError):
                        async with HttpClient(
                            retry_config=RetryConfig(
                                max_retries=3, base_delay=1.0, jitter_factor=0.0
                            )
                        ) as client:
                            await client.get("/test")

            # Should have 3 sleeps (before each retry)
            assert len(sleep_delays) == 3
            # Delays should be 1, 2, 4 (exponential)
            assert sleep_delays == [1.0, 2.0, 4.0]
