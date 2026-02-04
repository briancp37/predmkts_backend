"""Tests for the Gold ch-load CLI command and ch_loader module."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, call, patch

import pyarrow as pa
import pytest
from typer.testing import CliRunner

from prediction_data.cli.gold import app
from prediction_data.gold.ch_loader import (
    ALL_GOLD_TABLES,
    _get_table_columns,
    _read_gold_parquet_for_day,
    load_gold_table_to_clickhouse,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestChLoadCli:
    """Tests for `prediction-data gold ch-load`."""

    def test_help(self) -> None:
        result = runner.invoke(app, ["ch-load", "--help"])
        assert result.exit_code == 0
        assert "--table" in result.output
        assert "--all" in result.output
        assert "--lookback-days" in result.output
        assert "--dry-run" in result.output

    @patch("prediction_data.cli.gold.get_settings")
    def test_error_no_table_or_all(self, mock_settings: MagicMock) -> None:
        mock_settings.return_value.gold_bucket = "test-gold"
        result = runner.invoke(app, ["ch-load"])
        assert result.exit_code == 1
        assert "specify --table TABLE or --all" in result.output

    @patch("prediction_data.cli.gold.get_settings")
    def test_error_table_and_all_mutually_exclusive(
        self, mock_settings: MagicMock
    ) -> None:
        mock_settings.return_value.gold_bucket = "test-gold"
        result = runner.invoke(
            app, ["ch-load", "--table", "market_mark_daily", "--all"]
        )
        assert result.exit_code == 1
        assert "mutually exclusive" in result.output

    @patch("prediction_data.cli.gold.get_settings")
    def test_error_no_gold_bucket(self, mock_settings: MagicMock) -> None:
        mock_settings.return_value.gold_bucket = ""
        result = runner.invoke(app, ["ch-load", "--table", "market_mark_daily"])
        assert result.exit_code == 1
        assert "GOLD_BUCKET not configured" in result.output

    @patch("prediction_data.cli.gold.get_settings")
    def test_error_unknown_table(self, mock_settings: MagicMock) -> None:
        mock_settings.return_value.gold_bucket = "test-gold"
        result = runner.invoke(app, ["ch-load", "--table", "bogus_table"])
        assert result.exit_code == 1
        assert "unknown table" in result.output

    @patch("prediction_data.cli.gold.get_settings")
    def test_dry_run_single_table(self, mock_settings: MagicMock) -> None:
        mock_settings.return_value.gold_bucket = "test-gold"
        result = runner.invoke(
            app,
            ["ch-load", "--table", "market_mark_daily", "--lookback-days", "30", "--dry-run"],
        )
        assert result.exit_code == 0
        assert "[dry-run]" in result.output
        assert "market_mark_daily" in result.output
        assert "lookback=30" in result.output

    @patch("prediction_data.cli.gold.get_settings")
    def test_dry_run_all_tables(self, mock_settings: MagicMock) -> None:
        mock_settings.return_value.gold_bucket = "test-gold"
        result = runner.invoke(app, ["ch-load", "--all", "--dry-run"])
        assert result.exit_code == 0
        for tbl in ALL_GOLD_TABLES:
            assert tbl in result.output

    @patch("prediction_data.gold.ch_loader.load_gold_table_to_clickhouse")
    @patch("prediction_data.cli.gold.get_settings")
    def test_single_table_success(
        self, mock_settings: MagicMock, mock_load: MagicMock
    ) -> None:
        mock_settings.return_value.gold_bucket = "test-gold"
        mock_load.return_value = 100

        result = runner.invoke(
            app,
            ["ch-load", "--table", "market_mark_daily", "--lookback-days", "30"],
        )

        assert result.exit_code == 0
        assert "100 rows loaded" in result.output
        mock_load.assert_called_once_with(
            table_name="market_mark_daily",
            gold_bucket="test-gold",
            lookback_days=30,
        )

    @patch("prediction_data.gold.ch_loader.load_gold_table_to_clickhouse")
    @patch("prediction_data.cli.gold.get_settings")
    def test_all_tables_success(
        self, mock_settings: MagicMock, mock_load: MagicMock
    ) -> None:
        mock_settings.return_value.gold_bucket = "test-gold"
        mock_load.return_value = 50

        result = runner.invoke(app, ["ch-load", "--all"])

        assert result.exit_code == 0
        assert mock_load.call_count == len(ALL_GOLD_TABLES)
        expected_total = 50 * len(ALL_GOLD_TABLES)
        assert f"Total: {expected_total} rows" in result.output

    @patch("prediction_data.gold.ch_loader.load_gold_table_to_clickhouse")
    @patch("prediction_data.cli.gold.get_settings")
    def test_table_failure_reports_error(
        self, mock_settings: MagicMock, mock_load: MagicMock
    ) -> None:
        mock_settings.return_value.gold_bucket = "test-gold"
        mock_load.side_effect = RuntimeError("CH connection failed")

        result = runner.invoke(
            app, ["ch-load", "--table", "market_mark_daily"]
        )

        assert result.exit_code == 1
        assert "FAILED" in result.output
        assert "CH connection failed" in result.output

    @patch("prediction_data.gold.ch_loader.load_gold_table_to_clickhouse")
    @patch("prediction_data.cli.gold.get_settings")
    def test_all_tables_partial_failure(
        self, mock_settings: MagicMock, mock_load: MagicMock
    ) -> None:
        """When --all is used and one table fails, others still load."""
        mock_settings.return_value.gold_bucket = "test-gold"

        def side_effect(*, table_name: str, gold_bucket: str, lookback_days: int) -> int:
            if table_name == "wallet_pnl_daily":
                raise RuntimeError("table not found")
            return 25

        mock_load.side_effect = side_effect

        result = runner.invoke(app, ["ch-load", "--all"])

        assert result.exit_code == 1
        assert "1 table(s) failed" in result.output
        assert "wallet_pnl_daily" in result.output
        # Other tables should succeed.
        assert "market_mark_daily: 25 rows" in result.output


# ---------------------------------------------------------------------------
# ch_loader module unit tests
# ---------------------------------------------------------------------------


class TestGetTableColumns:
    """Tests for _get_table_columns."""

    def test_market_mark_daily(self) -> None:
        cols = _get_table_columns("market_mark_daily")
        assert "platform" in cols
        assert "mark_price" in cols

    def test_wallet_pnl_daily(self) -> None:
        cols = _get_table_columns("wallet_pnl_daily")
        assert "wallet" in cols
        assert "realized_pnl_usd" in cols

    def test_wallet_mtm_daily(self) -> None:
        cols = _get_table_columns("wallet_mtm_daily")
        assert "wallet" in cols
        assert "equity_usd" in cols

    def test_wallet_position_snapshot_daily(self) -> None:
        cols = _get_table_columns("wallet_position_snapshot_daily")
        assert "wallet" in cols
        assert "position_value_usd" in cols

    def test_unknown_table_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown Gold table"):
            _get_table_columns("nonexistent_table")


class TestReadGoldParquetForDay:
    """Tests for _read_gold_parquet_for_day."""

    def test_returns_none_on_no_such_key(self) -> None:
        s3 = MagicMock()
        s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        s3.get_object.side_effect = s3.exceptions.NoSuchKey("nope")

        result = _read_gold_parquet_for_day(
            "test-gold", "market_mark_daily", "2024-06-15", s3_client=s3
        )
        assert result is None

    def test_returns_none_on_generic_error(self) -> None:
        s3 = MagicMock()
        s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        s3.get_object.side_effect = RuntimeError("network error")

        result = _read_gold_parquet_for_day(
            "test-gold", "market_mark_daily", "2024-06-15", s3_client=s3
        )
        assert result is None


class TestLoadGoldTableToClickhouse:
    """Tests for load_gold_table_to_clickhouse."""

    @patch("prediction_data.gold.ch_loader._read_gold_parquet_for_day")
    def test_loads_days_within_lookback(self, mock_read: MagicMock) -> None:
        """Verify only days within lookback window are scanned."""
        ch = MagicMock()
        s3 = MagicMock()

        # Return data for 2 out of 3 days.
        sample = pa.table(
            {"platform": ["poly"], "market_id": ["m1"]},
        )

        call_count = 0

        def read_side_effect(
            bucket: str, table: str, day: str, *, s3_client: object = None
        ) -> pa.Table | None:
            nonlocal call_count
            call_count += 1
            # Return data only for today and yesterday.
            today_str = str(date.today())
            yesterday_str = str(date.today() - timedelta(days=1))
            if day in (today_str, yesterday_str):
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

        # Should scan 3 days.
        assert call_count == 3
        # Should insert for 2 days (1 row each).
        assert ch.insert.call_count == 2
        assert rows == 2

    @patch("prediction_data.gold.ch_loader._read_gold_parquet_for_day")
    def test_no_data_returns_zero(self, mock_read: MagicMock) -> None:
        """When no S3 partitions exist, returns 0 rows."""
        ch = MagicMock()
        s3 = MagicMock()
        mock_read.return_value = None

        rows = load_gold_table_to_clickhouse(
            table_name="market_mark_daily",
            gold_bucket="test-gold",
            lookback_days=7,
            s3_client=s3,
            clickhouse_client=ch,
        )

        assert rows == 0
        ch.insert.assert_not_called()

    @patch("prediction_data.gold.ch_loader._read_gold_parquet_for_day")
    def test_empty_tables_skipped(self, mock_read: MagicMock) -> None:
        """Empty Arrow tables (0 rows) should be skipped."""
        ch = MagicMock()
        s3 = MagicMock()

        empty = pa.table({"platform": pa.array([], type=pa.string())})
        mock_read.return_value = empty

        rows = load_gold_table_to_clickhouse(
            table_name="market_mark_daily",
            gold_bucket="test-gold",
            lookback_days=3,
            s3_client=s3,
            clickhouse_client=ch,
        )

        assert rows == 0
        ch.insert.assert_not_called()

    @patch("prediction_data.gold.ch_loader._read_gold_parquet_for_day")
    def test_default_lookback_is_90(self, mock_read: MagicMock) -> None:
        """Default lookback should be 90 days (DEFAULT_TTL_DAYS)."""
        ch = MagicMock()
        s3 = MagicMock()
        mock_read.return_value = None

        load_gold_table_to_clickhouse(
            table_name="market_mark_daily",
            gold_bucket="test-gold",
            s3_client=s3,
            clickhouse_client=ch,
        )

        # Should scan 90 days.
        assert mock_read.call_count == 90
