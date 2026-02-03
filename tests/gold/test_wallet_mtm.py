"""Tests for Gold wallet_mtm_daily computation."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from prediction_data.gold.wallet_mtm import (
    WALLET_MTM_DAILY_COLUMNS,
    WALLET_MTM_DAILY_SCHEMA,
    compute_mtm_for_day,
    compute_wallet_mtm,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_position(
    wallet: str = "0xAAA",
    platform: str = "polymarket",
    market_id: str = "mkt1",
    outcome_id: str = "tok1",
    qty: float = 100.0,
    avg_cost: float = 0.50,
) -> dict:
    return {
        "wallet": wallet,
        "platform": platform,
        "market_id": market_id,
        "outcome_id": outcome_id,
        "qty": qty,
        "avg_cost": avg_cost,
    }


# ---------------------------------------------------------------------------
# compute_mtm_for_day tests
# ---------------------------------------------------------------------------


class TestComputeMtmForDay:
    def test_single_wallet_single_position(self) -> None:
        positions = [_make_position(wallet="0xA", qty=100.0, avg_cost=0.50)]
        marks = {("polymarket", "mkt1", "tok1"): 0.70}
        result = compute_mtm_for_day(positions, marks, date(2024, 6, 15))
        assert result.num_rows == 1
        row = result.to_pylist()[0]
        assert row["wallet"] == "0xA"
        assert abs(row["equity_usd"] - 70.0) < 1e-9  # 100 * 0.70
        assert abs(row["unrealized_pnl_usd"] - 20.0) < 1e-9  # 100 * (0.70 - 0.50)
        assert abs(row["exposure_gross_usd"] - 70.0) < 1e-9
        assert abs(row["exposure_net_usd"] - 70.0) < 1e-9
        assert row["positions_count"] == 1
        assert row["missing_marks_count"] == 0

    def test_multiple_positions_same_wallet(self) -> None:
        positions = [
            _make_position(wallet="0xA", market_id="mkt1", outcome_id="tok1", qty=100.0, avg_cost=0.50),
            _make_position(wallet="0xA", market_id="mkt2", outcome_id="tok2", qty=-50.0, avg_cost=0.60),
        ]
        marks = {
            ("polymarket", "mkt1", "tok1"): 0.70,
            ("polymarket", "mkt2", "tok2"): 0.40,
        }
        result = compute_mtm_for_day(positions, marks, date(2024, 6, 15))
        assert result.num_rows == 1
        row = result.to_pylist()[0]
        # equity = 100*0.70 + (-50)*0.40 = 70 - 20 = 50
        assert abs(row["equity_usd"] - 50.0) < 1e-9
        # unrealized = 100*(0.70-0.50) + (-50)*(0.40-0.60) = 20 + 10 = 30
        assert abs(row["unrealized_pnl_usd"] - 30.0) < 1e-9
        # gross = abs(70) + abs(-20) = 90
        assert abs(row["exposure_gross_usd"] - 90.0) < 1e-9
        # net = 70 + (-20) = 50
        assert abs(row["exposure_net_usd"] - 50.0) < 1e-9
        assert row["positions_count"] == 2

    def test_multiple_wallets(self) -> None:
        positions = [
            _make_position(wallet="0xA", qty=100.0, avg_cost=0.50),
            _make_position(wallet="0xB", market_id="mkt2", outcome_id="tok2", qty=200.0, avg_cost=0.30),
        ]
        marks = {
            ("polymarket", "mkt1", "tok1"): 0.60,
            ("polymarket", "mkt2", "tok2"): 0.45,
        }
        result = compute_mtm_for_day(positions, marks, date(2024, 6, 15))
        assert result.num_rows == 2
        rows_by_wallet = {r["wallet"]: r for r in result.to_pylist()}
        assert abs(rows_by_wallet["0xA"]["equity_usd"] - 60.0) < 1e-9
        assert abs(rows_by_wallet["0xB"]["equity_usd"] - 90.0) < 1e-9

    def test_missing_mark_skips_position(self) -> None:
        positions = [
            _make_position(wallet="0xA", market_id="mkt1", outcome_id="tok1", qty=100.0, avg_cost=0.50),
            _make_position(wallet="0xA", market_id="mkt2", outcome_id="tok2", qty=50.0, avg_cost=0.40),
        ]
        # Only mkt1 has a mark.
        marks = {("polymarket", "mkt1", "tok1"): 0.70}
        result = compute_mtm_for_day(positions, marks, date(2024, 6, 15))
        assert result.num_rows == 1
        row = result.to_pylist()[0]
        assert abs(row["equity_usd"] - 70.0) < 1e-9  # only mkt1 counted
        assert row["positions_count"] == 1
        assert row["missing_marks_count"] == 1

    def test_all_marks_missing(self) -> None:
        positions = [_make_position(wallet="0xA")]
        marks: dict = {}
        result = compute_mtm_for_day(positions, marks, date(2024, 6, 15))
        assert result.num_rows == 1
        row = result.to_pylist()[0]
        assert row["positions_count"] == 0
        assert row["missing_marks_count"] == 1
        assert abs(row["equity_usd"]) < 1e-9

    def test_empty_positions(self) -> None:
        result = compute_mtm_for_day([], {}, date(2024, 6, 15))
        assert result.num_rows == 0
        assert result.schema == WALLET_MTM_DAILY_SCHEMA

    def test_schema_matches(self) -> None:
        positions = [_make_position()]
        marks = {("polymarket", "mkt1", "tok1"): 0.60}
        result = compute_mtm_for_day(positions, marks, date(2024, 6, 15))
        assert result.schema == WALLET_MTM_DAILY_SCHEMA

    def test_day_utc_set_correctly(self) -> None:
        positions = [_make_position()]
        marks = {("polymarket", "mkt1", "tok1"): 0.60}
        result = compute_mtm_for_day(positions, marks, date(2024, 12, 25))
        row = result.to_pylist()[0]
        assert row["day_utc"] == date(2024, 12, 25)

    def test_empty_wallet_skipped(self) -> None:
        positions = [_make_position(wallet=""), _make_position(wallet="0xA")]
        marks = {("polymarket", "mkt1", "tok1"): 0.60}
        result = compute_mtm_for_day(positions, marks, date(2024, 6, 15))
        assert result.num_rows == 1
        assert result.to_pylist()[0]["wallet"] == "0xA"


# ---------------------------------------------------------------------------
# compute_wallet_mtm tests
# ---------------------------------------------------------------------------


class TestComputeWalletMtm:
    def test_no_watchlist_wallets_returns_zero(self) -> None:
        mock_ch = MagicMock()
        # watchlist query returns empty
        mock_ch.query.return_value.result_rows = []
        rows = compute_wallet_mtm(
            dt=date(2024, 6, 15),
            clickhouse_client=mock_ch,
        )
        assert rows == 0
        mock_ch.insert.assert_not_called()

    def test_dry_run_skips_writes(self) -> None:
        mock_ch = MagicMock()

        def query_side_effect(query: str, **kwargs: object) -> MagicMock:
            result = MagicMock()
            if "gold_watchlist" in query:
                result.result_rows = [("0xA",)]
            elif "wallet_position_state" in query:
                result.result_rows = [("0xA", "polymarket", "mkt1", "tok1", 100.0, 0.50)]
            elif "market_mark_daily" in query:
                result.result_rows = [("polymarket", "mkt1", "tok1", 0.70)]
            else:
                result.result_rows = []
            return result

        mock_ch.query.side_effect = query_side_effect
        rows = compute_wallet_mtm(
            dt=date(2024, 6, 15),
            clickhouse_client=mock_ch,
            dry_run=True,
        )
        assert rows == 1
        mock_ch.insert.assert_not_called()

    def test_writes_to_s3_and_ch(self) -> None:
        mock_ch = MagicMock()

        def query_side_effect(query: str, **kwargs: object) -> MagicMock:
            result = MagicMock()
            if "gold_watchlist" in query:
                result.result_rows = [("0xA",)]
            elif "wallet_position_state" in query:
                result.result_rows = [("0xA", "polymarket", "mkt1", "tok1", 100.0, 0.50)]
            elif "market_mark_daily" in query:
                result.result_rows = [("polymarket", "mkt1", "tok1", 0.70)]
            else:
                result.result_rows = []
            return result

        mock_ch.query.side_effect = query_side_effect
        mock_s3 = MagicMock()
        paginator = MagicMock()
        paginator.paginate.return_value = [{"Contents": []}]
        mock_s3.get_paginator.return_value = paginator

        rows = compute_wallet_mtm(
            dt=date(2024, 6, 15),
            gold_bucket="test-gold",
            s3_client=mock_s3,
            clickhouse_client=mock_ch,
        )
        assert rows == 1
        mock_s3.put_object.assert_called_once()
        mock_ch.insert.assert_called_once()


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestComputeMtmCli:
    def test_cli_help(self) -> None:
        from prediction_data.cli.gold import app

        result = runner.invoke(app, ["compute-mtm", "--help"])
        assert result.exit_code == 0
        assert "wallet_mtm_daily" in result.output

    def test_cli_requires_date(self) -> None:
        from prediction_data.cli.gold import app

        result = runner.invoke(app, ["compute-mtm"])
        assert result.exit_code == 1

    @patch("prediction_data.cli.gold.get_settings")
    @patch("prediction_data.gold.wallet_mtm.compute_wallet_mtm")
    def test_cli_single_date(self, mock_compute: MagicMock, mock_settings: MagicMock) -> None:
        from prediction_data.cli.gold import app

        mock_settings.return_value.gold_bucket = "test-gold"
        mock_compute.return_value = 3

        result = runner.invoke(app, ["compute-mtm", "--dt", "2024-06-15", "--dry-run"])
        assert result.exit_code == 0
        assert "3 rows" in result.output
        mock_compute.assert_called_once()

    def test_cli_dt_conflicts_with_range(self) -> None:
        from prediction_data.cli.gold import app

        result = runner.invoke(app, ["compute-mtm", "--dt", "2024-06-15", "--start-date", "2024-06-01", "--end-date", "2024-06-30"])
        assert result.exit_code == 1
