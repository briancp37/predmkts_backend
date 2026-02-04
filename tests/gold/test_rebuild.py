"""Tests for the `gold rebuild` CLI command."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, call, patch

from typer.testing import CliRunner

from prediction_data.cli.gold import app

runner = CliRunner()


class TestRebuildCli:
    """Tests for `prediction-data gold rebuild`."""

    def test_help(self) -> None:
        result = runner.invoke(app, ["rebuild", "--help"])
        assert result.exit_code == 0
        assert "--table" in result.output
        assert "--start-date" in result.output
        assert "--end-date" in result.output
        assert "--force" in result.output
        assert "--dry-run" in result.output

    @patch("prediction_data.cli.gold.get_settings")
    def test_unknown_table_error(self, mock_settings: MagicMock) -> None:
        mock_settings.return_value.gold_bucket = "test-gold"
        result = runner.invoke(
            app,
            [
                "rebuild",
                "--table",
                "bogus_table",
                "--start-date",
                "2024-06-01",
                "--end-date",
                "2024-06-03",
            ],
        )
        assert result.exit_code == 1
        assert "unknown table" in result.output.lower()

    @patch("prediction_data.cli.gold.get_settings")
    def test_start_after_end_error(self, mock_settings: MagicMock) -> None:
        mock_settings.return_value.gold_bucket = "test-gold"
        result = runner.invoke(
            app,
            [
                "rebuild",
                "--table",
                "market_mark_daily",
                "--start-date",
                "2024-06-10",
                "--end-date",
                "2024-06-01",
            ],
        )
        assert result.exit_code == 1
        assert "--start-date must be <= --end-date" in result.output

    @patch("prediction_data.cli.gold._rebuild_day")
    @patch("prediction_data.cli.gold.get_settings")
    def test_dry_run_single_day(
        self,
        mock_settings: MagicMock,
        mock_rebuild: MagicMock,
    ) -> None:
        mock_settings.return_value.gold_bucket = "test-gold"
        mock_rebuild.return_value = 42

        result = runner.invoke(
            app,
            [
                "rebuild",
                "--table",
                "market_mark_daily",
                "--start-date",
                "2024-06-15",
                "--end-date",
                "2024-06-15",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "42 rows" in result.output
        assert "[dry-run]" in result.output
        mock_rebuild.assert_called_once_with(
            "market_mark_daily",
            date(2024, 6, 15),
            gold_bucket="test-gold",
            dry_run=True,
        )

    @patch("prediction_data.cli.gold._rebuild_day")
    @patch("prediction_data.cli.gold.get_settings")
    def test_date_range_processes_all_days(
        self,
        mock_settings: MagicMock,
        mock_rebuild: MagicMock,
    ) -> None:
        mock_settings.return_value.gold_bucket = "test-gold"
        mock_rebuild.return_value = 10

        result = runner.invoke(
            app,
            [
                "rebuild",
                "--table",
                "market_mark_daily",
                "--start-date",
                "2024-06-01",
                "--end-date",
                "2024-06-03",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert mock_rebuild.call_count == 3
        assert "Total rows: 30" in result.output
        assert "Days processed: 3/3" in result.output

        # Verify dates are in chronological order.
        called_dates = [c.args[1] for c in mock_rebuild.call_args_list]
        assert called_dates == [date(2024, 6, 1), date(2024, 6, 2), date(2024, 6, 3)]

    @patch("prediction_data.cli.gold._rebuild_day")
    @patch("prediction_data.cli.gold.get_settings")
    def test_failure_continues_and_reports(
        self,
        mock_settings: MagicMock,
        mock_rebuild: MagicMock,
    ) -> None:
        """Rebuild continues on failure and reports summary."""
        mock_settings.return_value.gold_bucket = "test-gold"

        def side_effect(table: str, dt: date, **kw: object) -> int:
            if dt == date(2024, 6, 2):
                raise RuntimeError("Silver data missing")
            return 10

        mock_rebuild.side_effect = side_effect

        result = runner.invoke(
            app,
            [
                "rebuild",
                "--table",
                "market_mark_daily",
                "--start-date",
                "2024-06-01",
                "--end-date",
                "2024-06-03",
                "--dry-run",
            ],
        )

        assert result.exit_code == 1
        # All 3 days attempted.
        assert mock_rebuild.call_count == 3
        assert "FAILED" in result.output
        assert "Failed: 1" in result.output
        assert "Days processed: 2/3" in result.output
        assert "Total rows: 20" in result.output

    @patch("prediction_data.cli.gold._gold_partition_exists")
    @patch("prediction_data.cli.gold._rebuild_day")
    @patch("prediction_data.cli.gold.get_settings")
    @patch("boto3.client")
    def test_skips_existing_without_force(
        self,
        mock_boto3_client: MagicMock,
        mock_settings: MagicMock,
        mock_rebuild: MagicMock,
        mock_exists: MagicMock,
    ) -> None:
        """Without --force, existing partitions are skipped."""
        mock_settings.return_value.gold_bucket = "test-gold"
        mock_rebuild.return_value = 10
        mock_boto3_client.return_value = MagicMock()

        # Day 2 exists, days 1 and 3 do not.
        def exists_side_effect(
            s3: object, bucket: str, table: str, day: str
        ) -> bool:
            return day == "2024-06-02"

        mock_exists.side_effect = exists_side_effect

        result = runner.invoke(
            app,
            [
                "rebuild",
                "--table",
                "market_mark_daily",
                "--start-date",
                "2024-06-01",
                "--end-date",
                "2024-06-03",
            ],
        )

        assert result.exit_code == 0
        # Only 2 days rebuilt, 1 skipped.
        assert mock_rebuild.call_count == 2
        assert "skipped (exists)" in result.output
        assert "Skipped (already exist): 1" in result.output
        assert "Days processed: 2/3" in result.output

    @patch("prediction_data.cli.gold._gold_partition_exists")
    @patch("prediction_data.cli.gold._rebuild_day")
    @patch("prediction_data.cli.gold.get_settings")
    def test_force_overwrites_existing(
        self,
        mock_settings: MagicMock,
        mock_rebuild: MagicMock,
        mock_exists: MagicMock,
    ) -> None:
        """With --force, existing partitions are overwritten."""
        mock_settings.return_value.gold_bucket = "test-gold"
        mock_rebuild.return_value = 10

        result = runner.invoke(
            app,
            [
                "rebuild",
                "--table",
                "market_mark_daily",
                "--start-date",
                "2024-06-01",
                "--end-date",
                "2024-06-03",
                "--force",
            ],
        )

        assert result.exit_code == 0
        # All 3 days processed, existence check never called.
        assert mock_rebuild.call_count == 3
        mock_exists.assert_not_called()
        assert "Days processed: 3/3" in result.output
        assert "[force]" in result.output

    @patch("prediction_data.cli.gold._rebuild_day")
    @patch("prediction_data.cli.gold.get_settings")
    def test_cumulative_table_shows_sequential_note(
        self,
        mock_settings: MagicMock,
        mock_rebuild: MagicMock,
    ) -> None:
        mock_settings.return_value.gold_bucket = "test-gold"
        mock_rebuild.return_value = 5

        result = runner.invoke(
            app,
            [
                "rebuild",
                "--table",
                "wallet_pnl_daily",
                "--start-date",
                "2024-06-01",
                "--end-date",
                "2024-06-01",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "cumulative" in result.output.lower()

    @patch("prediction_data.cli.gold._rebuild_day")
    @patch("prediction_data.cli.gold.get_settings")
    def test_wallet_mtm_shows_dependency_note(
        self,
        mock_settings: MagicMock,
        mock_rebuild: MagicMock,
    ) -> None:
        mock_settings.return_value.gold_bucket = "test-gold"
        mock_rebuild.return_value = 5

        result = runner.invoke(
            app,
            [
                "rebuild",
                "--table",
                "wallet_mtm_daily",
                "--start-date",
                "2024-06-01",
                "--end-date",
                "2024-06-01",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "depends on market marks" in result.output.lower()

    @patch("prediction_data.cli.gold._rebuild_day")
    @patch("prediction_data.cli.gold.get_settings")
    def test_wallet_pnl_shows_ledger_dependency_note(
        self,
        mock_settings: MagicMock,
        mock_rebuild: MagicMock,
    ) -> None:
        mock_settings.return_value.gold_bucket = "test-gold"
        mock_rebuild.return_value = 5

        result = runner.invoke(
            app,
            [
                "rebuild",
                "--table",
                "wallet_pnl_daily",
                "--start-date",
                "2024-06-01",
                "--end-date",
                "2024-06-01",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "wallet_position_ledger" in result.output


class TestRebuildDay:
    """Unit tests for _rebuild_day dispatch function."""

    @patch("prediction_data.gold.market_marks.compute_market_marks", return_value=42)
    def test_market_mark_daily(self, mock_marks: MagicMock) -> None:
        from prediction_data.cli.gold import _rebuild_day

        rows = _rebuild_day(
            "market_mark_daily",
            date(2024, 6, 15),
            gold_bucket="test-gold",
            dry_run=True,
        )
        assert rows == 42
        mock_marks.assert_called_once_with(
            platform="polymarket",
            dt=date(2024, 6, 15),
            gold_bucket="test-gold",
            dry_run=True,
        )

    @patch("prediction_data.gold.wallet_pnl.compute_wallet_pnl", return_value=7)
    def test_wallet_pnl_daily(self, mock_pnl: MagicMock) -> None:
        from prediction_data.cli.gold import _rebuild_day

        rows = _rebuild_day(
            "wallet_pnl_daily",
            date(2024, 6, 15),
            gold_bucket="test-gold",
            dry_run=True,
        )
        assert rows == 7
        mock_pnl.assert_called_once_with(
            dt=date(2024, 6, 15),
            gold_bucket="test-gold",
            dry_run=True,
        )

    @patch("prediction_data.gold.wallet_mtm.compute_wallet_mtm", return_value=3)
    def test_wallet_mtm_daily(self, mock_mtm: MagicMock) -> None:
        from prediction_data.cli.gold import _rebuild_day

        rows = _rebuild_day(
            "wallet_mtm_daily",
            date(2024, 6, 15),
            gold_bucket="test-gold",
            dry_run=True,
        )
        assert rows == 3
        mock_mtm.assert_called_once_with(
            dt=date(2024, 6, 15),
            gold_bucket="test-gold",
            dry_run=True,
        )

    @patch(
        "prediction_data.gold.wallet_position_snapshot.compute_wallet_position_snapshot",
        return_value=5,
    )
    def test_wallet_position_snapshot_daily(self, mock_snap: MagicMock) -> None:
        from prediction_data.cli.gold import _rebuild_day

        rows = _rebuild_day(
            "wallet_position_snapshot_daily",
            date(2024, 6, 15),
            gold_bucket="test-gold",
            dry_run=True,
        )
        assert rows == 5
        mock_snap.assert_called_once_with(
            dt=date(2024, 6, 15),
            gold_bucket="test-gold",
            dry_run=True,
        )

    def test_unknown_table_raises(self) -> None:
        import pytest

        from prediction_data.cli.gold import _rebuild_day

        with pytest.raises(ValueError, match="Unknown rebuild table"):
            _rebuild_day("nonexistent_table", date(2024, 6, 15))


class TestGoldPartitionExists:
    """Unit tests for _gold_partition_exists."""

    def test_returns_true_when_exists(self) -> None:
        from prediction_data.cli.gold import _gold_partition_exists

        mock_s3 = MagicMock()
        mock_s3.head_object.return_value = {"ContentLength": 1234}

        assert _gold_partition_exists(mock_s3, "bucket", "market_mark_daily", "2024-06-15") is True
        mock_s3.head_object.assert_called_once_with(
            Bucket="bucket",
            Key="gold/market_mark_daily/day=2024-06-15/part-000.parquet",
        )

    def test_returns_false_when_not_found(self) -> None:
        from prediction_data.cli.gold import _gold_partition_exists

        mock_s3 = MagicMock()
        mock_s3.head_object.side_effect = Exception("404 Not Found")

        assert _gold_partition_exists(mock_s3, "bucket", "market_mark_daily", "2024-06-15") is False
