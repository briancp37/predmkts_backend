"""Tests for Gold wallet_pnl_daily computation."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pyarrow as pa
from typer.testing import CliRunner

from prediction_data.gold.wallet_pnl import (
    WALLET_PNL_DAILY_COLUMNS,
    WALLET_PNL_DAILY_SCHEMA,
    aggregate_pnl_for_day,
    compute_wallet_pnl,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_fill(
    wallet: str = "0xAAA",
    qty_delta: float = 10.0,
    price: float = 0.50,
    fees_usd: float = 0.01,
    realized_pnl: float = 0.0,
) -> dict:
    return {
        "wallet": wallet,
        "qty_delta": qty_delta,
        "price": price,
        "fees_usd": fees_usd,
        "realized_pnl_this_fill_usd": realized_pnl,
    }


# ---------------------------------------------------------------------------
# aggregate_pnl_for_day tests
# ---------------------------------------------------------------------------


class TestAggregatePnlForDay:
    def test_single_wallet_single_fill(self) -> None:
        fills = [_make_fill(wallet="0xA", qty_delta=10.0, price=0.5, fees_usd=0.02, realized_pnl=1.5)]
        result = aggregate_pnl_for_day(fills, date(2024, 6, 15))
        assert result.num_rows == 1
        row = result.to_pylist()[0]
        assert row["wallet"] == "0xA"
        assert abs(row["realized_pnl_usd"] - 1.5) < 1e-9
        assert abs(row["fees_usd"] - 0.02) < 1e-9
        assert abs(row["volume_usd"] - 5.0) < 1e-9  # abs(10 * 0.5)
        assert row["trades_count"] == 1
        assert row["wins"] == 1
        assert row["losses"] == 0

    def test_multiple_fills_same_wallet(self) -> None:
        fills = [
            _make_fill(wallet="0xA", qty_delta=10.0, price=0.5, fees_usd=0.01, realized_pnl=2.0),
            _make_fill(wallet="0xA", qty_delta=-5.0, price=0.7, fees_usd=0.02, realized_pnl=-0.5),
            _make_fill(wallet="0xA", qty_delta=3.0, price=0.6, fees_usd=0.01, realized_pnl=0.0),
        ]
        result = aggregate_pnl_for_day(fills, date(2024, 6, 15))
        assert result.num_rows == 1
        row = result.to_pylist()[0]
        assert abs(row["realized_pnl_usd"] - 1.5) < 1e-9  # 2.0 + (-0.5) + 0.0
        assert abs(row["fees_usd"] - 0.04) < 1e-9
        # volume = abs(10*0.5) + abs(-5*0.7) + abs(3*0.6) = 5 + 3.5 + 1.8 = 10.3
        assert abs(row["volume_usd"] - 10.3) < 1e-9
        assert row["trades_count"] == 3
        assert row["wins"] == 1
        assert row["losses"] == 1

    def test_multiple_wallets(self) -> None:
        fills = [
            _make_fill(wallet="0xA", realized_pnl=1.0),
            _make_fill(wallet="0xB", realized_pnl=-2.0),
            _make_fill(wallet="0xA", realized_pnl=0.5),
        ]
        result = aggregate_pnl_for_day(fills, date(2024, 6, 15))
        assert result.num_rows == 2
        rows_by_wallet = {r["wallet"]: r for r in result.to_pylist()}
        assert abs(rows_by_wallet["0xA"]["realized_pnl_usd"] - 1.5) < 1e-9
        assert abs(rows_by_wallet["0xB"]["realized_pnl_usd"] - (-2.0)) < 1e-9

    def test_empty_input(self) -> None:
        result = aggregate_pnl_for_day([], date(2024, 6, 15))
        assert result.num_rows == 0
        assert result.schema == WALLET_PNL_DAILY_SCHEMA

    def test_schema_matches(self) -> None:
        fills = [_make_fill()]
        result = aggregate_pnl_for_day(fills, date(2024, 6, 15))
        assert result.schema == WALLET_PNL_DAILY_SCHEMA

    def test_fills_with_empty_wallet_skipped(self) -> None:
        fills = [
            {"wallet": "", "qty_delta": 1.0, "price": 0.5, "fees_usd": 0.0, "realized_pnl_this_fill_usd": 0.0},
            _make_fill(wallet="0xA"),
        ]
        result = aggregate_pnl_for_day(fills, date(2024, 6, 15))
        assert result.num_rows == 1
        assert result.to_pylist()[0]["wallet"] == "0xA"

    def test_wins_losses_counting(self) -> None:
        fills = [
            _make_fill(wallet="0xA", realized_pnl=5.0),
            _make_fill(wallet="0xA", realized_pnl=-1.0),
            _make_fill(wallet="0xA", realized_pnl=-2.0),
            _make_fill(wallet="0xA", realized_pnl=0.0),  # neither win nor loss
        ]
        result = aggregate_pnl_for_day(fills, date(2024, 6, 15))
        row = result.to_pylist()[0]
        assert row["wins"] == 1
        assert row["losses"] == 2
        assert row["trades_count"] == 4

    def test_day_utc_set_correctly(self) -> None:
        fills = [_make_fill()]
        result = aggregate_pnl_for_day(fills, date(2024, 12, 25))
        row = result.to_pylist()[0]
        assert row["day_utc"] == date(2024, 12, 25)


# ---------------------------------------------------------------------------
# compute_wallet_pnl tests
# ---------------------------------------------------------------------------


class TestComputeWalletPnl:
    def test_dry_run_skips_writes(self) -> None:
        mock_ch = MagicMock()
        mock_ch.query.return_value.result_rows = [
            ("0xA", 10.0, 0.5, 0.01, 1.0),
        ]
        rows = compute_wallet_pnl(
            dt=date(2024, 6, 15),
            clickhouse_client=mock_ch,
            dry_run=True,
        )
        assert rows == 1
        mock_ch.insert.assert_not_called()

    def test_writes_to_s3_and_ch(self) -> None:
        mock_ch = MagicMock()
        mock_ch.query.return_value.result_rows = [
            ("0xA", 10.0, 0.5, 0.01, 1.0),
        ]
        mock_s3 = MagicMock()
        paginator = MagicMock()
        paginator.paginate.return_value = [{"Contents": []}]
        mock_s3.get_paginator.return_value = paginator

        rows = compute_wallet_pnl(
            dt=date(2024, 6, 15),
            gold_bucket="test-gold",
            s3_client=mock_s3,
            clickhouse_client=mock_ch,
        )
        assert rows == 1
        mock_s3.put_object.assert_called_once()
        mock_ch.insert.assert_called_once()

    def test_no_ledger_rows_produces_zero(self) -> None:
        mock_ch = MagicMock()
        mock_ch.query.return_value.result_rows = []
        rows = compute_wallet_pnl(
            dt=date(2024, 6, 15),
            clickhouse_client=mock_ch,
        )
        assert rows == 0


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestComputePnlCli:
    def test_cli_help(self) -> None:
        from prediction_data.cli.gold import app

        result = runner.invoke(app, ["compute-pnl", "--help"])
        assert result.exit_code == 0
        assert "wallet_pnl_daily" in result.output

    def test_cli_requires_date(self) -> None:
        from prediction_data.cli.gold import app

        result = runner.invoke(app, ["compute-pnl"])
        assert result.exit_code == 1

    @patch("prediction_data.cli.gold.get_settings")
    @patch("prediction_data.gold.wallet_pnl.compute_wallet_pnl")
    def test_cli_single_date(self, mock_compute: MagicMock, mock_settings: MagicMock) -> None:
        from prediction_data.cli.gold import app

        mock_settings.return_value.gold_bucket = "test-gold"
        mock_compute.return_value = 5

        result = runner.invoke(app, ["compute-pnl", "--dt", "2024-06-15", "--dry-run"])
        assert result.exit_code == 0
        assert "5 rows" in result.output
        mock_compute.assert_called_once()

    def test_cli_dt_conflicts_with_range(self) -> None:
        from prediction_data.cli.gold import app

        result = runner.invoke(app, ["compute-pnl", "--dt", "2024-06-15", "--start-date", "2024-06-01", "--end-date", "2024-06-30"])
        assert result.exit_code == 1
