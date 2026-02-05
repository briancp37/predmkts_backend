"""Tests for the wallet_position_state module."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pyarrow as pa
import pytest

from prediction_data.gold.accounting import PositionState
from prediction_data.gold.fill_splitter import Fill
from prediction_data.gold.ledger import build_ledger_for_day
from prediction_data.gold.position_state import (
    POSITION_STATE_COLUMNS,
    POSITION_STATE_SCHEMA,
    positions_to_arrow,
    read_position_states,
    write_position_states,
)


def _ts(minute: int = 0) -> datetime:
    """Helper to create test timestamps."""
    return datetime(2024, 6, 15, 12, minute, 0, tzinfo=UTC)


def _fill(
    *,
    ts: datetime | None = None,
    wallet: str = "0xABC",
    platform: str = "polymarket",
    market_id: str = "m1",
    outcome_id: str = "m1_0",
    side: str = "buy",
    qty_delta: float = 100.0,
    price: float = 0.60,
    fees_usd: float = 0.0,
) -> Fill:
    """Helper to create a Fill."""
    return Fill(
        ts=ts or _ts(),
        wallet=wallet,
        platform=platform,
        market_id=market_id,
        outcome_id=outcome_id,
        side=side,
        qty_delta=qty_delta,
        price=price,
        fees_usd=fees_usd,
    )


def _pos(
    *,
    wallet: str = "0xABC",
    platform: str = "polymarket",
    market_id: str = "m1",
    outcome_id: str = "m1_0",
) -> PositionState:
    """Helper to create a fresh PositionState."""
    return PositionState(
        wallet=wallet, platform=platform, market_id=market_id, outcome_id=outcome_id
    )


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestSchema:
    def test_schema_field_count(self) -> None:
        assert len(POSITION_STATE_SCHEMA) == 9

    def test_columns_match_schema(self) -> None:
        assert [f.name for f in POSITION_STATE_SCHEMA] == POSITION_STATE_COLUMNS

    def test_schema_field_names(self) -> None:
        expected = [
            "wallet",
            "platform",
            "market_id",
            "outcome_id",
            "qty",
            "avg_cost",
            "cost_basis_usd",
            "last_fill_ts",
            "first_open_ts",
        ]
        assert expected == POSITION_STATE_COLUMNS

    def test_timestamp_fields_are_microsecond_utc(self) -> None:
        for name in ("last_fill_ts", "first_open_ts"):
            field = POSITION_STATE_SCHEMA.field(name)
            assert field.type == pa.timestamp("us", tz="UTC")


# ---------------------------------------------------------------------------
# positions_to_arrow tests
# ---------------------------------------------------------------------------


class TestPositionsToArrow:
    def test_empty_positions(self) -> None:
        table = positions_to_arrow({})
        assert table.num_rows == 0
        assert table.schema == POSITION_STATE_SCHEMA

    def test_single_open_position(self) -> None:
        pos = _pos()
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))
        key = ("0xABC", "polymarket", "m1", "m1_0")

        table = positions_to_arrow({key: pos})
        assert table.num_rows == 1
        row = table.to_pylist()[0]

        assert row["wallet"] == "0xABC"
        assert row["platform"] == "polymarket"
        assert row["market_id"] == "m1"
        assert row["outcome_id"] == "m1_0"
        assert row["qty"] == pytest.approx(100.0)
        assert row["avg_cost"] == pytest.approx(0.60)
        assert row["cost_basis_usd"] == pytest.approx(60.0)
        assert row["last_fill_ts"] == _ts(0)
        assert row["first_open_ts"] == _ts(0)

    def test_closed_position_included(self) -> None:
        """Closed positions (qty=0) should still be included for ReplacingMergeTree."""
        pos = _pos()
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))
        pos.apply_fill("sell", 100.0, 0.80, 0.0, _ts(1))
        key = ("0xABC", "polymarket", "m1", "m1_0")

        table = positions_to_arrow({key: pos})
        assert table.num_rows == 1
        row = table.to_pylist()[0]
        assert row["qty"] == pytest.approx(0.0)

    def test_position_without_last_fill_ts_skipped(self) -> None:
        """A position that was never filled (no last_fill_ts) should be skipped."""
        pos = _pos()
        key = ("0xABC", "polymarket", "m1", "m1_0")

        table = positions_to_arrow({key: pos})
        assert table.num_rows == 0

    def test_multiple_positions(self) -> None:
        pos1 = _pos(wallet="0xAAA")
        pos1.apply_fill("buy", 100.0, 0.50, 0.0, _ts(0))
        pos2 = _pos(wallet="0xBBB", market_id="m2", outcome_id="m2_0")
        pos2.apply_fill("buy", 200.0, 0.70, 0.0, _ts(1))

        positions = {
            ("0xAAA", "polymarket", "m1", "m1_0"): pos1,
            ("0xBBB", "polymarket", "m2", "m2_0"): pos2,
        }
        table = positions_to_arrow(positions)
        assert table.num_rows == 2

        rows_by_wallet = {r["wallet"]: r for r in table.to_pylist()}
        assert rows_by_wallet["0xAAA"]["qty"] == pytest.approx(100.0)
        assert rows_by_wallet["0xBBB"]["qty"] == pytest.approx(200.0)

    def test_arrow_schema_matches(self) -> None:
        pos = _pos()
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))
        key = ("0xABC", "polymarket", "m1", "m1_0")

        table = positions_to_arrow({key: pos})
        assert table.schema == POSITION_STATE_SCHEMA


# ---------------------------------------------------------------------------
# write_position_states tests
# ---------------------------------------------------------------------------


class TestWritePositionStates:
    def test_empty_positions(self) -> None:
        count = write_position_states({})
        assert count == 0

    def test_dry_run(self) -> None:
        pos = _pos()
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))
        key = ("0xABC", "polymarket", "m1", "m1_0")

        count = write_position_states({key: pos}, dry_run=True)
        assert count == 1

    def test_writes_to_clickhouse(self) -> None:
        pos = _pos()
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))
        key = ("0xABC", "polymarket", "m1", "m1_0")

        mock_ch = MagicMock()
        count = write_position_states({key: pos}, clickhouse_client=mock_ch)

        assert count == 1
        mock_ch.insert.assert_called_once()
        insert_args = mock_ch.insert.call_args
        assert insert_args[0][0] == "wallet_position_state"
        assert insert_args[1]["column_names"] == POSITION_STATE_COLUMNS

    def test_insert_data_matches(self) -> None:
        pos = _pos()
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))
        key = ("0xABC", "polymarket", "m1", "m1_0")

        mock_ch = MagicMock()
        write_position_states({key: pos}, clickhouse_client=mock_ch)

        data = mock_ch.insert.call_args[1]["data"]
        assert len(data) == 1
        assert data[0]["wallet"] == "0xABC"
        assert data[0]["qty"] == pytest.approx(100.0)
        assert data[0]["avg_cost"] == pytest.approx(0.60)

    def test_unfilled_positions_not_written(self) -> None:
        """Positions with no last_fill_ts should not be written."""
        pos = _pos()
        key = ("0xABC", "polymarket", "m1", "m1_0")

        mock_ch = MagicMock()
        count = write_position_states({key: pos}, clickhouse_client=mock_ch)
        assert count == 0
        mock_ch.insert.assert_not_called()


# ---------------------------------------------------------------------------
# read_position_states tests
# ---------------------------------------------------------------------------


class TestReadPositionStates:
    def test_empty_result(self) -> None:
        mock_ch = MagicMock()
        mock_ch.query.return_value.result_rows = []

        positions = read_position_states(clickhouse_client=mock_ch)
        assert positions == {}

    def test_reads_open_positions(self) -> None:
        mock_ch = MagicMock()
        mock_ch.query.return_value.result_rows = [
            ("0xAAA", "polymarket", "m1", "m1_0", 100.0, 0.60, 60.0, _ts(5), _ts(0)),
        ]

        positions = read_position_states(clickhouse_client=mock_ch)
        assert len(positions) == 1
        key = ("0xAAA", "polymarket", "m1", "m1_0")
        assert key in positions
        pos = positions[key]
        assert pos.wallet == "0xAAA"
        assert pos.qty == pytest.approx(100.0)
        assert pos.avg_cost == pytest.approx(0.60)
        assert pos.cost_basis_usd == pytest.approx(60.0)
        assert pos.last_fill_ts == _ts(5)
        assert pos.first_open_ts == _ts(0)

    def test_query_uses_final_and_qty_filter(self) -> None:
        mock_ch = MagicMock()
        mock_ch.query.return_value.result_rows = []

        read_position_states(clickhouse_client=mock_ch)

        query = mock_ch.query.call_args[0][0]
        assert "FINAL" in query
        assert "qty != 0" in query

    def test_multiple_positions(self) -> None:
        mock_ch = MagicMock()
        mock_ch.query.return_value.result_rows = [
            ("0xAAA", "polymarket", "m1", "m1_0", 100.0, 0.50, 50.0, _ts(3), _ts(0)),
            ("0xBBB", "polymarket", "m2", "m2_0", 200.0, 0.70, 140.0, _ts(5), _ts(1)),
        ]

        positions = read_position_states(clickhouse_client=mock_ch)
        assert len(positions) == 2
        assert ("0xAAA", "polymarket", "m1", "m1_0") in positions
        assert ("0xBBB", "polymarket", "m2", "m2_0") in positions


# ---------------------------------------------------------------------------
# first_open_ts tracking in PositionState
# ---------------------------------------------------------------------------


class TestFirstOpenTs:
    def test_set_on_open(self) -> None:
        pos = _pos()
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))
        assert pos.first_open_ts == _ts(0)

    def test_unchanged_on_subsequent_fills(self) -> None:
        """first_open_ts should not change when adding to an existing position."""
        pos = _pos()
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))
        pos.apply_fill("buy", 50.0, 0.70, 0.0, _ts(5))
        assert pos.first_open_ts == _ts(0)

    def test_unchanged_on_partial_sell(self) -> None:
        pos = _pos()
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))
        pos.apply_fill("sell", 40.0, 0.80, 0.0, _ts(5))
        assert pos.first_open_ts == _ts(0)

    def test_cleared_on_close(self) -> None:
        pos = _pos()
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))
        pos.apply_fill("sell", 100.0, 0.80, 0.0, _ts(5))
        assert pos.qty == 0.0
        assert pos.first_open_ts is None

    def test_reset_on_reopen(self) -> None:
        """After closing and reopening, first_open_ts should be the new open time."""
        pos = _pos()
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))
        pos.apply_fill("sell", 100.0, 0.80, 0.0, _ts(5))
        assert pos.first_open_ts is None

        pos.apply_fill("buy", 50.0, 0.70, 0.0, _ts(10))
        assert pos.first_open_ts == _ts(10)

    def test_reset_on_flip(self) -> None:
        """Position flip should set first_open_ts to the flip timestamp."""
        pos = _pos()
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))
        assert pos.first_open_ts == _ts(0)

        pos.apply_fill("sell", 150.0, 0.80, 0.0, _ts(5))
        assert pos.qty == pytest.approx(-50.0)
        assert pos.first_open_ts == _ts(5)

    def test_short_position_open_ts(self) -> None:
        """Opening a short position directly should set first_open_ts."""
        pos = _pos()
        pos.apply_fill("sell", 100.0, 0.60, 0.0, _ts(0))
        assert pos.qty == pytest.approx(-100.0)
        assert pos.first_open_ts == _ts(0)


# ---------------------------------------------------------------------------
# Integration with ledger
# ---------------------------------------------------------------------------


class TestIntegrationWithLedger:
    def test_ledger_then_position_state(self) -> None:
        """Process fills through ledger, then write position states."""
        fills = [
            _fill(ts=_ts(0), wallet="0xAAA", side="buy", qty_delta=100.0, price=0.50),
            _fill(ts=_ts(1), wallet="0xBBB", side="buy", qty_delta=200.0, price=0.70),
            _fill(ts=_ts(2), wallet="0xAAA", side="sell", qty_delta=40.0, price=0.80),
        ]

        writer, positions = build_ledger_for_day(fills, {})
        assert writer.count == 3

        table = positions_to_arrow(positions)
        assert table.num_rows == 2

        rows_by_wallet = {r["wallet"]: r for r in table.to_pylist()}
        assert rows_by_wallet["0xAAA"]["qty"] == pytest.approx(60.0)
        assert rows_by_wallet["0xAAA"]["avg_cost"] == pytest.approx(0.50)
        assert rows_by_wallet["0xBBB"]["qty"] == pytest.approx(200.0)
        assert rows_by_wallet["0xBBB"]["avg_cost"] == pytest.approx(0.70)

    def test_closed_position_in_arrow_after_ledger(self) -> None:
        """A position closed during ledger processing should appear in arrow with qty=0."""
        fills = [
            _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.50),
            _fill(ts=_ts(1), side="sell", qty_delta=100.0, price=0.80),
        ]

        _, positions = build_ledger_for_day(fills, {})
        table = positions_to_arrow(positions)
        assert table.num_rows == 1
        row = table.to_pylist()[0]
        assert row["qty"] == pytest.approx(0.0)

    def test_trade_to_fills_to_position_state(self) -> None:
        """Full pipeline: trade → fills → ledger → position state."""
        from prediction_data.gold.fill_splitter import trades_to_fills

        trade = {
            "event_ts": _ts(0),
            "platform_market_id": "0xMKT",
            "maker": "0xMAKER",
            "taker": "0xTAKER",
            "nonusdc_side": "token1",
            "maker_direction": "sell",
            "taker_direction": "buy",
            "token_amount": 100.0,
            "price": 0.60,
        }
        fills = trades_to_fills([trade])
        _, positions = build_ledger_for_day(fills, {})

        table = positions_to_arrow(positions)
        assert table.num_rows == 2

        rows_by_wallet = {r["wallet"]: r for r in table.to_pylist()}
        # Maker sold → short position
        assert rows_by_wallet["0xMAKER"]["qty"] == pytest.approx(-100.0)
        assert rows_by_wallet["0xMAKER"]["avg_cost"] == pytest.approx(0.60)
        # Taker bought → long position
        assert rows_by_wallet["0xTAKER"]["qty"] == pytest.approx(100.0)
        assert rows_by_wallet["0xTAKER"]["avg_cost"] == pytest.approx(0.60)


# ---------------------------------------------------------------------------
# Downstream compatibility
# ---------------------------------------------------------------------------


class TestDownstreamCompatibility:
    def test_position_state_has_fields_for_mtm(self) -> None:
        """wallet_mtm.py queries: wallet, platform, market_id, outcome_id, qty, avg_cost."""
        required = {"wallet", "platform", "market_id", "outcome_id", "qty", "avg_cost"}
        assert required.issubset(set(POSITION_STATE_COLUMNS))

    def test_position_state_has_fields_for_snapshot(self) -> None:
        """wallet_position_snapshot.py queries the same fields as MTM."""
        required = {"wallet", "platform", "market_id", "outcome_id", "qty", "avg_cost"}
        assert required.issubset(set(POSITION_STATE_COLUMNS))

    def test_arrow_to_pylist_compatible_with_ch_insert(self) -> None:
        """to_pylist() should produce dicts with all POSITION_STATE_COLUMNS keys."""
        pos = _pos()
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))
        key = ("0xABC", "polymarket", "m1", "m1_0")

        table = positions_to_arrow({key: pos})
        row_dicts = table.to_pylist()
        assert len(row_dicts) == 1
        assert set(row_dicts[0].keys()) == set(POSITION_STATE_COLUMNS)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_small_quantities(self) -> None:
        pos = _pos()
        pos.apply_fill("buy", 0.001, 0.50, 0.0, _ts(0))
        key = ("0xABC", "polymarket", "m1", "m1_0")

        table = positions_to_arrow({key: pos})
        row = table.to_pylist()[0]
        assert row["qty"] == pytest.approx(0.001)

    def test_price_boundaries(self) -> None:
        pos = _pos()
        pos.apply_fill("buy", 100.0, 0.0, 0.0, _ts(0))
        key = ("0xABC", "polymarket", "m1", "m1_0")

        table = positions_to_arrow({key: pos})
        row = table.to_pylist()[0]
        assert row["avg_cost"] == pytest.approx(0.0)
        assert row["cost_basis_usd"] == pytest.approx(0.0)

    def test_multiple_outcomes_same_market(self) -> None:
        pos1 = _pos(outcome_id="m1_0")
        pos1.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))
        pos2 = _pos(outcome_id="m1_1")
        pos2.apply_fill("buy", 50.0, 0.40, 0.0, _ts(1))

        positions = {
            ("0xABC", "polymarket", "m1", "m1_0"): pos1,
            ("0xABC", "polymarket", "m1", "m1_1"): pos2,
        }
        table = positions_to_arrow(positions)
        assert table.num_rows == 2

        rows_by_outcome = {r["outcome_id"]: r for r in table.to_pylist()}
        assert rows_by_outcome["m1_0"]["qty"] == pytest.approx(100.0)
        assert rows_by_outcome["m1_1"]["qty"] == pytest.approx(50.0)

    def test_negative_qty_short_position(self) -> None:
        pos = _pos()
        pos.apply_fill("sell", 100.0, 0.60, 0.0, _ts(0))
        key = ("0xABC", "polymarket", "m1", "m1_0")

        table = positions_to_arrow({key: pos})
        row = table.to_pylist()[0]
        assert row["qty"] == pytest.approx(-100.0)
