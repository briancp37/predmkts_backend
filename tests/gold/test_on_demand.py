"""Tests for on-demand snapshot reconstruction."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock

from prediction_data.gold.on_demand import (
    SNAPSHOT_SCHEMA,
    _replay_fills_to_snapshots,
    compute_wallet_snapshots,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fill(
    ts: datetime,
    platform: str = "polymarket",
    market_id: str = "mkt1",
    outcome_id: str = "tok1",
    side: str = "buy",
    qty_delta: float = 10.0,
    price: float = 0.50,
    fees_usd: float = 0.0,
    avg_cost_after: float = 0.50,
    qty_after: float = 10.0,
) -> dict:
    return {
        "ts": ts,
        "platform": platform,
        "market_id": market_id,
        "outcome_id": outcome_id,
        "side": side,
        "qty_delta": qty_delta,
        "price": price,
        "fees_usd": fees_usd,
        "avg_cost_after": avg_cost_after,
        "qty_after": qty_after,
    }


# ---------------------------------------------------------------------------
# _replay_fills_to_snapshots
# ---------------------------------------------------------------------------


class TestReplayFills:
    def test_single_fill_single_day(self) -> None:
        fills = [
            _make_fill(
                ts=datetime(2024, 6, 15, 10, 0, 0),
                qty_delta=100.0,
                price=0.50,
                avg_cost_after=0.50,
                qty_after=100.0,
            ),
        ]
        marks = {(date(2024, 6, 15), "polymarket", "mkt1", "tok1"): 0.60}
        result = _replay_fills_to_snapshots(
            "0xA", [date(2024, 6, 15)], {}, fills, marks
        )
        assert result.num_rows == 1
        row = result.to_pylist()[0]
        assert row["wallet"] == "0xA"
        assert row["qty"] == 100.0
        assert row["avg_cost"] == 0.50
        assert abs(row["mark_price"] - 0.60) < 1e-9
        assert abs(row["position_value_usd"] - 60.0) < 1e-9
        assert abs(row["unrealized_pnl_usd"] - 10.0) < 1e-9

    def test_carry_forward_position(self) -> None:
        """Position from day 1 carries forward to day 2 with no fills."""
        fills = [
            _make_fill(
                ts=datetime(2024, 6, 15, 10, 0, 0),
                qty_after=100.0,
                avg_cost_after=0.50,
            ),
        ]
        marks = {
            (date(2024, 6, 15), "polymarket", "mkt1", "tok1"): 0.55,
            (date(2024, 6, 16), "polymarket", "mkt1", "tok1"): 0.65,
        }
        result = _replay_fills_to_snapshots(
            "0xA",
            [date(2024, 6, 15), date(2024, 6, 16)],
            {},
            fills,
            marks,
        )
        assert result.num_rows == 2
        rows = result.to_pylist()
        assert rows[0]["day_utc"] == date(2024, 6, 15)
        assert abs(rows[0]["position_value_usd"] - 55.0) < 1e-9
        assert rows[1]["day_utc"] == date(2024, 6, 16)
        assert abs(rows[1]["position_value_usd"] - 65.0) < 1e-9
        # qty and avg_cost carried forward
        assert rows[1]["qty"] == 100.0
        assert rows[1]["avg_cost"] == 0.50

    def test_initial_positions_carried(self) -> None:
        """Existing positions before range are carried forward."""
        initial = {
            ("polymarket", "mkt1", "tok1"): {"qty": 50.0, "avg_cost": 0.40},
        }
        marks = {(date(2024, 6, 15), "polymarket", "mkt1", "tok1"): 0.70}
        result = _replay_fills_to_snapshots(
            "0xA", [date(2024, 6, 15)], initial, [], marks
        )
        assert result.num_rows == 1
        row = result.to_pylist()[0]
        assert row["qty"] == 50.0
        assert abs(row["position_value_usd"] - 35.0) < 1e-9  # 50 * 0.70

    def test_position_closed_mid_range(self) -> None:
        """Position with qty=0 is removed from snapshot."""
        fills = [
            _make_fill(
                ts=datetime(2024, 6, 15, 10, 0, 0),
                qty_after=100.0,
                avg_cost_after=0.50,
            ),
            _make_fill(
                ts=datetime(2024, 6, 16, 10, 0, 0),
                side="sell",
                qty_delta=-100.0,
                price=0.70,
                qty_after=0.0,
                avg_cost_after=0.50,
            ),
        ]
        marks = {
            (date(2024, 6, 15), "polymarket", "mkt1", "tok1"): 0.55,
            (date(2024, 6, 16), "polymarket", "mkt1", "tok1"): 0.70,
        }
        result = _replay_fills_to_snapshots(
            "0xA",
            [date(2024, 6, 15), date(2024, 6, 16)],
            {},
            fills,
            marks,
        )
        # Day 1: position open.  Day 2: position closed → no row.
        assert result.num_rows == 1
        row = result.to_pylist()[0]
        assert row["day_utc"] == date(2024, 6, 15)

    def test_missing_mark_produces_nan(self) -> None:
        """Positions without a mark get NaN values."""
        initial = {
            ("polymarket", "mkt1", "tok1"): {"qty": 100.0, "avg_cost": 0.50},
        }
        result = _replay_fills_to_snapshots(
            "0xA", [date(2024, 6, 15)], initial, [], {}
        )
        assert result.num_rows == 1
        row = result.to_pylist()[0]
        assert row["mark_price"] != row["mark_price"]  # NaN check

    def test_empty_range(self) -> None:
        result = _replay_fills_to_snapshots("0xA", [], {}, [], {})
        assert result.num_rows == 0
        assert result.schema == SNAPSHOT_SCHEMA

    def test_schema_matches(self) -> None:
        fills = [
            _make_fill(ts=datetime(2024, 6, 15, 10, 0, 0), qty_after=10.0),
        ]
        marks = {(date(2024, 6, 15), "polymarket", "mkt1", "tok1"): 0.50}
        result = _replay_fills_to_snapshots("0xA", [date(2024, 6, 15)], {}, fills, marks)
        assert result.schema == SNAPSHOT_SCHEMA


# ---------------------------------------------------------------------------
# compute_wallet_snapshots
# ---------------------------------------------------------------------------


class TestComputeWalletSnapshots:
    def _make_ch_mock(
        self,
        initial_rows: list | None = None,
        fill_rows: list | None = None,
        mark_rows: list | None = None,
    ) -> MagicMock:
        mock_ch = MagicMock()

        def query_side_effect(query: str, **kwargs: object) -> MagicMock:  # noqa: ARG001
            result = MagicMock()
            if "before_date" in query:
                # _read_initial_positions
                result.result_rows = initial_rows or []
            elif "wallet_position_ledger" in query:
                # _read_ledger_for_wallet
                result.result_rows = fill_rows or []
            elif "market_mark_daily" in query:
                result.result_rows = mark_rows or []
            else:
                result.result_rows = []
            return result

        mock_ch.query.side_effect = query_side_effect
        return mock_ch

    def test_dry_run_returns_table(self) -> None:
        mock_ch = self._make_ch_mock(
            fill_rows=[
                (datetime(2024, 6, 15, 10), "polymarket", "mkt1", "tok1", "buy", 100, 0.5, 0, 0.5, 100),
            ],
            mark_rows=[
                (date(2024, 6, 15), "polymarket", "mkt1", "tok1", 0.6),
            ],
        )
        result = compute_wallet_snapshots(
            wallet="0xA",
            start_date=date(2024, 6, 15),
            end_date=date(2024, 6, 15),
            clickhouse_client=mock_ch,
            dry_run=True,
        )
        assert result.num_rows == 1
        row = result.to_pylist()[0]
        assert row["wallet"] == "0xA"
        assert abs(row["position_value_usd"] - 60.0) < 1e-9

    def test_partial_existing_only_computes_missing(self) -> None:
        """When some partitions exist in S3, only missing days are computed."""
        mock_ch = self._make_ch_mock(
            initial_rows=[("polymarket", "mkt1", "tok1", 100.0, 0.50)],
            mark_rows=[
                (date(2024, 6, 16), "polymarket", "mkt1", "tok1", 0.70),
            ],
        )
        mock_s3 = MagicMock()

        # Day 15 exists, day 16 doesn't.
        def fake_paginate(Bucket: str, Prefix: str) -> list:  # noqa: ARG001, N803
            if "day=2024-06-15" in Prefix:
                return [{"Contents": [{"Key": "gold/wallet_position_snapshot_daily/day=2024-06-15/part-000.parquet"}]}]
            return [{}]

        paginator = MagicMock()
        paginator.paginate.side_effect = fake_paginate
        mock_s3.get_paginator.return_value = paginator

        result = compute_wallet_snapshots(
            wallet="0xA",
            start_date=date(2024, 6, 15),
            end_date=date(2024, 6, 16),
            gold_bucket="test-gold",
            s3_client=mock_s3,
            clickhouse_client=mock_ch,
        )
        # Only day 16 computed.
        days = [row["day_utc"] for row in result.to_pylist()]
        assert date(2024, 6, 15) not in days
        assert date(2024, 6, 16) in days

    def test_no_fills_carry_forward(self) -> None:
        """Wallet with positions but no fills in range carries forward."""
        mock_ch = self._make_ch_mock(
            initial_rows=[("polymarket", "mkt1", "tok1", 50.0, 0.40)],
            fill_rows=[],
            mark_rows=[
                (date(2024, 6, 15), "polymarket", "mkt1", "tok1", 0.60),
            ],
        )
        result = compute_wallet_snapshots(
            wallet="0xA",
            start_date=date(2024, 6, 15),
            end_date=date(2024, 6, 15),
            clickhouse_client=mock_ch,
            dry_run=True,
        )
        assert result.num_rows == 1
        row = result.to_pylist()[0]
        assert row["qty"] == 50.0
        assert abs(row["position_value_usd"] - 30.0) < 1e-9  # 50 * 0.60

    def test_all_partitions_exist_returns_empty(self) -> None:
        """When all partitions exist, returns empty table."""
        mock_ch = MagicMock()
        # Should not even be called for fill/mark queries.
        mock_ch.query.return_value.result_rows = []

        mock_s3 = MagicMock()
        paginator = MagicMock()
        paginator.paginate.return_value = [{"Contents": [{"Key": "x.parquet"}]}]
        mock_s3.get_paginator.return_value = paginator

        result = compute_wallet_snapshots(
            wallet="0xA",
            start_date=date(2024, 6, 15),
            end_date=date(2024, 6, 15),
            gold_bucket="test-gold",
            s3_client=mock_s3,
            clickhouse_client=mock_ch,
        )
        assert result.num_rows == 0
