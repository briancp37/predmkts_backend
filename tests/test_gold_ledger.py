"""Tests for the wallet_position_ledger module."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pyarrow as pa
import pytest

from prediction_data.gold.accounting import PositionState
from prediction_data.gold.fill_splitter import Fill
from prediction_data.gold.ledger import (
    LEDGER_COLUMNS,
    LEDGER_SCHEMA,
    LedgerRow,
    LedgerWriter,
    build_ledger_for_day,
    record_fill,
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


class TestLedgerRow:
    def test_frozen(self) -> None:
        row = LedgerRow(
            ts=_ts(),
            wallet="0xABC",
            platform="polymarket",
            market_id="m1",
            outcome_id="m1_0",
            side="buy",
            qty_delta=100.0,
            price=0.60,
            fees_usd=0.0,
            qty_before=0.0,
            qty_after=100.0,
            avg_cost_before=0.0,
            avg_cost_after=0.60,
            realized_pnl_this_fill_usd=0.0,
        )
        with pytest.raises(AttributeError):
            row.qty_after = 999.0  # type: ignore[misc]


class TestRecordFill:
    def test_opening_buy(self) -> None:
        """Opening buy should capture before=0, after=qty."""
        pos = _pos()
        result, row = record_fill(pos, _fill(side="buy", qty_delta=100.0, price=0.60))

        assert result.realized_pnl == 0.0
        assert not result.closed
        assert row.qty_before == 0.0
        assert row.qty_after == 100.0
        assert row.avg_cost_before == 0.0
        assert row.avg_cost_after == pytest.approx(0.60)
        assert row.realized_pnl_this_fill_usd == 0.0

    def test_partial_sell_captures_before_after(self) -> None:
        """Partial sell should capture before/after state correctly."""
        pos = _pos()
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))

        result, row = record_fill(
            pos, _fill(ts=_ts(1), side="sell", qty_delta=40.0, price=0.80)
        )

        assert row.qty_before == 100.0
        assert row.qty_after == 60.0
        assert row.avg_cost_before == pytest.approx(0.60)
        assert row.avg_cost_after == pytest.approx(0.60)
        assert row.realized_pnl_this_fill_usd == pytest.approx(8.0)

    def test_close_position(self) -> None:
        """Closing a position should show qty_after=0."""
        pos = _pos()
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))

        result, row = record_fill(
            pos, _fill(ts=_ts(1), side="sell", qty_delta=100.0, price=0.80)
        )

        assert result.closed
        assert row.qty_before == 100.0
        assert row.qty_after == 0.0
        assert row.realized_pnl_this_fill_usd == pytest.approx(20.0)

    def test_position_flip(self) -> None:
        """Flip should close existing and open new direction."""
        pos = _pos()
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))

        result, row = record_fill(
            pos, _fill(ts=_ts(1), side="sell", qty_delta=150.0, price=0.80)
        )

        assert row.qty_before == 100.0
        assert row.qty_after == -50.0
        assert row.avg_cost_before == pytest.approx(0.60)
        assert row.avg_cost_after == pytest.approx(0.80)
        assert row.realized_pnl_this_fill_usd == pytest.approx(20.0)

    def test_fill_fields_propagated(self) -> None:
        """All fill fields should be copied to the ledger row."""
        fill = _fill(
            ts=_ts(5),
            wallet="0xDEF",
            platform="kalshi",
            market_id="mkt42",
            outcome_id="mkt42_1",
            side="buy",
            qty_delta=50.0,
            price=0.75,
            fees_usd=1.5,
        )
        pos = PositionState(
            wallet="0xDEF", platform="kalshi", market_id="mkt42", outcome_id="mkt42_1"
        )
        _, row = record_fill(pos, fill)

        assert row.ts == _ts(5)
        assert row.wallet == "0xDEF"
        assert row.platform == "kalshi"
        assert row.market_id == "mkt42"
        assert row.outcome_id == "mkt42_1"
        assert row.side == "buy"
        assert row.qty_delta == 50.0
        assert row.price == 0.75
        assert row.fees_usd == 1.5

    def test_fees_on_sell(self) -> None:
        """Fees should reduce realized PnL."""
        pos = _pos()
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))

        _, row = record_fill(
            pos, _fill(ts=_ts(1), side="sell", qty_delta=100.0, price=0.80, fees_usd=2.0)
        )

        assert row.realized_pnl_this_fill_usd == pytest.approx(18.0)


class TestLedgerWriter:
    def test_empty_writer(self) -> None:
        writer = LedgerWriter()
        assert writer.count == 0
        assert writer.rows == []

    def test_record_accumulates(self) -> None:
        writer = LedgerWriter()
        pos = _pos()
        writer.record(pos, _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.60))
        writer.record(pos, _fill(ts=_ts(1), side="sell", qty_delta=50.0, price=0.80))

        assert writer.count == 2
        rows = writer.rows
        assert len(rows) == 2
        assert rows[0].side == "buy"
        assert rows[1].side == "sell"

    def test_record_returns_result_and_row(self) -> None:
        writer = LedgerWriter()
        pos = _pos()
        result, row = writer.record(
            pos, _fill(side="buy", qty_delta=100.0, price=0.60)
        )

        assert result.realized_pnl == 0.0
        assert not result.closed
        assert row.qty_after == 100.0

    def test_rows_is_copy(self) -> None:
        """rows property should return a copy, not the internal list."""
        writer = LedgerWriter()
        pos = _pos()
        writer.record(pos, _fill())
        rows = writer.rows
        rows.clear()
        assert writer.count == 1

    def test_clear(self) -> None:
        writer = LedgerWriter()
        pos = _pos()
        writer.record(pos, _fill())
        assert writer.count == 1
        writer.clear()
        assert writer.count == 0
        assert writer.rows == []

    def test_to_arrow_empty(self) -> None:
        writer = LedgerWriter()
        table = writer.to_arrow()
        assert table.num_rows == 0
        assert table.schema == LEDGER_SCHEMA

    def test_to_arrow_schema(self) -> None:
        writer = LedgerWriter()
        pos = _pos()
        writer.record(pos, _fill(side="buy", qty_delta=100.0, price=0.60))
        table = writer.to_arrow()

        assert table.num_rows == 1
        assert table.schema == LEDGER_SCHEMA
        assert table.column_names == LEDGER_COLUMNS

    def test_to_arrow_values(self) -> None:
        writer = LedgerWriter()
        pos = _pos()
        writer.record(pos, _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.60))
        writer.record(
            pos, _fill(ts=_ts(1), side="sell", qty_delta=40.0, price=0.80)
        )

        table = writer.to_arrow()
        rows = table.to_pylist()

        assert len(rows) == 2
        assert rows[0]["wallet"] == "0xABC"
        assert rows[0]["side"] == "buy"
        assert rows[0]["qty_before"] == 0.0
        assert rows[0]["qty_after"] == 100.0
        assert rows[1]["side"] == "sell"
        assert rows[1]["qty_before"] == 100.0
        assert rows[1]["qty_after"] == 60.0
        assert rows[1]["realized_pnl_this_fill_usd"] == pytest.approx(8.0)

    def test_to_arrow_timestamp_type(self) -> None:
        """Timestamps should be stored as microsecond UTC."""
        writer = LedgerWriter()
        pos = _pos()
        writer.record(pos, _fill(ts=_ts(0)))
        table = writer.to_arrow()
        ts_type = table.schema.field("ts").type
        assert ts_type == pa.timestamp("us", tz="UTC")


class TestLedgerWriterFlush:
    def test_flush_empty(self) -> None:
        writer = LedgerWriter()
        count = writer.flush(day="2024-06-15")
        assert count == 0

    def test_flush_dry_run(self) -> None:
        writer = LedgerWriter()
        pos = _pos()
        writer.record(pos, _fill())
        count = writer.flush(day="2024-06-15", dry_run=True)
        assert count == 1

    def test_flush_writes_to_s3_and_ch(self) -> None:
        writer = LedgerWriter()
        pos = _pos()
        writer.record(pos, _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.60))

        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value.paginate.return_value = [
            {"Contents": []}
        ]
        mock_ch = MagicMock()

        with patch("prediction_data.gold.s3_writer.write_gold_parquet") as mock_write:
            count = writer.flush(
                gold_bucket="test-bucket",
                day="2024-06-15",
                s3_client=mock_s3,
                clickhouse_client=mock_ch,
            )

        assert count == 1
        mock_write.assert_called_once()
        call_args = mock_write.call_args
        assert call_args[0][1] == "test-bucket"
        assert call_args[0][2] == "wallet_position_ledger"
        assert call_args[0][3] == "2024-06-15"

        mock_ch.insert.assert_called_once()
        insert_args = mock_ch.insert.call_args
        assert insert_args[0][0] == "wallet_position_ledger"
        assert insert_args[1]["column_names"] == LEDGER_COLUMNS

    def test_flush_no_s3_without_bucket(self) -> None:
        writer = LedgerWriter()
        pos = _pos()
        writer.record(pos, _fill())

        mock_ch = MagicMock()
        with patch("prediction_data.gold.s3_writer.write_gold_parquet") as mock_write:
            writer.flush(
                day="2024-06-15",
                clickhouse_client=mock_ch,
            )

        mock_write.assert_not_called()
        mock_ch.insert.assert_called_once()

    def test_flush_ch_data_matches_arrow(self) -> None:
        """Data inserted into CH should match the Arrow table contents."""
        writer = LedgerWriter()
        pos = _pos()
        writer.record(pos, _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.60))
        writer.record(pos, _fill(ts=_ts(1), side="sell", qty_delta=100.0, price=0.80))

        mock_ch = MagicMock()
        writer.flush(day="2024-06-15", clickhouse_client=mock_ch)

        insert_data = mock_ch.insert.call_args[1]["data"]
        assert len(insert_data) == 2
        assert insert_data[0]["side"] == "buy"
        assert insert_data[1]["side"] == "sell"
        assert insert_data[1]["realized_pnl_this_fill_usd"] == pytest.approx(20.0)


class TestBuildLedgerForDay:
    def test_empty_fills(self) -> None:
        writer, positions = build_ledger_for_day([], {})
        assert writer.count == 0
        assert positions == {}

    def test_single_fill_creates_position(self) -> None:
        fills = [_fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.60)]
        writer, positions = build_ledger_for_day(fills, {})

        assert writer.count == 1
        key = ("0xABC", "polymarket", "m1", "m1_0")
        assert key in positions
        assert positions[key].qty == 100.0
        assert positions[key].avg_cost == pytest.approx(0.60)

    def test_multiple_fills_same_position(self) -> None:
        """Multiple fills for the same wallet/market should accumulate."""
        fills = [
            _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.60),
            _fill(ts=_ts(1), side="buy", qty_delta=50.0, price=0.90),
        ]
        writer, positions = build_ledger_for_day(fills, {})

        assert writer.count == 2
        key = ("0xABC", "polymarket", "m1", "m1_0")
        assert positions[key].qty == 150.0
        assert positions[key].avg_cost == pytest.approx(0.70)

    def test_multiple_wallets(self) -> None:
        """Fills for different wallets should create separate positions."""
        fills = [
            _fill(ts=_ts(0), wallet="0xAAA", side="buy", qty_delta=100.0, price=0.50),
            _fill(ts=_ts(1), wallet="0xBBB", side="buy", qty_delta=200.0, price=0.70),
        ]
        writer, positions = build_ledger_for_day(fills, {})

        assert writer.count == 2
        assert len(positions) == 2
        assert positions[("0xAAA", "polymarket", "m1", "m1_0")].qty == 100.0
        assert positions[("0xBBB", "polymarket", "m1", "m1_0")].qty == 200.0

    def test_reuses_existing_positions(self) -> None:
        """Pre-existing positions should be reused, not replaced."""
        existing_pos = _pos()
        existing_pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))
        key = ("0xABC", "polymarket", "m1", "m1_0")
        positions: dict[tuple[str, str, str, str], PositionState] = {key: existing_pos}

        fills = [
            _fill(ts=_ts(5), side="sell", qty_delta=40.0, price=0.80),
        ]
        writer, positions = build_ledger_for_day(fills, positions)

        assert writer.count == 1
        rows = writer.rows
        assert rows[0].qty_before == 100.0
        assert rows[0].qty_after == 60.0
        assert rows[0].realized_pnl_this_fill_usd == pytest.approx(8.0)
        assert positions[key].qty == 60.0

    def test_ledger_arrow_matches_rows(self) -> None:
        """Arrow table should contain the same data as the LedgerRow list."""
        fills = [
            _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.60),
            _fill(ts=_ts(1), side="sell", qty_delta=100.0, price=0.80),
        ]
        writer, _ = build_ledger_for_day(fills, {})
        table = writer.to_arrow()
        arrow_rows = table.to_pylist()

        assert len(arrow_rows) == 2
        assert arrow_rows[0]["qty_before"] == 0.0
        assert arrow_rows[0]["qty_after"] == 100.0
        assert arrow_rows[1]["qty_before"] == 100.0
        assert arrow_rows[1]["qty_after"] == 0.0
        assert arrow_rows[1]["realized_pnl_this_fill_usd"] == pytest.approx(20.0)


class TestIntegrationWithFillSplitter:
    """End-to-end: Silver trade → fills → ledger with correct PnL."""

    def test_trade_to_ledger_round_trip(self) -> None:
        """A matched trade should produce 2 ledger rows (maker + taker)."""
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
        assert len(fills) == 2

        writer, positions = build_ledger_for_day(fills, {})
        assert writer.count == 2

        rows = writer.rows
        # Both fills are for different wallets
        wallets = {r.wallet for r in rows}
        assert wallets == {"0xMAKER", "0xTAKER"}

        # Maker: sell 100 @ 0.60 (opening short from zero)
        maker_row = next(r for r in rows if r.wallet == "0xMAKER")
        assert maker_row.side == "sell"
        assert maker_row.qty_before == 0.0
        assert maker_row.qty_after == -100.0
        assert maker_row.avg_cost_after == pytest.approx(0.60)

        # Taker: buy 100 @ 0.60 (opening long from zero)
        taker_row = next(r for r in rows if r.wallet == "0xTAKER")
        assert taker_row.side == "buy"
        assert taker_row.qty_before == 0.0
        assert taker_row.qty_after == 100.0
        assert taker_row.avg_cost_after == pytest.approx(0.60)

    def test_multi_trade_sequence_pnl(self) -> None:
        """Process multiple trades and verify cumulative PnL in ledger.

        Trade 1: TAKER buys 100 @ 0.50 from MAKER
        Trade 2: TAKER sells 100 @ 0.80 to MAKER2
        TAKER should have realized PnL = 100 * (0.80 - 0.50) = 30.0.
        """
        from prediction_data.gold.fill_splitter import trades_to_fills

        trades = [
            {
                "event_ts": _ts(0),
                "platform_market_id": "0xMKT",
                "maker": "0xMAKER",
                "taker": "0xTAKER",
                "nonusdc_side": "token1",
                "maker_direction": "sell",
                "taker_direction": "buy",
                "token_amount": 100.0,
                "price": 0.50,
            },
            {
                "event_ts": _ts(5),
                "platform_market_id": "0xMKT",
                "maker": "0xMAKER2",
                "taker": "0xTAKER",
                "nonusdc_side": "token1",
                "maker_direction": "buy",
                "taker_direction": "sell",
                "token_amount": 100.0,
                "price": 0.80,
            },
        ]
        fills = trades_to_fills(trades)
        writer, positions = build_ledger_for_day(fills, {})

        # Find TAKER's sell row (the close)
        taker_rows = [r for r in writer.rows if r.wallet == "0xTAKER"]
        assert len(taker_rows) == 2

        taker_sell = next(r for r in taker_rows if r.side == "sell")
        assert taker_sell.qty_before == 100.0
        assert taker_sell.qty_after == 0.0
        assert taker_sell.realized_pnl_this_fill_usd == pytest.approx(30.0)

        # TAKER position should be closed
        taker_key = ("0xTAKER", "polymarket", "0xMKT", "0xMKT_0")
        assert positions[taker_key].qty == 0.0


class TestDownstreamCompatibility:
    """Verify the ledger schema produces fields expected by wallet_pnl and on_demand."""

    def test_wallet_pnl_fields_present(self) -> None:
        """wallet_pnl.py reads: wallet, qty_delta, price, fees_usd, realized_pnl_this_fill_usd."""
        required = {"wallet", "qty_delta", "price", "fees_usd", "realized_pnl_this_fill_usd"}
        assert required.issubset(set(LEDGER_COLUMNS))

    def test_on_demand_fields_present(self) -> None:
        """on_demand.py reads: ts, platform, market_id, outcome_id, side,
        qty_delta, price, fees_usd, avg_cost_after, qty_after."""
        required = {
            "ts", "platform", "market_id", "outcome_id", "side",
            "qty_delta", "price", "fees_usd", "avg_cost_after", "qty_after",
        }
        assert required.issubset(set(LEDGER_COLUMNS))

    def test_arrow_to_pylist_compatible_with_ch_insert(self) -> None:
        """to_pylist() should produce dicts with all LEDGER_COLUMNS keys."""
        writer = LedgerWriter()
        pos = _pos()
        writer.record(pos, _fill())
        table = writer.to_arrow()
        row_dicts = table.to_pylist()
        assert len(row_dicts) == 1
        assert set(row_dicts[0].keys()) == set(LEDGER_COLUMNS)


class TestEdgeCases:
    def test_position_flip_ledger_row(self) -> None:
        """Flip should produce a single ledger row with before/after reflecting the flip."""
        pos = _pos()
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(0))

        writer = LedgerWriter()
        writer.record(
            pos, _fill(ts=_ts(1), side="sell", qty_delta=150.0, price=0.80)
        )

        rows = writer.rows
        assert len(rows) == 1
        assert rows[0].qty_before == 100.0
        assert rows[0].qty_after == -50.0
        assert rows[0].realized_pnl_this_fill_usd == pytest.approx(20.0)

    def test_small_quantities(self) -> None:
        """Handle fractional token quantities correctly."""
        pos = _pos()
        writer = LedgerWriter()
        writer.record(pos, _fill(side="buy", qty_delta=0.001, price=0.50))
        writer.record(pos, _fill(ts=_ts(1), side="sell", qty_delta=0.001, price=0.60))

        rows = writer.rows
        assert rows[1].qty_after == pytest.approx(0.0)
        assert rows[1].realized_pnl_this_fill_usd == pytest.approx(0.0001)

    def test_price_boundaries(self) -> None:
        """Prices at 0 and 1 should work correctly."""
        pos = _pos()
        writer = LedgerWriter()
        writer.record(pos, _fill(side="buy", qty_delta=100.0, price=0.0))

        assert writer.rows[0].avg_cost_after == 0.0

        result, row = writer.record(
            pos, _fill(ts=_ts(1), side="sell", qty_delta=100.0, price=1.0)
        )
        assert row.realized_pnl_this_fill_usd == pytest.approx(100.0)

    def test_multiple_outcomes_same_market(self) -> None:
        """Different outcome IDs should create separate positions."""
        fills = [
            _fill(ts=_ts(0), outcome_id="m1_0", side="buy", qty_delta=100.0, price=0.60),
            _fill(ts=_ts(1), outcome_id="m1_1", side="buy", qty_delta=50.0, price=0.40),
        ]
        writer, positions = build_ledger_for_day(fills, {})

        assert len(positions) == 2
        assert positions[("0xABC", "polymarket", "m1", "m1_0")].qty == 100.0
        assert positions[("0xABC", "polymarket", "m1", "m1_1")].qty == 50.0

    def test_build_ledger_preserves_position_identity(self) -> None:
        """Positions passed in should be mutated in place, not replaced."""
        pos = _pos()
        key = ("0xABC", "polymarket", "m1", "m1_0")
        positions: dict[tuple[str, str, str, str], PositionState] = {key: pos}

        fills = [_fill(side="buy", qty_delta=100.0, price=0.60)]
        _, result_positions = build_ledger_for_day(fills, positions)

        assert result_positions[key] is pos
        assert pos.qty == 100.0
