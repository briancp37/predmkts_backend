"""Tests for the `gold freshness` CLI command."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from prediction_data.cli.gold import app

runner = CliRunner()


class TestFreshnessCli:
    """Tests for `prediction-data gold freshness`."""

    @patch("prediction_data.gold.clickhouse.get_client")
    @patch("prediction_data.gold.ops_metadata.check_freshness")
    def test_displays_freshness_data(
        self, mock_check: MagicMock, _mock_client: MagicMock
    ) -> None:
        """Verify freshness CLI displays tabular output with expected columns."""
        mock_check.return_value = [
            {
                "dataset": "market_mark_daily",
                "state": "fresh",
                "actual_lag_seconds": 150,
                "expected_lag_seconds": 300,
                "last_success_at": datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
                "last_run_id": "abc123",
            },
            {
                "dataset": "wallet_pnl_daily",
                "state": "stale",
                "actual_lag_seconds": 800,
                "expected_lag_seconds": 600,
                "last_success_at": datetime(2024, 6, 15, 11, 50, 0, tzinfo=UTC),
                "last_run_id": "def456",
            },
        ]

        result = runner.invoke(app, ["freshness"])

        assert result.exit_code == 0
        # Check header row
        assert "Dataset" in result.output
        assert "State" in result.output
        assert "Lag" in result.output
        assert "SLA" in result.output
        assert "Last Success" in result.output

        # Check data rows
        assert "market_mark_daily" in result.output
        assert "fresh" in result.output
        assert "150" in result.output
        assert "300" in result.output

        assert "wallet_pnl_daily" in result.output
        assert "stale" in result.output
        assert "800" in result.output
        assert "600" in result.output

    @patch("prediction_data.gold.clickhouse.get_client")
    @patch("prediction_data.gold.ops_metadata.check_freshness")
    def test_empty_freshness_data(
        self, mock_check: MagicMock, _mock_client: MagicMock
    ) -> None:
        """Verify message when no freshness data recorded yet."""
        mock_check.return_value = []

        result = runner.invoke(app, ["freshness"])

        assert result.exit_code == 0
        assert "No freshness data recorded yet" in result.output

    @patch("prediction_data.gold.clickhouse.get_client")
    @patch("prediction_data.gold.ops_metadata.check_freshness")
    def test_handles_missing_last_success(
        self, mock_check: MagicMock, _mock_client: MagicMock
    ) -> None:
        """Verify CLI handles None last_success_at gracefully."""
        mock_check.return_value = [
            {
                "dataset": "market_mark_daily",
                "state": "broken",
                "actual_lag_seconds": 0,
                "expected_lag_seconds": 300,
                "last_success_at": None,
                "last_run_id": None,
            },
        ]

        result = runner.invoke(app, ["freshness"])

        assert result.exit_code == 0
        assert "market_mark_daily" in result.output
        assert "broken" in result.output
        # The — placeholder for missing timestamp
        assert "—" in result.output

    @patch("prediction_data.gold.clickhouse.get_client")
    @patch("prediction_data.gold.ops_metadata.check_freshness")
    def test_output_format_alignment(
        self, mock_check: MagicMock, _mock_client: MagicMock
    ) -> None:
        """Verify output columns are properly aligned with padding."""
        mock_check.return_value = [
            {
                "dataset": "market_mark_daily",
                "state": "fresh",
                "actual_lag_seconds": 100,
                "expected_lag_seconds": 300,
                "last_success_at": datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
                "last_run_id": "r1",
            },
            {
                "dataset": "wallet_position_snapshot_daily",
                "state": "broken",
                "actual_lag_seconds": 2000,
                "expected_lag_seconds": 900,
                "last_success_at": datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC),
                "last_run_id": "r2",
            },
        ]

        result = runner.invoke(app, ["freshness"])

        assert result.exit_code == 0
        lines = result.output.strip().split("\n")

        # Should have header, separator, and 2 data rows
        assert len(lines) == 4

        # Check separator line exists (made of dashes)
        assert "---" in lines[1]

        # All data lines should contain the timestamp format (YYYY-MM-DD HH:MM:SS)
        assert "2024-06-15 12:00:00" in lines[2]
        assert "2024-06-15 10:00:00" in lines[3]
