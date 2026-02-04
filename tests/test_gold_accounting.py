"""Tests for the average-cost position accounting engine."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from prediction_data.gold.accounting import FillResult, PositionState


def _ts(minute: int = 0) -> datetime:
    """Helper to create test timestamps."""
    return datetime(2024, 6, 15, 12, minute, 0, tzinfo=UTC)


class TestPositionStateBasics:
    def test_initial_state(self) -> None:
        pos = PositionState(
            wallet="0xABC",
            platform="polymarket",
            market_id="m1",
            outcome_id="o1",
        )
        assert pos.qty == 0.0
        assert pos.avg_cost == 0.0
        assert pos.cost_basis_usd == 0.0
        assert pos.last_fill_ts is None
        assert not pos.is_open

    def test_invalid_side_raises(self) -> None:
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        with pytest.raises(ValueError, match="side must be 'buy' or 'sell'"):
            pos.apply_fill("hold", 10.0, 0.50, 0.0, _ts())

    def test_zero_qty_delta_raises(self) -> None:
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        with pytest.raises(ValueError, match="qty_delta must be positive"):
            pos.apply_fill("buy", 0.0, 0.50, 0.0, _ts())

    def test_negative_qty_delta_raises(self) -> None:
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        with pytest.raises(ValueError, match="qty_delta must be positive"):
            pos.apply_fill("buy", -5.0, 0.50, 0.0, _ts())


class TestSingleBuy:
    def test_open_long(self) -> None:
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        result = pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(1))

        assert result.realized_pnl == 0.0
        assert not result.closed
        assert pos.qty == 100.0
        assert pos.avg_cost == pytest.approx(0.60)
        assert pos.cost_basis_usd == pytest.approx(60.0)
        assert pos.is_open
        assert pos.last_fill_ts == _ts(1)


class TestMultipleBuys:
    def test_avg_cost_calculation(self) -> None:
        """Buy 100 @ 0.60, then 50 @ 0.90 → avg_cost = (60 + 45) / 150 = 0.70."""
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(1))
        result = pos.apply_fill("buy", 50.0, 0.90, 0.0, _ts(2))

        assert result.realized_pnl == 0.0
        assert pos.qty == 150.0
        assert pos.avg_cost == pytest.approx(0.70)
        assert pos.cost_basis_usd == pytest.approx(105.0)

    def test_three_buys(self) -> None:
        """Buy 10 @ 0.50, 20 @ 0.60, 10 @ 0.80 → avg = (5 + 12 + 8) / 40 = 0.625."""
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        pos.apply_fill("buy", 10.0, 0.50, 0.0, _ts(1))
        pos.apply_fill("buy", 20.0, 0.60, 0.0, _ts(2))
        pos.apply_fill("buy", 10.0, 0.80, 0.0, _ts(3))

        assert pos.qty == 40.0
        assert pos.avg_cost == pytest.approx(0.625)


class TestPartialSell:
    def test_partial_sell_realized_pnl(self) -> None:
        """Buy 100 @ 0.60, sell 40 @ 0.80 → PnL = 40 * (0.80 - 0.60) = 8.0."""
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(1))
        result = pos.apply_fill("sell", 40.0, 0.80, 0.0, _ts(2))

        assert result.realized_pnl == pytest.approx(8.0)
        assert not result.closed
        assert pos.qty == 60.0
        assert pos.avg_cost == pytest.approx(0.60)  # unchanged on sell
        assert pos.cost_basis_usd == pytest.approx(36.0)

    def test_sell_at_loss(self) -> None:
        """Buy 100 @ 0.60, sell 50 @ 0.40 → PnL = 50 * (0.40 - 0.60) = -10.0."""
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(1))
        result = pos.apply_fill("sell", 50.0, 0.40, 0.0, _ts(2))

        assert result.realized_pnl == pytest.approx(-10.0)
        assert pos.qty == 50.0
        assert pos.avg_cost == pytest.approx(0.60)

    def test_avg_cost_preserved_across_sells(self) -> None:
        """Multiple partial sells should not change avg_cost."""
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(1))
        pos.apply_fill("sell", 20.0, 0.80, 0.0, _ts(2))
        pos.apply_fill("sell", 30.0, 0.70, 0.0, _ts(3))

        assert pos.qty == 50.0
        assert pos.avg_cost == pytest.approx(0.60)


class TestPositionClose:
    def test_exact_close(self) -> None:
        """Buy 100 @ 0.60, sell 100 @ 0.80 → PnL = 100 * 0.20 = 20.0."""
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(1))
        result = pos.apply_fill("sell", 100.0, 0.80, 0.0, _ts(2))

        assert result.realized_pnl == pytest.approx(20.0)
        assert result.closed
        assert pos.qty == 0.0
        assert pos.cost_basis_usd == 0.0
        assert not pos.is_open

    def test_close_at_loss(self) -> None:
        """Buy 50 @ 0.70, sell 50 @ 0.30 → PnL = 50 * (0.30 - 0.70) = -20.0."""
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        pos.apply_fill("buy", 50.0, 0.70, 0.0, _ts(1))
        result = pos.apply_fill("sell", 50.0, 0.30, 0.0, _ts(2))

        assert result.realized_pnl == pytest.approx(-20.0)
        assert result.closed

    def test_close_breakeven(self) -> None:
        """Buy 100 @ 0.50, sell 100 @ 0.50 → PnL = 0."""
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        pos.apply_fill("buy", 100.0, 0.50, 0.0, _ts(1))
        result = pos.apply_fill("sell", 100.0, 0.50, 0.0, _ts(2))

        assert result.realized_pnl == pytest.approx(0.0)
        assert result.closed


class TestPositionFlip:
    def test_long_to_short(self) -> None:
        """Buy 100 @ 0.60, sell 150 @ 0.80.

        Close leg: 100 @ 0.80, PnL = 100 * (0.80 - 0.60) = 20.0
        Open leg: 50 short @ 0.80
        """
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(1))
        result = pos.apply_fill("sell", 150.0, 0.80, 0.0, _ts(2))

        assert result.realized_pnl == pytest.approx(20.0)
        assert not result.closed  # position flipped, not closed
        assert pos.qty == -50.0
        assert pos.avg_cost == pytest.approx(0.80)
        assert pos.cost_basis_usd == pytest.approx(40.0)

    def test_short_to_long(self) -> None:
        """Open short by selling, then buy back more than the short.

        Sell 100 @ 0.80 (opening short via flip from zero).
        Actually, let's open short differently:
        Buy 50 @ 0.60, sell 100 @ 0.80 (flip to short 50 @ 0.80).
        Then buy 80 @ 0.70 (flip back to long 30 @ 0.70).

        Close short leg: 50 * (0.80 - 0.70) = 5.0
        Open long leg: 30 @ 0.70
        """
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        # Open long 50 @ 0.60
        pos.apply_fill("buy", 50.0, 0.60, 0.0, _ts(1))
        # Flip to short 50 @ 0.80 (close long, open short)
        pos.apply_fill("sell", 100.0, 0.80, 0.0, _ts(2))
        assert pos.qty == -50.0
        assert pos.avg_cost == pytest.approx(0.80)

        # Flip back to long 30 @ 0.70 (close short 50, open long 30)
        result = pos.apply_fill("buy", 80.0, 0.70, 0.0, _ts(3))

        # Short closed: 50 * (0.80 - 0.70) = 5.0 profit
        assert result.realized_pnl == pytest.approx(5.0)
        assert pos.qty == 30.0
        assert pos.avg_cost == pytest.approx(0.70)


class TestFees:
    def test_fees_reduce_realized_pnl(self) -> None:
        """Buy 100 @ 0.60, sell 100 @ 0.80 with $2 fees → PnL = 20 - 2 = 18."""
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(1))
        result = pos.apply_fill("sell", 100.0, 0.80, 2.0, _ts(2))

        assert result.realized_pnl == pytest.approx(18.0)

    def test_fees_on_partial_sell(self) -> None:
        """Buy 100 @ 0.60, sell 40 @ 0.80 with $1 fee → PnL = 8 - 1 = 7."""
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(1))
        result = pos.apply_fill("sell", 40.0, 0.80, 1.0, _ts(2))

        assert result.realized_pnl == pytest.approx(7.0)

    def test_fees_on_flip(self) -> None:
        """Buy 100 @ 0.60, sell 150 @ 0.80 with $3 fee.

        Close leg PnL = 100 * 0.20 - 3.0 = 17.0.
        """
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(1))
        result = pos.apply_fill("sell", 150.0, 0.80, 3.0, _ts(2))

        assert result.realized_pnl == pytest.approx(17.0)
        assert pos.qty == -50.0

    def test_fees_on_buy_do_not_affect_pnl(self) -> None:
        """Buy with fees: no realized PnL but cost_basis includes fees."""
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        result = pos.apply_fill("buy", 100.0, 0.60, 2.0, _ts(1))

        assert result.realized_pnl == 0.0
        assert pos.qty == 100.0
        assert pos.avg_cost == pytest.approx(0.60)
        # cost_basis includes fees
        assert pos.cost_basis_usd == pytest.approx(62.0)


class TestTimestampTracking:
    def test_last_fill_ts_updated(self) -> None:
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        pos.apply_fill("buy", 100.0, 0.60, 0.0, _ts(1))
        assert pos.last_fill_ts == _ts(1)

        pos.apply_fill("buy", 50.0, 0.70, 0.0, _ts(5))
        assert pos.last_fill_ts == _ts(5)

        pos.apply_fill("sell", 30.0, 0.80, 0.0, _ts(10))
        assert pos.last_fill_ts == _ts(10)


class TestComplexSequence:
    def test_buy_sell_buy_close(self) -> None:
        """Full lifecycle: open → partial sell → add → close.

        Buy 100 @ 0.50
        Sell 40 @ 0.70 → PnL = 40 * 0.20 = 8.0, qty=60
        Buy 20 @ 0.55 → avg_cost = (60*0.50 + 20*0.55) / 80 = 41/80 = 0.5125
        Sell 80 @ 0.90 → PnL = 80 * (0.90 - 0.5125) = 80 * 0.3875 = 31.0
        """
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )

        r1 = pos.apply_fill("buy", 100.0, 0.50, 0.0, _ts(1))
        assert r1.realized_pnl == 0.0
        assert pos.qty == 100.0

        r2 = pos.apply_fill("sell", 40.0, 0.70, 0.0, _ts(2))
        assert r2.realized_pnl == pytest.approx(8.0)
        assert pos.qty == 60.0
        assert pos.avg_cost == pytest.approx(0.50)

        r3 = pos.apply_fill("buy", 20.0, 0.55, 0.0, _ts(3))
        assert r3.realized_pnl == 0.0
        assert pos.qty == 80.0
        assert pos.avg_cost == pytest.approx(0.5125)

        r4 = pos.apply_fill("sell", 80.0, 0.90, 0.0, _ts(4))
        assert r4.realized_pnl == pytest.approx(31.0)
        assert r4.closed
        assert pos.qty == 0.0

    def test_total_realized_pnl_across_fills(self) -> None:
        """Track cumulative PnL across a sequence of trades.

        Buy 200 @ 0.40 → cost = 80
        Sell 100 @ 0.60 → PnL = 100 * 0.20 = 20
        Sell 50 @ 0.30 → PnL = 50 * -0.10 = -5
        Sell 50 @ 0.50 → PnL = 50 * 0.10 = 5, closed
        Total PnL = 20 + (-5) + 5 = 20
        """
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        total_pnl = 0.0

        pos.apply_fill("buy", 200.0, 0.40, 0.0, _ts(1))

        r = pos.apply_fill("sell", 100.0, 0.60, 0.0, _ts(2))
        total_pnl += r.realized_pnl
        assert total_pnl == pytest.approx(20.0)

        r = pos.apply_fill("sell", 50.0, 0.30, 0.0, _ts(3))
        total_pnl += r.realized_pnl
        assert total_pnl == pytest.approx(15.0)

        r = pos.apply_fill("sell", 50.0, 0.50, 0.0, _ts(4))
        total_pnl += r.realized_pnl
        assert total_pnl == pytest.approx(20.0)
        assert r.closed

    def test_reopen_after_close(self) -> None:
        """Close a position, then reopen with a new trade."""
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        pos.apply_fill("buy", 100.0, 0.50, 0.0, _ts(1))
        pos.apply_fill("sell", 100.0, 0.80, 0.0, _ts(2))
        assert pos.qty == 0.0

        # Reopen.
        pos.apply_fill("buy", 50.0, 0.65, 0.0, _ts(3))
        assert pos.qty == 50.0
        assert pos.avg_cost == pytest.approx(0.65)
        assert pos.is_open


class TestFillResult:
    def test_fill_result_fields(self) -> None:
        r = FillResult(realized_pnl=5.0, closed=True)
        assert r.realized_pnl == 5.0
        assert r.closed


class TestEdgeCases:
    def test_very_small_quantities(self) -> None:
        """Handle fractional token quantities."""
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        pos.apply_fill("buy", 0.001, 0.50, 0.0, _ts(1))
        assert pos.qty == pytest.approx(0.001)
        assert pos.avg_cost == pytest.approx(0.50)

        result = pos.apply_fill("sell", 0.001, 0.60, 0.0, _ts(2))
        assert result.realized_pnl == pytest.approx(0.0001)
        assert result.closed

    def test_price_at_zero(self) -> None:
        """Handle price of 0 (worthless outcome)."""
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        pos.apply_fill("buy", 100.0, 0.50, 0.0, _ts(1))
        result = pos.apply_fill("sell", 100.0, 0.0, 0.0, _ts(2))

        assert result.realized_pnl == pytest.approx(-50.0)
        assert result.closed

    def test_price_at_one(self) -> None:
        """Handle price of 1.0 (fully resolved YES outcome)."""
        pos = PositionState(
            wallet="0xABC", platform="polymarket", market_id="m1", outcome_id="o1"
        )
        pos.apply_fill("buy", 100.0, 0.50, 0.0, _ts(1))
        result = pos.apply_fill("sell", 100.0, 1.0, 0.0, _ts(2))

        assert result.realized_pnl == pytest.approx(50.0)
        assert result.closed
