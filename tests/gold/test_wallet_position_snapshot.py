"""Tests for Gold wallet_position_snapshot_daily computation."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from prediction_data.gold.wallet_position_snapshot import (
    WALLET_POSITION_SNAPSHOT_DAILY_COLUMNS,
    WALLET_POSITION_SNAPSHOT_DAILY_SCHEMA,
    compute_snapshot_for_day,
    compute_wallet_position_snapshot,
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
# compute_snapshot_for_day tests
# ---------------------------------------------------------------------------


class TestComputeSnapshotForDay:
    def test_single_position(self) -> None:
        positions = [_make_position(wallet="0xA", qty=100.0, avg_cost=0.50)]
        marks = {("polymarket", "mkt1", "tok1"): 0.70}
        result = compute_snapshot_for_day(positions, marks, date(2024, 6, 15))
        assert result.num_rows == 1
        row = result.to_pylist()[0]
        assert row["wallet"] == "0xA"
        assert row["platform"] == "polymarket"
        assert row["market_id"] == "mkt1"
        assert row["outcome_id"] == "tok1"
        assert abs(row["qty"] - 100.0) < 1e-9
        assert abs(row["avg_cost"] - 0.50) < 1e-9
        assert abs(row["mark_price"] - 0.70) < 1e-9
        assert abs(row["position_value_usd"] - 70.0) < 1e-9  # 100 * 0.70
        assert abs(row["unrealized_pnl_usd"] - 20.0) < 1e-9  # 100 * (0.70 - 0.50)

    def test_multiple_positions_same_wallet(self) -> None:
        positions = [
            _make_position(wallet="0xA", market_id="mkt1", outcome_id="tok1", qty=100.0, avg_cost=0.50),
            _make_position(wallet="0xA", market_id="mkt2", outcome_id="tok2", qty=-50.0, avg_cost=0.60),
        ]
        marks = {
            ("polymarket", "mkt1", "tok1"): 0.70,
            ("polymarket", "mkt2", "tok2"): 0.40,
        }
        result = compute_snapshot_for_day(positions, marks, date(2024, 6, 15))
        assert result.num_rows == 2
        rows = {r["market_id"]: r for r in result.to_pylist()}
        assert abs(rows["mkt1"]["position_value_usd"] - 70.0) < 1e-9
        assert abs(rows["mkt2"]["position_value_usd"] - (-20.0)) < 1e-9  # -50 * 0.40

    def test_multiple_wallets(self) -> None:
        positions = [
            _make_position(wallet="0xA", qty=100.0, avg_cost=0.50),
            _make_position(wallet="0xB", market_id="mkt2", outcome_id="tok2", qty=200.0, avg_cost=0.30),
        ]
        marks = {
            ("polymarket", "mkt1", "tok1"): 0.60,
            ("polymarket", "mkt2", "tok2"): 0.45,
        }
        result = compute_snapshot_for_day(positions, marks, date(2024, 6, 15))
        assert result.num_rows == 2
        rows_by_wallet = {r["wallet"]: r for r in result.to_pylist()}
        assert abs(rows_by_wallet["0xA"]["position_value_usd"] - 60.0) < 1e-9
        assert abs(rows_by_wallet["0xB"]["position_value_usd"] - 90.0) < 1e-9

    def test_missing_mark_skips_position(self) -> None:
        positions = [
            _make_position(wallet="0xA", market_id="mkt1", outcome_id="tok1", qty=100.0, avg_cost=0.50),
            _make_position(wallet="0xA", market_id="mkt2", outcome_id="tok2", qty=50.0, avg_cost=0.40),
        ]
        marks = {("polymarket", "mkt1", "tok1"): 0.70}
        result = compute_snapshot_for_day(positions, marks, date(2024, 6, 15))
        assert result.num_rows == 1
        row = result.to_pylist()[0]
        assert row["market_id"] == "mkt1"

    def test_all_marks_missing(self) -> None:
        positions = [_make_position(wallet="0xA")]
        marks: dict = {}
        result = compute_snapshot_for_day(positions, marks, date(2024, 6, 15))
        assert result.num_rows == 0

    def test_empty_positions(self) -> None:
        result = compute_snapshot_for_day([], {}, date(2024, 6, 15))
        assert result.num_rows == 0
        assert result.schema == WALLET_POSITION_SNAPSHOT_DAILY_SCHEMA

    def test_schema_matches(self) -> None:
        positions = [_make_position()]
        marks = {("polymarket", "mkt1", "tok1"): 0.60}
        result = compute_snapshot_for_day(positions, marks, date(2024, 6, 15))
        assert result.schema == WALLET_POSITION_SNAPSHOT_DAILY_SCHEMA

    def test_day_utc_set_correctly(self) -> None:
        positions = [_make_position()]
        marks = {("polymarket", "mkt1", "tok1"): 0.60}
        result = compute_snapshot_for_day(positions, marks, date(2024, 12, 25))
        row = result.to_pylist()[0]
        assert row["day_utc"] == date(2024, 12, 25)

    def test_empty_wallet_skipped(self) -> None:
        positions = [_make_position(wallet=""), _make_position(wallet="0xA")]
        marks = {("polymarket", "mkt1", "tok1"): 0.60}
        result = compute_snapshot_for_day(positions, marks, date(2024, 6, 15))
        assert result.num_rows == 1
        assert result.to_pylist()[0]["wallet"] == "0xA"

    def test_negative_qty_short_position(self) -> None:
        positions = [_make_position(wallet="0xA", qty=-50.0, avg_cost=0.60)]
        marks = {("polymarket", "mkt1", "tok1"): 0.40}
        result = compute_snapshot_for_day(positions, marks, date(2024, 6, 15))
        row = result.to_pylist()[0]
        assert abs(row["position_value_usd"] - (-20.0)) < 1e-9  # -50 * 0.40
        assert abs(row["unrealized_pnl_usd"] - 10.0) < 1e-9  # -50 * (0.40 - 0.60)


# ---------------------------------------------------------------------------
# compute_wallet_position_snapshot tests
# ---------------------------------------------------------------------------


class TestComputeWalletPositionSnapshot:
    def test_no_watchlist_wallets_returns_zero(self) -> None:
        mock_ch = MagicMock()
        mock_ch.query.return_value.result_rows = []
        rows = compute_wallet_position_snapshot(
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
        rows = compute_wallet_position_snapshot(
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

        rows = compute_wallet_position_snapshot(
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


class TestComputePositionSnapshotCli:
    def test_cli_help(self) -> None:
        from prediction_data.cli.gold import app

        result = runner.invoke(app, ["compute-position-snapshot", "--help"])
        assert result.exit_code == 0
        assert "wallet_position_snapshot_daily" in result.output

    def test_cli_requires_date(self) -> None:
        from prediction_data.cli.gold import app

        result = runner.invoke(app, ["compute-position-snapshot"])
        assert result.exit_code == 1

    @patch("prediction_data.cli.gold.get_settings")
    @patch("prediction_data.gold.wallet_position_snapshot.compute_wallet_position_snapshot")
    def test_cli_single_date(self, mock_compute: MagicMock, mock_settings: MagicMock) -> None:
        from prediction_data.cli.gold import app

        mock_settings.return_value.gold_bucket = "test-gold"
        mock_compute.return_value = 5

        result = runner.invoke(app, ["compute-position-snapshot", "--dt", "2024-06-15", "--dry-run"])
        assert result.exit_code == 0
        assert "5 rows" in result.output
        mock_compute.assert_called_once()

    def test_cli_dt_conflicts_with_range(self) -> None:
        from prediction_data.cli.gold import app

        result = runner.invoke(app, ["compute-position-snapshot", "--dt", "2024-06-15", "--start-date", "2024-06-01", "--end-date", "2024-06-30"])
        assert result.exit_code == 1
