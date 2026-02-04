"""Tests for the Silver trade → fill splitter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from prediction_data.gold.fill_splitter import (
    Fill,
    nonusdc_side_to_outcome_id,
    split_trade_to_fills,
    trades_to_fills,
)


def _ts(minute: int = 0) -> datetime:
    """Helper to create test timestamps."""
    return datetime(2024, 6, 15, 12, minute, 0, tzinfo=UTC)


def _trade(
    *,
    event_ts: datetime | None = None,
    platform_market_id: str = "0xABC123",
    maker: str = "0xMaker",
    taker: str = "0xTaker",
    nonusdc_side: str = "token1",
    maker_direction: str = "sell",
    taker_direction: str = "buy",
    price: float = 0.60,
    token_amount: float = 100.0,
    usd_amount: float = 60.0,
) -> dict[str, Any]:
    """Build a Silver trade dict with sensible defaults."""
    return {
        "event_ts": event_ts or _ts(0),
        "platform_market_id": platform_market_id,
        "platform_trade_id": "trade-001",
        "maker": maker,
        "taker": taker,
        "nonusdc_side": nonusdc_side,
        "maker_direction": maker_direction,
        "taker_direction": taker_direction,
        "price": price,
        "usd_amount": usd_amount,
        "token_amount": token_amount,
        "transaction_hash": "0xTxHash",
        "bronze_run_id": "run-001",
        "silver_ingestion_ts": _ts(0),
    }


# ---------------------------------------------------------------------------
# nonusdc_side_to_outcome_id
# ---------------------------------------------------------------------------


class TestOutcomeIdMapping:
    def test_token1_maps_to_index_0(self) -> None:
        assert nonusdc_side_to_outcome_id("mkt1", "token1") == "mkt1_0"

    def test_token2_maps_to_index_1(self) -> None:
        assert nonusdc_side_to_outcome_id("mkt1", "token2") == "mkt1_1"

    def test_invalid_side_raises(self) -> None:
        with pytest.raises(ValueError, match="nonusdc_side must be"):
            nonusdc_side_to_outcome_id("mkt1", "token3")

    def test_empty_side_raises(self) -> None:
        with pytest.raises(ValueError, match="nonusdc_side must be"):
            nonusdc_side_to_outcome_id("mkt1", "")

    def test_preserves_market_id_in_outcome(self) -> None:
        oid = nonusdc_side_to_outcome_id("0xLongMarketId123", "token2")
        assert oid == "0xLongMarketId123_1"


# ---------------------------------------------------------------------------
# split_trade_to_fills — single trade → 2 fills
# ---------------------------------------------------------------------------


class TestSplitTradeToFills:
    def test_produces_two_fills(self) -> None:
        maker_fill, taker_fill = split_trade_to_fills(_trade())
        assert isinstance(maker_fill, Fill)
        assert isinstance(taker_fill, Fill)

    def test_maker_fill_fields(self) -> None:
        trade = _trade(
            maker="0xAlice",
            maker_direction="sell",
            nonusdc_side="token1",
            platform_market_id="mkt1",
            price=0.60,
            token_amount=100.0,
        )
        maker_fill, _ = split_trade_to_fills(trade)

        assert maker_fill.wallet == "0xAlice"
        assert maker_fill.side == "sell"
        assert maker_fill.market_id == "mkt1"
        assert maker_fill.outcome_id == "mkt1_0"
        assert maker_fill.qty_delta == 100.0
        assert maker_fill.price == 0.60
        assert maker_fill.platform == "polymarket"
        assert maker_fill.fees_usd == 0.0

    def test_taker_fill_fields(self) -> None:
        trade = _trade(
            taker="0xBob",
            taker_direction="buy",
            nonusdc_side="token2",
            platform_market_id="mkt2",
            price=0.40,
            token_amount=50.0,
        )
        _, taker_fill = split_trade_to_fills(trade)

        assert taker_fill.wallet == "0xBob"
        assert taker_fill.side == "buy"
        assert taker_fill.market_id == "mkt2"
        assert taker_fill.outcome_id == "mkt2_1"
        assert taker_fill.qty_delta == 50.0
        assert taker_fill.price == 0.40
        assert taker_fill.platform == "polymarket"
        assert taker_fill.fees_usd == 0.0

    def test_both_fills_share_timestamp(self) -> None:
        trade = _trade(event_ts=_ts(5))
        maker_fill, taker_fill = split_trade_to_fills(trade)

        assert maker_fill.ts == _ts(5)
        assert taker_fill.ts == _ts(5)

    def test_both_fills_share_outcome_id(self) -> None:
        trade = _trade(nonusdc_side="token1", platform_market_id="m1")
        maker_fill, taker_fill = split_trade_to_fills(trade)

        assert maker_fill.outcome_id == taker_fill.outcome_id == "m1_0"

    def test_both_fills_share_qty_and_price(self) -> None:
        trade = _trade(price=0.75, token_amount=200.0)
        maker_fill, taker_fill = split_trade_to_fills(trade)

        assert maker_fill.qty_delta == taker_fill.qty_delta == 200.0
        assert maker_fill.price == taker_fill.price == 0.75

    def test_maker_sells_taker_buys(self) -> None:
        """Typical trade: maker sells, taker buys."""
        trade = _trade(maker_direction="sell", taker_direction="buy")
        maker_fill, taker_fill = split_trade_to_fills(trade)

        assert maker_fill.side == "sell"
        assert taker_fill.side == "buy"

    def test_maker_buys_taker_sells(self) -> None:
        """Reverse case: maker buys, taker sells."""
        trade = _trade(maker_direction="buy", taker_direction="sell")
        maker_fill, taker_fill = split_trade_to_fills(trade)

        assert maker_fill.side == "buy"
        assert taker_fill.side == "sell"

    def test_custom_platform(self) -> None:
        trade = _trade()
        maker_fill, taker_fill = split_trade_to_fills(trade, platform="kalshi")

        assert maker_fill.platform == "kalshi"
        assert taker_fill.platform == "kalshi"

    def test_invalid_nonusdc_side_raises(self) -> None:
        trade = _trade(nonusdc_side="invalid")
        with pytest.raises(ValueError, match="nonusdc_side must be"):
            split_trade_to_fills(trade)

    def test_missing_required_field_raises(self) -> None:
        trade = _trade()
        del trade["maker"]
        with pytest.raises(KeyError):
            split_trade_to_fills(trade)

    def test_fills_are_frozen(self) -> None:
        """Fill dataclass is immutable."""
        maker_fill, _ = split_trade_to_fills(_trade())
        with pytest.raises(AttributeError):
            maker_fill.price = 0.99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# trades_to_fills — batch conversion with sorting
# ---------------------------------------------------------------------------


class TestTradesToFills:
    def test_empty_input(self) -> None:
        assert trades_to_fills([]) == []

    def test_single_trade_produces_two_fills(self) -> None:
        fills = trades_to_fills([_trade()])
        assert len(fills) == 2

    def test_multiple_trades_produce_correct_count(self) -> None:
        trades = [_trade(event_ts=_ts(i)) for i in range(5)]
        fills = trades_to_fills(trades)
        assert len(fills) == 10

    def test_fills_sorted_by_timestamp(self) -> None:
        """Fills from out-of-order trades should be sorted by ts."""
        trades = [
            _trade(event_ts=_ts(3)),
            _trade(event_ts=_ts(1)),
            _trade(event_ts=_ts(2)),
        ]
        fills = trades_to_fills(trades)

        timestamps = [f.ts for f in fills]
        assert timestamps == sorted(timestamps)

    def test_fills_from_same_timestamp_stable(self) -> None:
        """Multiple fills at the same timestamp should not error."""
        trades = [_trade(event_ts=_ts(0)), _trade(event_ts=_ts(0))]
        fills = trades_to_fills(trades)
        assert len(fills) == 4
        assert all(f.ts == _ts(0) for f in fills)

    def test_mixed_outcome_ids(self) -> None:
        """Trades across different markets and sides produce correct outcome IDs."""
        trades = [
            _trade(platform_market_id="m1", nonusdc_side="token1"),
            _trade(platform_market_id="m1", nonusdc_side="token2"),
            _trade(platform_market_id="m2", nonusdc_side="token1"),
        ]
        fills = trades_to_fills(trades)

        outcome_ids = {f.outcome_id for f in fills}
        assert outcome_ids == {"m1_0", "m1_1", "m2_0"}


# ---------------------------------------------------------------------------
# Integration with accounting engine
# ---------------------------------------------------------------------------


class TestFillAccountingIntegration:
    """Verify fills produced by the splitter work with PositionState."""

    def test_fills_feed_into_accounting(self) -> None:
        """A buy fill from a trade should open a position correctly."""
        from prediction_data.gold.accounting import PositionState

        trade = _trade(
            taker="0xBob",
            taker_direction="buy",
            nonusdc_side="token1",
            platform_market_id="mkt1",
            price=0.60,
            token_amount=100.0,
        )
        _, taker_fill = split_trade_to_fills(trade)

        pos = PositionState(
            wallet=taker_fill.wallet,
            platform=taker_fill.platform,
            market_id=taker_fill.market_id,
            outcome_id=taker_fill.outcome_id,
        )
        result = pos.apply_fill(
            side=taker_fill.side,
            qty_delta=taker_fill.qty_delta,
            price=taker_fill.price,
            fees=taker_fill.fees_usd,
            ts=taker_fill.ts,
        )

        assert result.realized_pnl == 0.0
        assert pos.qty == 100.0
        assert pos.avg_cost == pytest.approx(0.60)

    def test_round_trip_buy_then_sell(self) -> None:
        """Two trades: taker buys then sells → realized PnL from accounting."""
        from prediction_data.gold.accounting import PositionState

        buy_trade = _trade(
            event_ts=_ts(1),
            taker="0xBob",
            taker_direction="buy",
            nonusdc_side="token1",
            platform_market_id="mkt1",
            price=0.50,
            token_amount=100.0,
        )
        sell_trade = _trade(
            event_ts=_ts(2),
            maker="0xBob",
            maker_direction="sell",
            nonusdc_side="token1",
            platform_market_id="mkt1",
            price=0.80,
            token_amount=100.0,
        )

        fills = trades_to_fills([buy_trade, sell_trade])

        pos = PositionState(
            wallet="0xBob",
            platform="polymarket",
            market_id="mkt1",
            outcome_id="mkt1_0",
        )

        total_pnl = 0.0
        for fill in fills:
            if fill.wallet == "0xBob":
                r = pos.apply_fill(
                    side=fill.side,
                    qty_delta=fill.qty_delta,
                    price=fill.price,
                    fees=fill.fees_usd,
                    ts=fill.ts,
                )
                total_pnl += r.realized_pnl

        # 100 * (0.80 - 0.50) = 30.0
        assert total_pnl == pytest.approx(30.0)
        assert pos.qty == 0.0
