"""Tests for scheduling and CLI commands (sprint 08 testing category).

Covers:
- Integration test: daily-run executes all steps in order via real dispatch
- Unit test: ch-load respects lookback window (only loads recent partitions)
- Unit test: rebuild processes dates in correct order for cumulative tables
- Comprehensive --help output verification for all Gold CLI commands
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pyarrow as pa
import pytest
from typer.testing import CliRunner

from prediction_data.cli.gold import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Integration test: daily-run end-to-end dispatch
# ---------------------------------------------------------------------------


class TestDailyRunIntegration:
    """Integration test verifying daily-run dispatches through _run_daily_step
    to the real underlying functions in the correct order."""

    @patch("prediction_data.cli.gold._emit_daily_run_metadata")
    @patch(
        "prediction_data.gold.wallet_position_snapshot.compute_wallet_position_snapshot",
        return_value=5,
    )
    @patch("prediction_data.gold.wallet_mtm.compute_wallet_mtm", return_value=3)
    @patch("prediction_data.gold.wallet_pnl.compute_wallet_pnl", return_value=7)
    @patch(
        "prediction_data.gold.market_marks.compute_market_marks", return_value=42
    )
    @patch("prediction_data.gold.dimensions.load_dim_category", return_value=5)
    @patch("prediction_data.gold.dimensions.load_dim_event", return_value=10)
    @patch("prediction_data.gold.dimensions.load_dim_wallet", return_value=20)
    @patch("prediction_data.gold.dimensions.load_dim_outcome", return_value=15)
    @patch("prediction_data.gold.dimensions.load_dim_market", return_value=100)
    @patch("prediction_data.gold.dimensions.load_dim_platform", return_value=2)
    @patch("prediction_data.cli.gold.get_settings")
    def test_daily_run_dispatches_all_steps_end_to_end(
        self,
        mock_settings: MagicMock,
        mock_platform: MagicMock,
        mock_market: MagicMock,
        mock_outcome: MagicMock,
        mock_wallet: MagicMock,
        mock_event: MagicMock,
        mock_category: MagicMock,
        mock_marks: MagicMock,
        mock_pnl: MagicMock,
        mock_mtm: MagicMock,
        mock_snap: MagicMock,
        mock_metadata: MagicMock,
    ) -> None:
        """Verify daily-run dispatches through the real _run_daily_step to
        all underlying compute functions, in the correct execution order.

        This does NOT mock _run_daily_step — it mocks the leaf functions
        that _run_daily_step calls, so we verify the full dispatch chain.
        process-trades is expected to fail (NotImplementedError) and the
        fail-forward behaviour should continue to compute-marks and
        compute-wallet-metrics.
        """
        mock_settings.return_value.gold_bucket = "test-gold"

        result = runner.invoke(
            app, ["daily-run", "--dt", "2024-06-15", "--dry-run"]
        )

        # Should exit 1 because process-trades raises NotImplementedError.
        assert result.exit_code == 1

        # Step 1: load-dims — all dimension loaders called.
        mock_platform.assert_called_once_with(
            gold_bucket="test-gold", dry_run=True
        )
        mock_market.assert_called_once_with(
            gold_bucket="test-gold", dry_run=True
        )
        mock_outcome.assert_called_once_with(
            gold_bucket="test-gold", dry_run=True
        )
        mock_wallet.assert_called_once_with(
            gold_bucket="test-gold", dry_run=True
        )
        mock_event.assert_called_once_with(
            gold_bucket="test-gold", dry_run=True
        )
        mock_category.assert_called_once_with(
            gold_bucket="test-gold", dry_run=True
        )

        # Step 2: process-trades — fails with NotImplementedError (no mock).
        assert "process-trades" in result.output
        assert "FAILED" in result.output

        # Step 3: compute-marks — dispatched despite step 2 failure.
        mock_marks.assert_called_once_with(
            platform="polymarket",
            dt=date(2024, 6, 15),
            gold_bucket="test-gold",
            dry_run=True,
        )

        # Step 4: compute-wallet-metrics — all three wallet functions called.
        mock_pnl.assert_called_once_with(
            dt=date(2024, 6, 15), gold_bucket="test-gold", dry_run=True
        )
        mock_mtm.assert_called_once_with(
            dt=date(2024, 6, 15), gold_bucket="test-gold", dry_run=True
        )
        mock_snap.assert_called_once_with(
            dt=date(2024, 6, 15), gold_bucket="test-gold", dry_run=True
        )

        # Summary: 3/4 steps succeeded (process-trades failed).
        assert "Steps succeeded: 3/4" in result.output

        # Total rows: dims(152) + marks(42) + wallet(15) = 209.
        assert "Total rows: 209" in result.output

        # Metadata emitted with failure flag.
        mock_metadata.assert_called_once()
        assert mock_metadata.call_args.kwargs["has_failures"] is True
        assert mock_metadata.call_args.kwargs["total_rows"] == 209

    @patch("prediction_data.cli.gold._emit_daily_run_metadata")
    @patch(
        "prediction_data.gold.wallet_position_snapshot.compute_wallet_position_snapshot",
        return_value=5,
    )
    @patch("prediction_data.gold.wallet_mtm.compute_wallet_mtm", return_value=3)
    @patch("prediction_data.gold.wallet_pnl.compute_wallet_pnl", return_value=7)
    @patch(
        "prediction_data.gold.market_marks.compute_market_marks", return_value=42
    )
    @patch("prediction_data.gold.dimensions.load_dim_category", return_value=5)
    @patch("prediction_data.gold.dimensions.load_dim_event", return_value=10)
    @patch("prediction_data.gold.dimensions.load_dim_wallet", return_value=20)
    @patch("prediction_data.gold.dimensions.load_dim_outcome", return_value=15)
    @patch("prediction_data.gold.dimensions.load_dim_market", return_value=100)
    @patch("prediction_data.gold.dimensions.load_dim_platform", return_value=2)
    @patch("prediction_data.cli.gold.get_settings")
    def test_daily_run_stop_on_error_halts_at_process_trades(
        self,
        mock_settings: MagicMock,
        mock_platform: MagicMock,
        mock_market: MagicMock,
        mock_outcome: MagicMock,
        mock_wallet: MagicMock,
        mock_event: MagicMock,
        mock_category: MagicMock,
        mock_marks: MagicMock,
        mock_pnl: MagicMock,
        mock_mtm: MagicMock,
        mock_snap: MagicMock,
        mock_metadata: MagicMock,
    ) -> None:
        """With --stop-on-error, daily-run halts at process-trades and
        does NOT continue to compute-marks or compute-wallet-metrics."""
        mock_settings.return_value.gold_bucket = "test-gold"

        result = runner.invoke(
            app,
            ["daily-run", "--dt", "2024-06-15", "--dry-run", "--stop-on-error"],
        )

        assert result.exit_code == 1

        # load-dims should have been called (step 1 succeeds).
        mock_platform.assert_called_once()

        # compute-marks and wallet metrics should NOT be called.
        mock_marks.assert_not_called()
        mock_pnl.assert_not_called()
        mock_mtm.assert_not_called()
        mock_snap.assert_not_called()

        assert "Halting due to --stop-on-error" in result.output


# ---------------------------------------------------------------------------
# Unit test: ch-load lookback window
# ---------------------------------------------------------------------------


class TestChLoadLookbackWindow:
    """Verify ch-load only loads partitions within the lookback window."""

    @patch("prediction_data.gold.ch_loader._read_gold_parquet_for_day")
    def test_lookback_excludes_old_dates(self, mock_read: MagicMock) -> None:
        """Only days within lookback window are scanned; older days are not."""
        from prediction_data.gold.ch_loader import load_gold_table_to_clickhouse

        ch = MagicMock()
        s3 = MagicMock()
        mock_read.return_value = None

        load_gold_table_to_clickhouse(
            table_name="market_mark_daily",
            gold_bucket="test-gold",
            lookback_days=5,
            s3_client=s3,
            clickhouse_client=ch,
        )

        # Should scan exactly 5 days.
        assert mock_read.call_count == 5

        # Verify the date range: today-4 through today.
        called_days = sorted(
            call.args[2] for call in mock_read.call_args_list
        )
        today = date.today()
        expected_days = sorted(
            str(today - timedelta(days=i)) for i in range(5)
        )
        assert called_days == expected_days

    @patch("prediction_data.gold.ch_loader._read_gold_parquet_for_day")
    def test_lookback_1_only_scans_today(self, mock_read: MagicMock) -> None:
        """With lookback_days=1, only today's partition is scanned."""
        from prediction_data.gold.ch_loader import load_gold_table_to_clickhouse

        ch = MagicMock()
        s3 = MagicMock()
        mock_read.return_value = None

        load_gold_table_to_clickhouse(
            table_name="market_mark_daily",
            gold_bucket="test-gold",
            lookback_days=1,
            s3_client=s3,
            clickhouse_client=ch,
        )

        assert mock_read.call_count == 1
        called_day = mock_read.call_args_list[0].args[2]
        assert called_day == str(date.today())

    @patch("prediction_data.gold.ch_loader._read_gold_parquet_for_day")
    def test_lookback_only_inserts_existing_partitions(
        self, mock_read: MagicMock
    ) -> None:
        """Only days with actual data are inserted into ClickHouse."""
        from prediction_data.gold.ch_loader import load_gold_table_to_clickhouse

        ch = MagicMock()
        s3 = MagicMock()

        sample = pa.table({"platform": ["poly"], "market_id": ["m1"]})

        # Only yesterday has data; today and day-before-yesterday return None.
        yesterday = str(date.today() - timedelta(days=1))

        def read_side_effect(
            bucket: str, table: str, day: str, *, s3_client: object = None
        ) -> pa.Table | None:
            if day == yesterday:
                return sample
            return None

        mock_read.side_effect = read_side_effect

        rows = load_gold_table_to_clickhouse(
            table_name="market_mark_daily",
            gold_bucket="test-gold",
            lookback_days=3,
            s3_client=s3,
            clickhouse_client=ch,
        )

        # 3 days scanned, 1 insert.
        assert mock_read.call_count == 3
        assert ch.insert.call_count == 1
        assert rows == 1


# ---------------------------------------------------------------------------
# Unit test: rebuild processes cumulative tables in correct date order
# ---------------------------------------------------------------------------


class TestRebuildCumulativeTableOrdering:
    """Verify rebuild processes cumulative tables sequentially from earliest
    to latest date."""

    @patch("prediction_data.cli.gold._rebuild_day")
    @patch("prediction_data.cli.gold.get_settings")
    def test_cumulative_table_processes_dates_sequentially(
        self,
        mock_settings: MagicMock,
        mock_rebuild: MagicMock,
    ) -> None:
        """wallet_pnl_daily (cumulative) must process from earliest to latest."""
        mock_settings.return_value.gold_bucket = "test-gold"
        mock_rebuild.return_value = 10

        result = runner.invoke(
            app,
            [
                "rebuild",
                "--table",
                "wallet_pnl_daily",
                "--start-date",
                "2024-06-01",
                "--end-date",
                "2024-06-05",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0

        # Verify dates are processed in chronological order.
        called_dates = [c.args[1] for c in mock_rebuild.call_args_list]
        assert called_dates == [
            date(2024, 6, 1),
            date(2024, 6, 2),
            date(2024, 6, 3),
            date(2024, 6, 4),
            date(2024, 6, 5),
        ]

        # Verify cumulative note appears in output.
        assert "cumulative" in result.output.lower()

    @patch("prediction_data.cli.gold._rebuild_day")
    @patch("prediction_data.cli.gold.get_settings")
    def test_wallet_mtm_cumulative_sequential_order(
        self,
        mock_settings: MagicMock,
        mock_rebuild: MagicMock,
    ) -> None:
        """wallet_mtm_daily (cumulative) processes earliest-first."""
        mock_settings.return_value.gold_bucket = "test-gold"
        mock_rebuild.return_value = 5

        result = runner.invoke(
            app,
            [
                "rebuild",
                "--table",
                "wallet_mtm_daily",
                "--start-date",
                "2024-03-10",
                "--end-date",
                "2024-03-13",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0

        called_dates = [c.args[1] for c in mock_rebuild.call_args_list]
        assert called_dates == [
            date(2024, 3, 10),
            date(2024, 3, 11),
            date(2024, 3, 12),
            date(2024, 3, 13),
        ]

        assert "cumulative" in result.output.lower()

    @patch("prediction_data.cli.gold._rebuild_day")
    @patch("prediction_data.cli.gold.get_settings")
    def test_wallet_position_snapshot_cumulative_sequential_order(
        self,
        mock_settings: MagicMock,
        mock_rebuild: MagicMock,
    ) -> None:
        """wallet_position_snapshot_daily (cumulative) processes earliest-first."""
        mock_settings.return_value.gold_bucket = "test-gold"
        mock_rebuild.return_value = 3

        result = runner.invoke(
            app,
            [
                "rebuild",
                "--table",
                "wallet_position_snapshot_daily",
                "--start-date",
                "2024-01-15",
                "--end-date",
                "2024-01-18",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0

        called_dates = [c.args[1] for c in mock_rebuild.call_args_list]
        assert called_dates == [
            date(2024, 1, 15),
            date(2024, 1, 16),
            date(2024, 1, 17),
            date(2024, 1, 18),
        ]

        assert "cumulative" in result.output.lower()

    @patch("prediction_data.cli.gold._rebuild_day")
    @patch("prediction_data.cli.gold.get_settings")
    def test_independent_table_also_processes_chronologically(
        self,
        mock_settings: MagicMock,
        mock_rebuild: MagicMock,
    ) -> None:
        """market_mark_daily (independent) also runs in chronological order
        but does NOT show the cumulative note."""
        mock_settings.return_value.gold_bucket = "test-gold"
        mock_rebuild.return_value = 20

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

        called_dates = [c.args[1] for c in mock_rebuild.call_args_list]
        assert called_dates == [
            date(2024, 6, 1),
            date(2024, 6, 2),
            date(2024, 6, 3),
        ]

        # Independent tables do NOT show the "cumulative" note.
        assert "cumulative" not in result.output.lower()


# ---------------------------------------------------------------------------
# Verify all Gold CLI commands show correct --help output
# ---------------------------------------------------------------------------


class TestAllGoldCommandsHelp:
    """Verify every Gold CLI command produces valid --help output with
    the expected options and flags."""

    def test_gold_help(self) -> None:
        """Top-level `gold --help` lists all subcommands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        # Core commands should be listed.
        assert "daily-run" in result.output
        assert "ch-load" in result.output
        assert "rebuild" in result.output
        assert "load-dims" in result.output
        assert "compute-marks" in result.output
        assert "status" in result.output

    def test_daily_run_help(self) -> None:
        result = runner.invoke(app, ["daily-run", "--help"])
        assert result.exit_code == 0
        assert "--dt" in result.output
        assert "--dry-run" in result.output
        assert "--stop-on-error" in result.output
        assert "load-dims" in result.output.lower() or "daily" in result.output.lower()

    def test_ch_load_help(self) -> None:
        result = runner.invoke(app, ["ch-load", "--help"])
        assert result.exit_code == 0
        assert "--table" in result.output
        assert "--all" in result.output
        assert "--lookback-days" in result.output
        assert "--dry-run" in result.output

    def test_rebuild_help(self) -> None:
        result = runner.invoke(app, ["rebuild", "--help"])
        assert result.exit_code == 0
        assert "--table" in result.output
        assert "--start-date" in result.output
        assert "--end-date" in result.output
        assert "--force" in result.output
        assert "--dry-run" in result.output

    def test_load_dims_help(self) -> None:
        result = runner.invoke(app, ["load-dims", "--help"])
        assert result.exit_code == 0
        assert "--table" in result.output
        assert "--dry-run" in result.output

    def test_compute_marks_help(self) -> None:
        result = runner.invoke(app, ["compute-marks", "--help"])
        assert result.exit_code == 0
        assert "--dt" in result.output
        assert "--start-date" in result.output
        assert "--end-date" in result.output
        assert "--platform" in result.output
        assert "--dry-run" in result.output

    def test_compute_pnl_help(self) -> None:
        result = runner.invoke(app, ["compute-pnl", "--help"])
        assert result.exit_code == 0
        assert "--dt" in result.output
        assert "--dry-run" in result.output

    def test_compute_mtm_help(self) -> None:
        result = runner.invoke(app, ["compute-mtm", "--help"])
        assert result.exit_code == 0
        assert "--dt" in result.output
        assert "--dry-run" in result.output

    def test_compute_position_snapshot_help(self) -> None:
        result = runner.invoke(app, ["compute-position-snapshot", "--help"])
        assert result.exit_code == 0
        assert "--dt" in result.output
        assert "--dry-run" in result.output

    def test_compute_wallet_metrics_help(self) -> None:
        result = runner.invoke(app, ["compute-wallet-metrics", "--help"])
        assert result.exit_code == 0
        assert "--dt" in result.output
        assert "--start-date" in result.output
        assert "--end-date" in result.output
        assert "--dry-run" in result.output

    def test_load_marks_ch_help(self) -> None:
        result = runner.invoke(app, ["load-marks-ch", "--help"])
        assert result.exit_code == 0
        assert "--lookback-days" in result.output
        assert "--dry-run" in result.output

    def test_status_help(self) -> None:
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0

    def test_freshness_help(self) -> None:
        result = runner.invoke(app, ["freshness", "--help"])
        assert result.exit_code == 0

    def test_compute_snapshot_help(self) -> None:
        result = runner.invoke(app, ["compute-snapshot", "--help"])
        assert result.exit_code == 0
        assert "--wallet" in result.output
        assert "--start-date" in result.output
        assert "--end-date" in result.output
        assert "--dry-run" in result.output
        assert "--skip-ch" in result.output
        assert "--chunk-days" in result.output

    def test_watchlist_help(self) -> None:
        result = runner.invoke(app, ["watchlist", "--help"])
        assert result.exit_code == 0
        assert "add" in result.output
        assert "remove" in result.output
        assert "list" in result.output

    def test_watchlist_add_help(self) -> None:
        result = runner.invoke(app, ["watchlist", "add", "--help"])
        assert result.exit_code == 0
        assert "address" in result.output.lower()

    def test_watchlist_remove_help(self) -> None:
        result = runner.invoke(app, ["watchlist", "remove", "--help"])
        assert result.exit_code == 0
        assert "address" in result.output.lower()

    def test_watchlist_list_help(self) -> None:
        result = runner.invoke(app, ["watchlist", "list", "--help"])
        assert result.exit_code == 0
        assert "--all" in result.output
