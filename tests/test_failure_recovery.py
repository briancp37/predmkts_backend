"""Failure recovery tests for the ingestion pipeline.

These tests validate that:
- API failures propagate as exceptions (non-zero exit codes)
- Network timeouts are handled gracefully
- Failed runs do not write partial data to S3
- Retries produce new run_ids (no data corruption)
- HTTP retry logic works correctly for retryable vs non-retryable errors
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from prediction_data.bronze.polymarket.ingest import (
    ingest_trades as poly_ingest_trades,
)
from prediction_data.core.http import (
    HttpClient,
    RetryConfig,
    TimeoutConfig,
    _calculate_backoff_delay,
    _is_retryable_error,
)
from prediction_data.storage.s3 import S3Client as RealS3Client


# --- Helpers ---

SAMPLE_TRADES = [
    {"id": "t1", "side": "BUY", "size": "10", "price": "0.55", "condition_id": "0xabc"},
]


class FakeS3Client:
    """Captures all S3 put_object calls for validation."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, Bucket: str, Key: str, Body: bytes, **kwargs) -> None:
        self.objects[Key] = Body


class FailingS3Client:
    """S3 client that raises on put_object."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def put_object(self, **kwargs) -> None:
        raise self._error


# --- API Failure Tests ---


class TestAPIFailurePropagation:
    """Verify that API failures propagate as exceptions."""

    @pytest.mark.asyncio
    async def test_api_error_raises_exception(self) -> None:
        """An API error during fetch should propagate and prevent S3 writes."""
        fake_s3 = FakeS3Client()

        with (
            patch(
                "prediction_data.bronze.polymarket.ingest.PolymarketClient"
            ) as MockClient,
            patch(
                "prediction_data.bronze.polymarket.ingest.S3Client"
            ) as MockS3,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(bronze_bucket="test-bucket")

            client_instance = AsyncMock()
            client_instance.fetch_trades.side_effect = httpx.HTTPStatusError(
                "Server Error",
                request=httpx.Request("GET", "https://api.example.com"),
                response=httpx.Response(500),
            )
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            MockS3.return_value = RealS3Client(bucket="test-bucket", s3_client=fake_s3)

            with pytest.raises(httpx.HTTPStatusError):
                await poly_ingest_trades(dt="2026-01-28")

        # No data should have been written to S3
        assert len(fake_s3.objects) == 0

    @pytest.mark.asyncio
    async def test_connection_error_raises_exception(self) -> None:
        """A network connection error should propagate."""
        with (
            patch(
                "prediction_data.bronze.polymarket.ingest.PolymarketClient"
            ) as MockClient,
            patch(
                "prediction_data.bronze.polymarket.ingest.S3Client"
            ) as MockS3,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(bronze_bucket="test-bucket")

            client_instance = AsyncMock()
            client_instance.fetch_trades.side_effect = httpx.ConnectError(
                "Connection refused"
            )
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            MockS3.return_value = RealS3Client(bucket="test-bucket", s3_client=FakeS3Client())

            with pytest.raises(httpx.ConnectError):
                await poly_ingest_trades(dt="2026-01-28")

    @pytest.mark.asyncio
    async def test_timeout_error_raises_exception(self) -> None:
        """A timeout error should propagate."""
        with (
            patch(
                "prediction_data.bronze.polymarket.ingest.PolymarketClient"
            ) as MockClient,
            patch(
                "prediction_data.bronze.polymarket.ingest.S3Client"
            ) as MockS3,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(bronze_bucket="test-bucket")

            client_instance = AsyncMock()
            client_instance.fetch_trades.side_effect = httpx.ReadTimeout(
                "Read timed out"
            )
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            MockS3.return_value = RealS3Client(bucket="test-bucket", s3_client=FakeS3Client())

            with pytest.raises(httpx.ReadTimeout):
                await poly_ingest_trades(dt="2026-01-28")


# --- S3 Failure Tests ---


class TestS3FailurePropagation:
    """Verify that S3 upload failures propagate correctly."""

    @pytest.mark.asyncio
    async def test_s3_upload_failure_raises_exception(self) -> None:
        """An S3 upload failure should propagate and not leave partial state."""
        with (
            patch(
                "prediction_data.bronze.polymarket.ingest.PolymarketClient"
            ) as MockClient,
            patch(
                "prediction_data.bronze.polymarket.ingest.S3Client"
            ) as MockS3,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(bronze_bucket="test-bucket")

            client_instance = AsyncMock()
            client_instance.fetch_trades.return_value = (SAMPLE_TRADES, False)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            failing_s3 = FailingS3Client(Exception("S3 PutObject failed"))
            MockS3.return_value = RealS3Client(bucket="test-bucket", s3_client=failing_s3)

            with pytest.raises(Exception, match="S3 PutObject failed"):
                await poly_ingest_trades(dt="2026-01-28")


# --- Retry Logic Unit Tests ---


class TestRetryableErrorClassification:
    """Verify retryable vs non-retryable error classification."""

    def test_connect_error_is_retryable(self) -> None:
        exc = httpx.ConnectError("Connection refused")
        assert _is_retryable_error(exc, RetryConfig()) is True

    def test_connect_timeout_is_retryable(self) -> None:
        exc = httpx.ConnectTimeout("Timed out")
        assert _is_retryable_error(exc, RetryConfig()) is True

    def test_read_timeout_is_retryable(self) -> None:
        exc = httpx.ReadTimeout("Read timed out")
        assert _is_retryable_error(exc, RetryConfig()) is True

    def test_429_is_retryable(self) -> None:
        exc = httpx.HTTPStatusError(
            "Rate limited",
            request=httpx.Request("GET", "https://example.com"),
            response=httpx.Response(429),
        )
        assert _is_retryable_error(exc, RetryConfig()) is True

    def test_500_is_retryable(self) -> None:
        exc = httpx.HTTPStatusError(
            "Server error",
            request=httpx.Request("GET", "https://example.com"),
            response=httpx.Response(500),
        )
        assert _is_retryable_error(exc, RetryConfig()) is True

    def test_502_is_retryable(self) -> None:
        exc = httpx.HTTPStatusError(
            "Bad gateway",
            request=httpx.Request("GET", "https://example.com"),
            response=httpx.Response(502),
        )
        assert _is_retryable_error(exc, RetryConfig()) is True

    def test_400_is_not_retryable(self) -> None:
        exc = httpx.HTTPStatusError(
            "Bad request",
            request=httpx.Request("GET", "https://example.com"),
            response=httpx.Response(400),
        )
        assert _is_retryable_error(exc, RetryConfig()) is False

    def test_404_is_not_retryable(self) -> None:
        exc = httpx.HTTPStatusError(
            "Not found",
            request=httpx.Request("GET", "https://example.com"),
            response=httpx.Response(404),
        )
        assert _is_retryable_error(exc, RetryConfig()) is False

    def test_generic_exception_is_not_retryable(self) -> None:
        exc = ValueError("bad value")
        assert _is_retryable_error(exc, RetryConfig()) is False


class TestBackoffDelay:
    """Verify exponential backoff calculation."""

    def test_first_attempt_uses_base_delay(self) -> None:
        delay = _calculate_backoff_delay(0, base_delay=1.0, max_delay=60.0, jitter_factor=0.0)
        assert delay == 1.0

    def test_second_attempt_doubles(self) -> None:
        delay = _calculate_backoff_delay(1, base_delay=1.0, max_delay=60.0, jitter_factor=0.0)
        assert delay == 2.0

    def test_third_attempt_quadruples(self) -> None:
        delay = _calculate_backoff_delay(2, base_delay=1.0, max_delay=60.0, jitter_factor=0.0)
        assert delay == 4.0

    def test_delay_capped_at_max(self) -> None:
        delay = _calculate_backoff_delay(10, base_delay=1.0, max_delay=60.0, jitter_factor=0.0)
        assert delay == 60.0

    def test_jitter_adds_variance(self) -> None:
        delays = set()
        for _ in range(20):
            d = _calculate_backoff_delay(0, base_delay=1.0, max_delay=60.0, jitter_factor=0.5)
            delays.add(round(d, 4))
        # With jitter, we should get multiple distinct values
        assert len(delays) > 1


# --- Retry Creates New Run IDs ---


class TestRetryRunIdIsolation:
    """Verify that retried runs create new run_ids (no data corruption)."""

    @pytest.mark.asyncio
    async def test_failed_then_successful_run_gets_new_run_id(self) -> None:
        """A retry after failure must produce a different run_id."""
        run_ids = []

        # First run: fails
        with (
            patch(
                "prediction_data.bronze.polymarket.ingest.PolymarketClient"
            ) as MockClient,
            patch(
                "prediction_data.bronze.polymarket.ingest.S3Client"
            ) as MockS3,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(bronze_bucket="test-bucket")

            client_instance = AsyncMock()
            client_instance.fetch_trades.side_effect = httpx.ConnectError("fail")
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            MockS3.return_value = RealS3Client(bucket="test-bucket", s3_client=FakeS3Client())

            with pytest.raises(httpx.ConnectError):
                await poly_ingest_trades(dt="2026-01-28")
            # No run_id from failed run

        # Second run: succeeds
        fake_s3 = FakeS3Client()
        with (
            patch(
                "prediction_data.bronze.polymarket.ingest.PolymarketClient"
            ) as MockClient,
            patch(
                "prediction_data.bronze.polymarket.ingest.S3Client"
            ) as MockS3,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(bronze_bucket="test-bucket")

            client_instance = AsyncMock()
            client_instance.fetch_trades.return_value = (SAMPLE_TRADES, False)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            MockS3.return_value = RealS3Client(bucket="test-bucket", s3_client=fake_s3)

            run_id = await poly_ingest_trades(dt="2026-01-28")
            run_ids.append(run_id)

        # Third run: also succeeds (different run_id)
        fake_s3_2 = FakeS3Client()
        with (
            patch(
                "prediction_data.bronze.polymarket.ingest.PolymarketClient"
            ) as MockClient,
            patch(
                "prediction_data.bronze.polymarket.ingest.S3Client"
            ) as MockS3,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(bronze_bucket="test-bucket")

            client_instance = AsyncMock()
            client_instance.fetch_trades.return_value = (SAMPLE_TRADES, False)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            MockS3.return_value = RealS3Client(bucket="test-bucket", s3_client=fake_s3_2)

            run_id = await poly_ingest_trades(dt="2026-01-28")
            run_ids.append(run_id)

        # All successful run_ids must be unique
        assert len(set(run_ids)) == 2, f"Run IDs not unique: {run_ids}"

        # Each run wrote to different S3 paths (different run_ids in keys)
        keys_1 = set(fake_s3.objects.keys())
        keys_2 = set(fake_s3_2.objects.keys())
        assert keys_1.isdisjoint(keys_2), "Retry overwrote existing data"


# --- CLI Exit Code Tests ---


class TestCLIExitCodes:
    """Verify CLI commands produce non-zero exit codes on failure."""

    def test_cli_returns_exit_code_1_on_api_failure(self) -> None:
        """CLI should exit with code 1 when ingestion fails."""
        from typer.testing import CliRunner

        from prediction_data.cli.main import app

        runner = CliRunner()

        with (
            patch(
                "prediction_data.bronze.polymarket.ingest.PolymarketClient"
            ) as MockClient,
            patch("prediction_data.bronze.polymarket.ingest.S3Client"),
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(bronze_bucket="test-bucket")

            client_instance = AsyncMock()
            client_instance.fetch_trades.side_effect = httpx.ConnectError("fail")
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = runner.invoke(app, ["ingest", "polymarket-trades", "--dt", "2026-01-28"])

        assert result.exit_code == 1

    def test_cli_returns_exit_code_0_on_success(self) -> None:
        """CLI should exit with code 0 when ingestion succeeds."""
        from typer.testing import CliRunner

        from prediction_data.cli.main import app

        runner = CliRunner()

        with (
            patch(
                "prediction_data.bronze.polymarket.ingest.PolymarketClient"
            ) as MockClient,
            patch(
                "prediction_data.bronze.polymarket.ingest.S3Client"
            ) as MockS3,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(bronze_bucket="test-bucket")

            client_instance = AsyncMock()
            client_instance.fetch_trades.return_value = (SAMPLE_TRADES, False)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            MockS3.return_value = RealS3Client(bucket="test-bucket", s3_client=FakeS3Client())

            result = runner.invoke(app, ["ingest", "polymarket-trades", "--dt", "2026-01-28"])

        assert result.exit_code == 0
