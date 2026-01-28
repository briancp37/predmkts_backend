"""Tests for run ID generation and RunContext."""

import re
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import structlog

from prediction_data.core.run import RunContext, _generate_run_id


class TestGenerateRunId:
    """Tests for run_id generation."""

    def test_generates_valid_uuid4(self) -> None:
        """Run ID should be a valid UUID4 string."""
        run_id = _generate_run_id()
        uuid4_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
            re.IGNORECASE,
        )
        assert uuid4_pattern.match(run_id), f"Invalid UUID4 format: {run_id}"

    def test_generates_unique_ids(self) -> None:
        """Each call should generate a unique run_id."""
        run_ids = [_generate_run_id() for _ in range(100)]
        assert len(set(run_ids)) == 100, "Generated duplicate run_ids"


class TestRunContext:
    """Tests for RunContext dataclass."""

    def test_creates_with_required_fields(self) -> None:
        """RunContext should be created with platform and entity."""
        ctx = RunContext(platform="polymarket", entity="markets")
        assert ctx.platform == "polymarket"
        assert ctx.entity == "markets"
        assert ctx.run_id is not None
        assert ctx.start_time is not None
        assert ctx.end_time is None

    def test_auto_generates_run_id(self) -> None:
        """RunContext should auto-generate a UUID4 run_id."""
        ctx = RunContext(platform="kalshi", entity="trades")
        uuid4_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
            re.IGNORECASE,
        )
        assert uuid4_pattern.match(ctx.run_id)

    def test_auto_generates_start_time(self) -> None:
        """RunContext should auto-generate start_time in UTC."""
        before = datetime.now(timezone.utc)
        ctx = RunContext(platform="polymarket", entity="markets")
        after = datetime.now(timezone.utc)
        assert before <= ctx.start_time <= after
        assert ctx.start_time.tzinfo == timezone.utc

    def test_allows_custom_run_id(self) -> None:
        """RunContext should accept a custom run_id."""
        custom_id = "custom-run-id-12345"
        ctx = RunContext(platform="polymarket", entity="markets", run_id=custom_id)
        assert ctx.run_id == custom_id


class TestRunContextS3KeyPrefix:
    """Tests for S3 key prefix formatting."""

    def test_format_s3_key_prefix(self) -> None:
        """Should format S3 key prefix correctly."""
        ctx = RunContext(
            platform="polymarket",
            entity="markets",
            run_id="abc-123-def-456",
        )
        prefix = ctx.format_s3_key_prefix("2024-01-15")
        assert prefix == "bronze/polymarket/markets/dt=2024-01-15/run_id=abc-123-def-456/"

    def test_format_s3_key_prefix_different_platform(self) -> None:
        """Should work with different platforms."""
        ctx = RunContext(
            platform="kalshi",
            entity="trades",
            run_id="xyz-789",
        )
        prefix = ctx.format_s3_key_prefix("2024-06-30")
        assert prefix == "bronze/kalshi/trades/dt=2024-06-30/run_id=xyz-789/"


class TestRunContextTimestamps:
    """Tests for run start/end timestamp tracking."""

    def test_mark_complete_sets_end_time(self) -> None:
        """mark_complete should set end_time."""
        ctx = RunContext(platform="polymarket", entity="markets")
        assert ctx.end_time is None
        ctx.mark_complete()
        assert ctx.end_time is not None
        assert ctx.end_time.tzinfo == timezone.utc

    def test_duration_seconds_none_when_running(self) -> None:
        """duration_seconds should be None when run is still active."""
        ctx = RunContext(platform="polymarket", entity="markets")
        assert ctx.duration_seconds is None

    def test_duration_seconds_after_complete(self) -> None:
        """duration_seconds should return elapsed time after completion."""
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 12, 5, 30, tzinfo=timezone.utc)
        ctx = RunContext(platform="polymarket", entity="markets", start_time=start)
        ctx.end_time = end
        assert ctx.duration_seconds == 330.0  # 5 minutes 30 seconds


class TestRunContextLogging:
    """Tests for structlog binding."""

    def test_bind_to_logger_binds_context(self) -> None:
        """bind_to_logger should bind context to structlog."""
        ctx = RunContext(
            platform="polymarket",
            entity="markets",
            run_id="test-run-id",
        )
        with patch("prediction_data.core.run.bind_context") as mock_bind:
            ctx.bind_to_logger(dt="2024-01-15")
            mock_bind.assert_called_once_with(
                platform="polymarket",
                entity="markets",
                run_id="test-run-id",
                dt="2024-01-15",
            )

    def test_bind_to_logger_without_dt(self) -> None:
        """bind_to_logger should work without dt."""
        ctx = RunContext(
            platform="kalshi",
            entity="trades",
            run_id="another-run-id",
        )
        with patch("prediction_data.core.run.bind_context") as mock_bind:
            ctx.bind_to_logger()
            mock_bind.assert_called_once_with(
                platform="kalshi",
                entity="trades",
                run_id="another-run-id",
                dt=None,
            )

    def test_log_start(self) -> None:
        """log_start should log run start info."""
        ctx = RunContext(
            platform="polymarket",
            entity="markets",
            run_id="log-test-run",
        )
        mock_logger = structlog.testing.CapturingLogger()
        ctx.log_start(logger=mock_logger)  # type: ignore[arg-type]
        assert len(mock_logger.calls) == 1
        call = mock_logger.calls[0]
        assert call.method_name == "info"
        assert call.args == ("Run started",)
        assert call.kwargs["run_id"] == "log-test-run"
        assert call.kwargs["platform"] == "polymarket"
        assert call.kwargs["entity"] == "markets"

    def test_log_end(self) -> None:
        """log_end should log run completion info."""
        ctx = RunContext(
            platform="polymarket",
            entity="markets",
            run_id="log-test-run",
        )
        ctx.mark_complete()
        mock_logger = structlog.testing.CapturingLogger()
        ctx.log_end(logger=mock_logger)  # type: ignore[arg-type]
        assert len(mock_logger.calls) == 1
        call = mock_logger.calls[0]
        assert call.method_name == "info"
        assert call.args == ("Run completed",)
        assert call.kwargs["run_id"] == "log-test-run"
        assert call.kwargs["duration_seconds"] is not None
