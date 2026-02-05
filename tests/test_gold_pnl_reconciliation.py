"""PnL Reconciliation Tests for Gold Layer.

Tests PnL accuracy with known trade sequences and hand-calculated expected values.
Verifies the full pipeline: fills → ledger → wallet_pnl_daily aggregation.

PRD Reference: plans/release/03_gold_level/sprint/09_validation_and_delivery/prd.json
Category: pnl_reconciliation
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from prediction_data.gold.accounting import PositionState
from prediction_data.gold.fill_splitter import Fill
from prediction_data.gold.ledger import LedgerWriter, build_ledger_for_day
from prediction_data.gold.wallet_pnl import aggregate_pnl_for_day


def _ts(minute: int = 0) -> datetime:
    """Helper to create test timestamps."""
    return datetime(2024, 6, 15, 12, minute, 0, tzinfo=UTC)


def _fill(
    *,
    ts: datetime | None = None,
    wallet: str = "0xTEST",
    platform: str = "polymarket",
    market_id: str = "MKT1",
    outcome_id: str = "MKT1_0",
    side: str = "buy",
    qty_delta: float = 100.0,
    price: float = 0.50,
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


# =============================================================================
# SYNTHETIC TEST FIXTURES WITH HAND-CALCULATED PNL
# =============================================================================
#
# These fixtures define trade sequences with expected PnL at each step,
# computed by hand using the average cost basis methodology:
#
# - Buy: new_avg_cost = (old_qty * old_avg_cost + qty_delta * price) / new_qty
# - Sell: realized_pnl = qty_delta * (price - avg_cost) - fees
# - Flip: close existing position at full qty, open remainder in opposite direction
# =============================================================================


class TestCase1SimpleBuySellCycle:
    """Test case 1: simple buy-sell cycle.

    Sequence:
        1. Buy 100 @ $0.50 → position: qty=100, avg_cost=0.50, realized_pnl=0
        2. Sell 100 @ $0.70 → position: qty=0, realized_pnl = 100 * (0.70 - 0.50) = $20

    Total realized PnL: $20.00
    """

    def test_accounting_engine_pnl(self) -> None:
        """Test the accounting engine produces correct PnL."""
        pos = PositionState(
            wallet="0xTEST", platform="polymarket", market_id="MKT1", outcome_id="MKT1_0"
        )

        # Step 1: Buy 100 @ $0.50
        r1 = pos.apply_fill("buy", 100.0, 0.50, 0.0, _ts(0))
        assert r1.realized_pnl == 0.0
        assert not r1.closed
        assert pos.qty == 100.0
        assert pos.avg_cost == pytest.approx(0.50)
        assert pos.cost_basis_usd == pytest.approx(50.0)

        # Step 2: Sell 100 @ $0.70
        r2 = pos.apply_fill("sell", 100.0, 0.70, 0.0, _ts(1))
        assert r2.realized_pnl == pytest.approx(20.0)  # 100 * (0.70 - 0.50) = 20
        assert r2.closed
        assert pos.qty == 0.0
        assert pos.cost_basis_usd == 0.0

    def test_ledger_captures_pnl(self) -> None:
        """Test the ledger captures per-fill PnL correctly."""
        fills = [
            _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.50),
            _fill(ts=_ts(1), side="sell", qty_delta=100.0, price=0.70),
        ]
        writer, positions = build_ledger_for_day(fills, {})
        rows = writer.rows

        assert len(rows) == 2

        # Fill 1: Buy - no realized PnL
        assert rows[0].realized_pnl_this_fill_usd == 0.0
        assert rows[0].qty_before == 0.0
        assert rows[0].qty_after == 100.0

        # Fill 2: Sell - realized PnL = $20
        assert rows[1].realized_pnl_this_fill_usd == pytest.approx(20.0)
        assert rows[1].qty_before == 100.0
        assert rows[1].qty_after == 0.0

    def test_wallet_pnl_daily_aggregation(self) -> None:
        """Test wallet_pnl_daily aggregates to correct total."""
        fills = [
            _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.50),
            _fill(ts=_ts(1), side="sell", qty_delta=100.0, price=0.70),
        ]
        writer, _ = build_ledger_for_day(fills, {})

        # Convert ledger to wallet_pnl_daily input format
        ledger_rows = [
            {
                "wallet": r.wallet,
                "qty_delta": r.qty_delta,
                "price": r.price,
                "fees_usd": r.fees_usd,
                "realized_pnl_this_fill_usd": r.realized_pnl_this_fill_usd,
            }
            for r in writer.rows
        ]

        pnl_table = aggregate_pnl_for_day(ledger_rows, date(2024, 6, 15))
        assert pnl_table.num_rows == 1
        row = pnl_table.to_pylist()[0]

        assert row["wallet"] == "0xTEST"
        assert row["realized_pnl_usd"] == pytest.approx(20.0)
        assert row["trades_count"] == 2
        assert row["wins"] == 1  # The sell with +$20 PnL
        assert row["losses"] == 0
        # Volume: abs(100 * 0.50) + abs(100 * 0.70) = 50 + 70 = 120
        assert row["volume_usd"] == pytest.approx(120.0)


class TestCase2MultipleBuysPartialSell:
    """Test case 2: multiple buys at different prices, partial sell.

    Sequence:
        1. Buy 100 @ $0.50 → qty=100, avg_cost=0.50
        2. Buy 50 @ $0.80 → qty=150, avg_cost = (100*0.50 + 50*0.80) / 150 = 90/150 = 0.60
        3. Sell 60 @ $0.75 → qty=90, realized_pnl = 60 * (0.75 - 0.60) = $9.00

    This verifies:
    - Weighted average cost calculation: (50 + 40) / 150 = 0.60
    - Partial close PnL uses the average cost, not individual lot prices
    """

    def test_accounting_engine_avg_cost(self) -> None:
        """Test average cost basis is computed correctly."""
        pos = PositionState(
            wallet="0xTEST", platform="polymarket", market_id="MKT1", outcome_id="MKT1_0"
        )

        # Step 1: Buy 100 @ $0.50
        r1 = pos.apply_fill("buy", 100.0, 0.50, 0.0, _ts(0))
        assert r1.realized_pnl == 0.0
        assert pos.qty == 100.0
        assert pos.avg_cost == pytest.approx(0.50)
        # cost_basis = 100 * 0.50 = 50
        assert pos.cost_basis_usd == pytest.approx(50.0)

        # Step 2: Buy 50 @ $0.80
        # new_avg_cost = (100 * 0.50 + 50 * 0.80) / 150 = (50 + 40) / 150 = 0.60
        r2 = pos.apply_fill("buy", 50.0, 0.80, 0.0, _ts(1))
        assert r2.realized_pnl == 0.0
        assert pos.qty == 150.0
        assert pos.avg_cost == pytest.approx(0.60)
        # cost_basis = 150 * 0.60 = 90
        assert pos.cost_basis_usd == pytest.approx(90.0)

        # Step 3: Sell 60 @ $0.75
        # realized_pnl = 60 * (0.75 - 0.60) = 60 * 0.15 = 9.0
        r3 = pos.apply_fill("sell", 60.0, 0.75, 0.0, _ts(2))
        assert r3.realized_pnl == pytest.approx(9.0)
        assert not r3.closed
        assert pos.qty == 90.0
        # avg_cost unchanged after sell
        assert pos.avg_cost == pytest.approx(0.60)
        # cost_basis = 90 * 0.60 = 54
        assert pos.cost_basis_usd == pytest.approx(54.0)

    def test_ledger_and_pnl_aggregation(self) -> None:
        """Test full pipeline: ledger → wallet_pnl_daily."""
        fills = [
            _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.50),
            _fill(ts=_ts(1), side="buy", qty_delta=50.0, price=0.80),
            _fill(ts=_ts(2), side="sell", qty_delta=60.0, price=0.75),
        ]
        writer, _ = build_ledger_for_day(fills, {})
        rows = writer.rows

        # Verify ledger rows
        assert len(rows) == 3
        # Buy 1: no realized PnL
        assert rows[0].realized_pnl_this_fill_usd == 0.0
        assert rows[0].avg_cost_after == pytest.approx(0.50)

        # Buy 2: no realized PnL, avg_cost updated
        assert rows[1].realized_pnl_this_fill_usd == 0.0
        assert rows[1].avg_cost_after == pytest.approx(0.60)

        # Sell: realized PnL = $9
        assert rows[2].realized_pnl_this_fill_usd == pytest.approx(9.0)
        assert rows[2].avg_cost_after == pytest.approx(0.60)  # unchanged

        # Verify aggregation
        ledger_rows = [
            {
                "wallet": r.wallet,
                "qty_delta": r.qty_delta,
                "price": r.price,
                "fees_usd": r.fees_usd,
                "realized_pnl_this_fill_usd": r.realized_pnl_this_fill_usd,
            }
            for r in writer.rows
        ]
        pnl_table = aggregate_pnl_for_day(ledger_rows, date(2024, 6, 15))
        row = pnl_table.to_pylist()[0]

        assert row["realized_pnl_usd"] == pytest.approx(9.0)
        assert row["trades_count"] == 3
        assert row["wins"] == 1  # The sell
        assert row["losses"] == 0


class TestCase3PositionFlip:
    """Test case 3: position flip (long to short via oversized sell).

    Sequence:
        1. Buy 100 @ $0.50 → qty=100, avg_cost=0.50
        2. Sell 150 @ $0.70 → flip!
           - Close long 100 @ $0.70: realized_pnl = 100 * (0.70 - 0.50) = $20
           - Open short 50 @ $0.70: qty=-50, avg_cost=0.70

    Then close the short:
        3. Buy 50 @ $0.60 → close short
           - realized_pnl = 50 * (0.70 - 0.60) = $5 (profit on short)

    Total realized PnL: $20 + $5 = $25
    """

    def test_accounting_engine_flip(self) -> None:
        """Test position flip mechanics."""
        pos = PositionState(
            wallet="0xTEST", platform="polymarket", market_id="MKT1", outcome_id="MKT1_0"
        )

        # Step 1: Buy 100 @ $0.50
        r1 = pos.apply_fill("buy", 100.0, 0.50, 0.0, _ts(0))
        assert r1.realized_pnl == 0.0
        assert pos.qty == 100.0

        # Step 2: Sell 150 @ $0.70 (flip to short)
        # Close leg: 100 * (0.70 - 0.50) = 20
        # Open leg: short 50 @ 0.70
        r2 = pos.apply_fill("sell", 150.0, 0.70, 0.0, _ts(1))
        assert r2.realized_pnl == pytest.approx(20.0)
        assert not r2.closed  # Flipped, not closed
        assert pos.qty == -50.0  # Short position
        assert pos.avg_cost == pytest.approx(0.70)

        # Step 3: Buy 50 @ $0.60 (close short)
        # Short profit: 50 * (0.70 - 0.60) = 5
        r3 = pos.apply_fill("buy", 50.0, 0.60, 0.0, _ts(2))
        assert r3.realized_pnl == pytest.approx(5.0)
        assert r3.closed
        assert pos.qty == 0.0

    def test_flip_pnl_reconciliation(self) -> None:
        """Test full pipeline with position flip."""
        fills = [
            _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.50),
            _fill(ts=_ts(1), side="sell", qty_delta=150.0, price=0.70),
            _fill(ts=_ts(2), side="buy", qty_delta=50.0, price=0.60),
        ]
        writer, positions = build_ledger_for_day(fills, {})
        rows = writer.rows

        # Verify position is closed
        key = ("0xTEST", "polymarket", "MKT1", "MKT1_0")
        assert positions[key].qty == 0.0

        # Verify ledger captures correct PnL per fill
        assert rows[0].realized_pnl_this_fill_usd == 0.0  # Buy
        assert rows[1].realized_pnl_this_fill_usd == pytest.approx(20.0)  # Flip
        assert rows[2].realized_pnl_this_fill_usd == pytest.approx(5.0)  # Close short

        # Verify aggregation
        ledger_rows = [
            {
                "wallet": r.wallet,
                "qty_delta": r.qty_delta,
                "price": r.price,
                "fees_usd": r.fees_usd,
                "realized_pnl_this_fill_usd": r.realized_pnl_this_fill_usd,
            }
            for r in writer.rows
        ]
        pnl_table = aggregate_pnl_for_day(ledger_rows, date(2024, 6, 15))
        row = pnl_table.to_pylist()[0]

        assert row["realized_pnl_usd"] == pytest.approx(25.0)  # 20 + 5
        assert row["trades_count"] == 3
        assert row["wins"] == 2  # Flip ($20) and close short ($5)


class TestCase4ConcurrentPositionsMultipleMarkets:
    """Test case 4: concurrent positions in multiple markets for same wallet.

    Wallet 0xTEST trades in two markets simultaneously:

    Market A (MKT_A):
        1. Buy 100 @ $0.40 → qty=100, avg_cost=0.40
        2. Sell 100 @ $0.60 → realized_pnl = 100 * (0.60 - 0.40) = $20

    Market B (MKT_B):
        1. Buy 50 @ $0.70 → qty=50, avg_cost=0.70
        2. Sell 50 @ $0.50 → realized_pnl = 50 * (0.50 - 0.70) = -$10 (loss)

    Total realized PnL: $20 + (-$10) = $10
    """

    def test_concurrent_positions_separate_tracking(self) -> None:
        """Test positions in different markets are tracked separately."""
        fills = [
            # Market A
            _fill(ts=_ts(0), market_id="MKT_A", outcome_id="MKT_A_0", side="buy", qty_delta=100.0, price=0.40),
            _fill(ts=_ts(1), market_id="MKT_B", outcome_id="MKT_B_0", side="buy", qty_delta=50.0, price=0.70),
            _fill(ts=_ts(2), market_id="MKT_A", outcome_id="MKT_A_0", side="sell", qty_delta=100.0, price=0.60),
            _fill(ts=_ts(3), market_id="MKT_B", outcome_id="MKT_B_0", side="sell", qty_delta=50.0, price=0.50),
        ]
        writer, positions = build_ledger_for_day(fills, {})
        rows = writer.rows

        assert len(rows) == 4
        assert len(positions) == 2

        # Verify positions are closed
        assert positions[("0xTEST", "polymarket", "MKT_A", "MKT_A_0")].qty == 0.0
        assert positions[("0xTEST", "polymarket", "MKT_B", "MKT_B_0")].qty == 0.0

        # Verify per-fill PnL
        # Row 0: Buy MKT_A - no PnL
        assert rows[0].market_id == "MKT_A"
        assert rows[0].realized_pnl_this_fill_usd == 0.0

        # Row 1: Buy MKT_B - no PnL
        assert rows[1].market_id == "MKT_B"
        assert rows[1].realized_pnl_this_fill_usd == 0.0

        # Row 2: Sell MKT_A - PnL = $20
        assert rows[2].market_id == "MKT_A"
        assert rows[2].realized_pnl_this_fill_usd == pytest.approx(20.0)

        # Row 3: Sell MKT_B - PnL = -$10
        assert rows[3].market_id == "MKT_B"
        assert rows[3].realized_pnl_this_fill_usd == pytest.approx(-10.0)

    def test_wallet_pnl_aggregates_all_markets(self) -> None:
        """Test wallet_pnl_daily aggregates PnL across all markets."""
        fills = [
            _fill(ts=_ts(0), market_id="MKT_A", outcome_id="MKT_A_0", side="buy", qty_delta=100.0, price=0.40),
            _fill(ts=_ts(1), market_id="MKT_B", outcome_id="MKT_B_0", side="buy", qty_delta=50.0, price=0.70),
            _fill(ts=_ts(2), market_id="MKT_A", outcome_id="MKT_A_0", side="sell", qty_delta=100.0, price=0.60),
            _fill(ts=_ts(3), market_id="MKT_B", outcome_id="MKT_B_0", side="sell", qty_delta=50.0, price=0.50),
        ]
        writer, _ = build_ledger_for_day(fills, {})

        ledger_rows = [
            {
                "wallet": r.wallet,
                "qty_delta": r.qty_delta,
                "price": r.price,
                "fees_usd": r.fees_usd,
                "realized_pnl_this_fill_usd": r.realized_pnl_this_fill_usd,
            }
            for r in writer.rows
        ]
        pnl_table = aggregate_pnl_for_day(ledger_rows, date(2024, 6, 15))

        assert pnl_table.num_rows == 1  # Single wallet
        row = pnl_table.to_pylist()[0]

        assert row["wallet"] == "0xTEST"
        assert row["realized_pnl_usd"] == pytest.approx(10.0)  # 20 + (-10)
        assert row["trades_count"] == 4
        assert row["wins"] == 1  # MKT_A sell
        assert row["losses"] == 1  # MKT_B sell


class TestReconciliationLedgerToWalletPnl:
    """Verify wallet_pnl_daily totals match sum of per-fill realized PnL from ledger.

    This is the key reconciliation test: the aggregated daily PnL must equal
    the sum of all realized_pnl_this_fill_usd values in the ledger.
    """

    def test_single_wallet_reconciliation(self) -> None:
        """Sum of ledger per-fill PnL must equal wallet_pnl_daily total."""
        fills = [
            _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.50),
            _fill(ts=_ts(1), side="sell", qty_delta=40.0, price=0.70),  # +8
            _fill(ts=_ts(2), side="buy", qty_delta=20.0, price=0.60),
            _fill(ts=_ts(3), side="sell", qty_delta=80.0, price=0.65),  # +4
        ]
        writer, _ = build_ledger_for_day(fills, {})

        # Compute sum of per-fill PnL from ledger
        ledger_pnl_sum = sum(r.realized_pnl_this_fill_usd for r in writer.rows)

        # Compute wallet_pnl_daily
        ledger_rows = [
            {
                "wallet": r.wallet,
                "qty_delta": r.qty_delta,
                "price": r.price,
                "fees_usd": r.fees_usd,
                "realized_pnl_this_fill_usd": r.realized_pnl_this_fill_usd,
            }
            for r in writer.rows
        ]
        pnl_table = aggregate_pnl_for_day(ledger_rows, date(2024, 6, 15))
        daily_pnl = pnl_table.to_pylist()[0]["realized_pnl_usd"]

        # RECONCILIATION CHECK: They must match!
        assert daily_pnl == pytest.approx(ledger_pnl_sum)

    def test_multi_wallet_reconciliation(self) -> None:
        """Each wallet's ledger PnL sum must match their wallet_pnl_daily total."""
        fills = [
            # Wallet A
            _fill(ts=_ts(0), wallet="0xAAA", side="buy", qty_delta=100.0, price=0.50),
            _fill(ts=_ts(1), wallet="0xAAA", side="sell", qty_delta=100.0, price=0.70),  # +20
            # Wallet B
            _fill(ts=_ts(2), wallet="0xBBB", side="buy", qty_delta=50.0, price=0.60),
            _fill(ts=_ts(3), wallet="0xBBB", side="sell", qty_delta=50.0, price=0.40),  # -10
            # Wallet C (complex)
            _fill(ts=_ts(4), wallet="0xCCC", side="buy", qty_delta=200.0, price=0.30),
            _fill(ts=_ts(5), wallet="0xCCC", side="sell", qty_delta=100.0, price=0.50),  # +20
            _fill(ts=_ts(6), wallet="0xCCC", side="sell", qty_delta=100.0, price=0.25),  # -5
        ]
        writer, _ = build_ledger_for_day(fills, {})

        # Group ledger rows by wallet and compute sums
        ledger_by_wallet: dict[str, float] = {}
        for r in writer.rows:
            ledger_by_wallet.setdefault(r.wallet, 0.0)
            ledger_by_wallet[r.wallet] += r.realized_pnl_this_fill_usd

        # Compute wallet_pnl_daily
        ledger_rows = [
            {
                "wallet": r.wallet,
                "qty_delta": r.qty_delta,
                "price": r.price,
                "fees_usd": r.fees_usd,
                "realized_pnl_this_fill_usd": r.realized_pnl_this_fill_usd,
            }
            for r in writer.rows
        ]
        pnl_table = aggregate_pnl_for_day(ledger_rows, date(2024, 6, 15))
        pnl_by_wallet = {r["wallet"]: r["realized_pnl_usd"] for r in pnl_table.to_pylist()}

        # RECONCILIATION CHECK: Each wallet must match
        for wallet in ledger_by_wallet:
            assert pnl_by_wallet[wallet] == pytest.approx(ledger_by_wallet[wallet])

        # Expected values
        assert pnl_by_wallet["0xAAA"] == pytest.approx(20.0)
        assert pnl_by_wallet["0xBBB"] == pytest.approx(-10.0)
        assert pnl_by_wallet["0xCCC"] == pytest.approx(15.0)  # 20 + (-5)

    def test_reconciliation_with_fees(self) -> None:
        """Fees should be tracked separately and reduce realized PnL."""
        fills = [
            _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.50, fees_usd=1.0),
            _fill(ts=_ts(1), side="sell", qty_delta=100.0, price=0.70, fees_usd=2.0),
        ]
        writer, _ = build_ledger_for_day(fills, {})

        # Ledger PnL sum (fees reduce the realized PnL on the sell)
        ledger_pnl_sum = sum(r.realized_pnl_this_fill_usd for r in writer.rows)
        # Expected: 0 (buy) + (100 * 0.20 - 2) = 18
        assert ledger_pnl_sum == pytest.approx(18.0)

        # Total fees from fills
        ledger_fees_sum = sum(r.fees_usd for r in writer.rows)
        assert ledger_fees_sum == pytest.approx(3.0)  # 1 + 2

        # Compute wallet_pnl_daily
        ledger_rows = [
            {
                "wallet": r.wallet,
                "qty_delta": r.qty_delta,
                "price": r.price,
                "fees_usd": r.fees_usd,
                "realized_pnl_this_fill_usd": r.realized_pnl_this_fill_usd,
            }
            for r in writer.rows
        ]
        pnl_table = aggregate_pnl_for_day(ledger_rows, date(2024, 6, 15))
        row = pnl_table.to_pylist()[0]

        # Reconciliation
        assert row["realized_pnl_usd"] == pytest.approx(ledger_pnl_sum)
        assert row["fees_usd"] == pytest.approx(ledger_fees_sum)


class TestComplexTradeSequences:
    """Additional complex scenarios to verify PnL accuracy."""

    def test_multiple_partial_closes(self) -> None:
        """Multiple partial sells should each realize PnL correctly.

        Buy 200 @ $0.40 → cost = $80, avg_cost = $0.40
        Sell 50 @ $0.60 → PnL = 50 * (0.60 - 0.40) = $10, qty=150
        Sell 100 @ $0.30 → PnL = 100 * (0.30 - 0.40) = -$10, qty=50
        Sell 50 @ $0.50 → PnL = 50 * (0.50 - 0.40) = $5, qty=0

        Total PnL = 10 + (-10) + 5 = $5
        """
        fills = [
            _fill(ts=_ts(0), side="buy", qty_delta=200.0, price=0.40),
            _fill(ts=_ts(1), side="sell", qty_delta=50.0, price=0.60),
            _fill(ts=_ts(2), side="sell", qty_delta=100.0, price=0.30),
            _fill(ts=_ts(3), side="sell", qty_delta=50.0, price=0.50),
        ]
        writer, positions = build_ledger_for_day(fills, {})
        rows = writer.rows

        # Verify individual fill PnL
        assert rows[0].realized_pnl_this_fill_usd == 0.0  # Buy
        assert rows[1].realized_pnl_this_fill_usd == pytest.approx(10.0)  # +$10
        assert rows[2].realized_pnl_this_fill_usd == pytest.approx(-10.0)  # -$10
        assert rows[3].realized_pnl_this_fill_usd == pytest.approx(5.0)  # +$5

        # Verify total
        total_pnl = sum(r.realized_pnl_this_fill_usd for r in rows)
        assert total_pnl == pytest.approx(5.0)

        # Verify closed
        key = ("0xTEST", "polymarket", "MKT1", "MKT1_0")
        assert positions[key].qty == 0.0

    def test_reopen_after_close(self) -> None:
        """Close a position and reopen - fresh cost basis.

        Sequence 1 (close):
            Buy 100 @ $0.50, Sell 100 @ $0.80 → PnL = $30

        Sequence 2 (reopen):
            Buy 50 @ $0.60, Sell 50 @ $0.40 → PnL = -$10

        Total PnL = $30 + (-$10) = $20
        """
        fills = [
            # First cycle
            _fill(ts=_ts(0), side="buy", qty_delta=100.0, price=0.50),
            _fill(ts=_ts(1), side="sell", qty_delta=100.0, price=0.80),
            # Second cycle (reopened)
            _fill(ts=_ts(2), side="buy", qty_delta=50.0, price=0.60),
            _fill(ts=_ts(3), side="sell", qty_delta=50.0, price=0.40),
        ]
        writer, positions = build_ledger_for_day(fills, {})
        rows = writer.rows

        # First sell: PnL = 100 * (0.80 - 0.50) = 30
        assert rows[1].realized_pnl_this_fill_usd == pytest.approx(30.0)
        # Second sell: PnL = 50 * (0.40 - 0.60) = -10
        assert rows[3].realized_pnl_this_fill_usd == pytest.approx(-10.0)

        total_pnl = sum(r.realized_pnl_this_fill_usd for r in rows)
        assert total_pnl == pytest.approx(20.0)

    def test_short_position_pnl(self) -> None:
        """Short position PnL: profit when price decreases.

        Open short via flip:
            Buy 50 @ $0.70, Sell 100 @ $0.60
            → Close long: 50 * (0.60 - 0.70) = -$5
            → Open short: 50 @ $0.60

        Close short:
            Buy 50 @ $0.40
            → Short PnL: 50 * (0.60 - 0.40) = $10 (profit)

        Total PnL = -5 + 10 = $5
        """
        fills = [
            _fill(ts=_ts(0), side="buy", qty_delta=50.0, price=0.70),
            _fill(ts=_ts(1), side="sell", qty_delta=100.0, price=0.60),  # Flip
            _fill(ts=_ts(2), side="buy", qty_delta=50.0, price=0.40),  # Close short
        ]
        writer, positions = build_ledger_for_day(fills, {})
        rows = writer.rows

        # Flip: closes long at loss
        assert rows[1].realized_pnl_this_fill_usd == pytest.approx(-5.0)
        assert rows[1].qty_after == -50.0  # Short position

        # Close short: profit
        assert rows[2].realized_pnl_this_fill_usd == pytest.approx(10.0)
        assert rows[2].qty_after == 0.0

        total_pnl = sum(r.realized_pnl_this_fill_usd for r in rows)
        assert total_pnl == pytest.approx(5.0)


class TestEdgeCasesPnL:
    """Edge cases for PnL calculations."""

    def test_price_zero_total_loss(self) -> None:
        """Selling at price 0 results in total loss of cost basis."""
        pos = PositionState(
            wallet="0xTEST", platform="polymarket", market_id="MKT1", outcome_id="MKT1_0"
        )
        pos.apply_fill("buy", 100.0, 0.50, 0.0, _ts(0))
        r = pos.apply_fill("sell", 100.0, 0.0, 0.0, _ts(1))

        # Loss = 100 * (0 - 0.50) = -50
        assert r.realized_pnl == pytest.approx(-50.0)

    def test_price_one_max_profit(self) -> None:
        """Selling at price 1.0 (resolved YES) gives max profit."""
        pos = PositionState(
            wallet="0xTEST", platform="polymarket", market_id="MKT1", outcome_id="MKT1_0"
        )
        pos.apply_fill("buy", 100.0, 0.30, 0.0, _ts(0))
        r = pos.apply_fill("sell", 100.0, 1.0, 0.0, _ts(1))

        # Profit = 100 * (1.0 - 0.30) = 70
        assert r.realized_pnl == pytest.approx(70.0)

    def test_very_small_quantities(self) -> None:
        """Fractional quantities should calculate correctly."""
        pos = PositionState(
            wallet="0xTEST", platform="polymarket", market_id="MKT1", outcome_id="MKT1_0"
        )
        pos.apply_fill("buy", 0.001, 0.50, 0.0, _ts(0))
        r = pos.apply_fill("sell", 0.001, 0.60, 0.0, _ts(1))

        # Profit = 0.001 * (0.60 - 0.50) = 0.0001
        assert r.realized_pnl == pytest.approx(0.0001)

    def test_breakeven_trade(self) -> None:
        """Trade at same price results in zero PnL."""
        pos = PositionState(
            wallet="0xTEST", platform="polymarket", market_id="MKT1", outcome_id="MKT1_0"
        )
        pos.apply_fill("buy", 100.0, 0.50, 0.0, _ts(0))
        r = pos.apply_fill("sell", 100.0, 0.50, 0.0, _ts(1))

        assert r.realized_pnl == pytest.approx(0.0)

    def test_high_fees_negative_pnl(self) -> None:
        """High fees can turn a winning trade into a loss."""
        pos = PositionState(
            wallet="0xTEST", platform="polymarket", market_id="MKT1", outcome_id="MKT1_0"
        )
        pos.apply_fill("buy", 100.0, 0.50, 0.0, _ts(0))
        # Gross PnL = 100 * (0.60 - 0.50) = 10, but fees = 15
        r = pos.apply_fill("sell", 100.0, 0.60, 15.0, _ts(1))

        assert r.realized_pnl == pytest.approx(-5.0)  # 10 - 15
