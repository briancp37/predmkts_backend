"""Tests for Gold market_mark_daily computation."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pyarrow as pa

from prediction_data.gold.market_marks import (
    MARKET_MARK_DAILY_SCHEMA,
    MIN_TRADES_FOR_VWAP,
    compute_marks_for_day,
    compute_vwap,
)


# ---------------------------------------------------------------------------
# VWAP tests
# ---------------------------------------------------------------------------


class TestComputeVwap:
    def test_basic_vwap(self) -> None:
        # Two trades: price=0.5 @ $100, price=0.7 @ $300
        # VWAP = (0.5*100 + 0.7*300) / (100+300) = (50+210)/400 = 0.65
        result = compute_vwap([0.5, 0.7], [100.0, 300.0])
        assert result is not None
        assert abs(result - 0.65) < 1e-9

    def test_single_trade(self) -> None:
        result = compute_vwap([0.42], [50.0])
        assert result is not None
        assert abs(result - 0.42) < 1e-9

    def test_empty_inputs(self) -> None:
        assert compute_vwap([], []) is None

    def test_zero_volume(self) -> None:
        assert compute_vwap([0.5, 0.6], [0.0, 0.0]) is None

    def test_equal_weights(self) -> None:
        # Equal amounts → simple average
        result = compute_vwap([0.3, 0.7], [100.0, 100.0])
        assert result is not None
        assert abs(result - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# compute_marks_for_day tests
# ---------------------------------------------------------------------------

def _make_trade(
    market_id: str,
    outcome_id: str,
    price: float,
    usd_amount: float,
    maker: str = "0xAAA",
    taker: str = "0xBBB",
    event_ts: datetime | None = None,
) -> dict:
    return {
        "platform_market_id": market_id,
        "nonusdc_side": outcome_id,
        "price": price,
        "usd_amount": usd_amount,
        "maker": maker,
        "taker": taker,
        "event_ts": event_ts or datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
    }


class TestComputeMarksForDay:
    def test_single_market_above_min_trades_uses_vwap(self) -> None:
        """When trades >= MIN_TRADES_FOR_VWAP, mark_price should be VWAP."""
        trades = [
            _make_trade("m1", "tok1", 0.5, 100.0, event_ts=datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc)),
            _make_trade("m1", "tok1", 0.6, 200.0, event_ts=datetime(2024, 6, 15, 11, 0, tzinfo=timezone.utc)),
            _make_trade("m1", "tok1", 0.7, 300.0, event_ts=datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)),
        ]
        assert len(trades) >= MIN_TRADES_FOR_VWAP

        result = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))
        assert result.num_rows == 1

        row = result.to_pylist()[0]
        # VWAP = (0.5*100 + 0.6*200 + 0.7*300) / 600 = (50+120+210)/600 = 380/600
        expected_vwap = 380.0 / 600.0
        assert abs(row["mark_price"] - expected_vwap) < 1e-9
        assert abs(row["last_trade_price"] - 0.7) < 1e-9
        assert abs(row["volume_usd_24h"] - 600.0) < 1e-9
        assert row["trades_count_24h"] == 3

    def test_below_min_trades_uses_last_price(self) -> None:
        """When trades < MIN_TRADES_FOR_VWAP, mark_price falls back to last trade price."""
        trades = [
            _make_trade("m1", "tok1", 0.5, 100.0, event_ts=datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc)),
            _make_trade("m1", "tok1", 0.8, 50.0, event_ts=datetime(2024, 6, 15, 14, 0, tzinfo=timezone.utc)),
        ]
        assert len(trades) < MIN_TRADES_FOR_VWAP

        result = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))
        row = result.to_pylist()[0]
        # Falls back to last trade price (0.8, the later trade)
        assert abs(row["mark_price"] - 0.8) < 1e-9
        assert abs(row["last_trade_price"] - 0.8) < 1e-9

    def test_multiple_markets_grouped(self) -> None:
        """Different market/outcome combos produce separate rows."""
        trades = [
            _make_trade("m1", "tok1", 0.5, 100.0),
            _make_trade("m1", "tok2", 0.3, 50.0),
            _make_trade("m2", "tok3", 0.9, 200.0),
        ]
        result = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))
        assert result.num_rows == 3

    def test_active_wallets_counted(self) -> None:
        """Active wallets counts distinct maker + taker addresses."""
        trades = [
            _make_trade("m1", "tok1", 0.5, 100.0, maker="0xA", taker="0xB"),
            _make_trade("m1", "tok1", 0.6, 100.0, maker="0xA", taker="0xC"),
            _make_trade("m1", "tok1", 0.7, 100.0, maker="0xD", taker="0xB"),
        ]
        result = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))
        row = result.to_pylist()[0]
        # Distinct wallets: 0xA, 0xB, 0xC, 0xD = 4
        assert row["active_wallets_24h"] == 4

    def test_empty_trades_produces_empty_table(self) -> None:
        result = compute_marks_for_day([], "polymarket", date(2024, 6, 15))
        assert result.num_rows == 0
        assert result.schema == MARKET_MARK_DAILY_SCHEMA

    def test_schema_matches(self) -> None:
        trades = [_make_trade("m1", "tok1", 0.5, 100.0)]
        result = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))
        assert result.schema == MARKET_MARK_DAILY_SCHEMA

    def test_trades_with_missing_fields_skipped(self) -> None:
        """Trades with empty market_id or outcome_id are skipped."""
        trades = [
            {"platform_market_id": "", "nonusdc_side": "tok1", "price": 0.5, "usd_amount": 100.0},
            {"platform_market_id": "m1", "nonusdc_side": "", "price": 0.5, "usd_amount": 100.0},
            _make_trade("m1", "tok1", 0.5, 100.0),
        ]
        result = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))
        assert result.num_rows == 1
