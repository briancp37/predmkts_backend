"""Tests for Gold market_mark_daily computation."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pyarrow as pa

from prediction_data.gold.market_marks import (
    MARKET_MARK_DAILY_COLUMNS,
    MARKET_MARK_DAILY_SCHEMA,
    MIN_TRADES_FOR_VWAP,
    _load_marks_to_clickhouse,
    attach_liquidity_metric,
    compute_marks_for_day,
    compute_vwap,
    load_marks_to_clickhouse_from_s3,
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

    def test_liquidity_metric_defaults_to_null(self) -> None:
        """compute_marks_for_day sets liquidity_metric to null (filled later)."""
        trades = [_make_trade("m1", "tok1", 0.5, 100.0)]
        result = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))
        row = result.to_pylist()[0]
        assert row["liquidity_metric"] is None


# ---------------------------------------------------------------------------
# attach_liquidity_metric tests
# ---------------------------------------------------------------------------


class TestAttachLiquidityMetric:
    def test_no_prior_data_uses_current_volume(self) -> None:
        """With no prior days, liquidity_metric equals today's volume."""
        trades = [_make_trade("m1", "tok1", 0.5, 200.0)]
        marks = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))
        result = attach_liquidity_metric(marks, {})
        row = result.to_pylist()[0]
        assert abs(row["liquidity_metric"] - 200.0) < 1e-9

    def test_with_prior_volumes(self) -> None:
        """Trailing avg includes prior days + current day."""
        trades = [_make_trade("m1", "tok1", 0.5, 100.0)]
        marks = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))
        # 3 prior days with volumes 200, 300, 400; current = 100
        prior = {("m1", "tok1"): [200.0, 300.0, 400.0]}
        result = attach_liquidity_metric(marks, prior)
        row = result.to_pylist()[0]
        expected = (200.0 + 300.0 + 400.0 + 100.0) / 4
        assert abs(row["liquidity_metric"] - expected) < 1e-9

    def test_multiple_outcomes(self) -> None:
        """Each outcome gets its own liquidity metric."""
        trades = [
            _make_trade("m1", "tok1", 0.5, 100.0),
            _make_trade("m1", "tok2", 0.3, 50.0),
        ]
        marks = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))
        prior = {("m1", "tok1"): [300.0]}
        result = attach_liquidity_metric(marks, prior)
        rows = {r["outcome_id"]: r for r in result.to_pylist()}
        # tok1: (300+100)/2 = 200
        assert abs(rows["tok1"]["liquidity_metric"] - 200.0) < 1e-9
        # tok2: only current day = 50
        assert abs(rows["tok2"]["liquidity_metric"] - 50.0) < 1e-9

    def test_schema_preserved(self) -> None:
        trades = [_make_trade("m1", "tok1", 0.5, 100.0)]
        marks = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))
        result = attach_liquidity_metric(marks, {})
        assert result.schema == MARKET_MARK_DAILY_SCHEMA


# ---------------------------------------------------------------------------
# ClickHouse loader tests
# ---------------------------------------------------------------------------


class TestLoadMarksToClickhouse:
    def test_inserts_rows_into_ch(self) -> None:
        """_load_marks_to_clickhouse calls client.insert with correct args."""
        trades = [
            _make_trade("m1", "tok1", 0.5, 100.0),
            _make_trade("m1", "tok2", 0.3, 50.0),
        ]
        marks = compute_marks_for_day(trades, "polymarket", date(2024, 6, 15))
        ch = MagicMock()

        _load_marks_to_clickhouse(marks, ch)

        ch.insert.assert_called_once()
        call_args = ch.insert.call_args
        assert call_args[0][0] == "market_mark_daily"
        assert call_args[1]["column_names"] == MARKET_MARK_DAILY_COLUMNS
        assert len(call_args[1]["data"]) == 2

    def test_load_from_s3_reads_partitions(self) -> None:
        """load_marks_to_clickhouse_from_s3 reads S3 partitions and inserts."""
        sample = compute_marks_for_day(
            [_make_trade("m1", "tok1", 0.5, 100.0)], "polymarket", date(2024, 6, 15)
        )
        ch = MagicMock()
        call_count = 0

        def mock_read(gold_bucket: str, day: str, s3_client: object = None) -> pa.Table | None:
            nonlocal call_count
            call_count += 1
            # Return data for first 3 days, None for rest
            if call_count <= 3:
                return sample
            return None

        with patch(
            "prediction_data.gold.market_marks._read_gold_marks_for_day",
            side_effect=mock_read,
        ):
            rows = load_marks_to_clickhouse_from_s3(
                gold_bucket="test-gold",
                lookback_days=5,
                s3_client=MagicMock(),
                clickhouse_client=ch,
            )

        assert rows == 3  # 3 days × 1 row each
        assert ch.insert.call_count == 3

    def test_load_from_s3_empty_bucket(self) -> None:
        """No rows loaded when no partitions exist."""
        ch = MagicMock()

        with patch(
            "prediction_data.gold.market_marks._read_gold_marks_for_day",
            return_value=None,
        ):
            rows = load_marks_to_clickhouse_from_s3(
                gold_bucket="test-gold",
                lookback_days=5,
                s3_client=MagicMock(),
                clickhouse_client=ch,
            )

        assert rows == 0
        ch.insert.assert_not_called()
