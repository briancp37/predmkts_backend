"""Core average-cost position accounting engine.

Implements FIFO-style average-cost accounting for prediction market positions.
Given a sequence of fills (buys and sells), tracks position state and computes
realized PnL on each fill.

Accounting rules:
- Buy: new_avg_cost = (old_qty * old_avg_cost + qty_delta * price) / new_qty
- Sell: realized_pnl = qty_delta * (price - avg_cost), avg_cost unchanged
- Close: qty → 0, emit final realized PnL
- Flip: oversized sell splits into close (realize PnL) + open (new direction)
"""

from __future__ import annotations

import dataclasses
from datetime import datetime


@dataclasses.dataclass(slots=True)
class FillResult:
    """Result of applying a single fill to a position."""

    realized_pnl: float
    closed: bool


@dataclasses.dataclass(slots=True)
class PositionState:
    """Mutable position state for a single wallet/platform/market/outcome.

    Tracks quantity, average cost, cost basis, and last fill timestamp.
    Positive qty = long, negative qty = short (from flips).
    """

    wallet: str
    platform: str
    market_id: str
    outcome_id: str
    qty: float = 0.0
    avg_cost: float = 0.0
    cost_basis_usd: float = 0.0
    last_fill_ts: datetime | None = None
    first_open_ts: datetime | None = None

    @property
    def is_open(self) -> bool:
        """Whether the position has a nonzero quantity."""
        return self.qty != 0.0

    def apply_fill(
        self,
        side: str,
        qty_delta: float,
        price: float,
        fees: float,
        ts: datetime,
    ) -> FillResult:
        """Apply a fill to this position and return the result.

        Args:
            side: "buy" or "sell".
            qty_delta: Absolute quantity of the fill (always positive).
            price: Fill price per unit.
            fees: Fees in USD for this fill.
            ts: Timestamp of the fill.

        Returns:
            FillResult with realized_pnl and whether the position was closed.

        Raises:
            ValueError: If side is not "buy" or "sell", or qty_delta <= 0.
        """
        if side not in ("buy", "sell"):
            msg = f"side must be 'buy' or 'sell', got {side!r}"
            raise ValueError(msg)
        if qty_delta <= 0:
            msg = f"qty_delta must be positive, got {qty_delta}"
            raise ValueError(msg)

        self.last_fill_ts = ts

        # Track when the position was first opened.
        if self.qty == 0.0:
            self.first_open_ts = ts

        # Convert to signed delta: buys increase qty, sells decrease.
        signed_delta = qty_delta if side == "buy" else -qty_delta

        # Determine whether this fill increases or reduces the position.
        if self._is_increasing(signed_delta):
            return self._apply_increase(signed_delta, price, fees)

        return self._apply_reduce(signed_delta, price, fees)

    def _is_increasing(self, signed_delta: float) -> bool:
        """Check if the fill increases the position (same direction or opening)."""
        if self.qty == 0.0:
            return True
        # Same sign means increasing.
        return (self.qty > 0) == (signed_delta > 0)

    def _apply_increase(
        self,
        signed_delta: float,
        price: float,
        fees: float,
    ) -> FillResult:
        """Apply a fill that increases (or opens) the position."""
        abs_delta = abs(signed_delta)
        old_qty = self.qty
        new_qty = old_qty + signed_delta

        if old_qty == 0.0:
            # Opening a new position.
            self.avg_cost = price
        else:
            # Weighted average cost.
            self.avg_cost = (
                abs(old_qty) * self.avg_cost + abs_delta * price
            ) / abs(new_qty)

        self.qty = new_qty
        self.cost_basis_usd = abs(self.qty) * self.avg_cost + fees
        return FillResult(realized_pnl=0.0, closed=False)

    def _apply_reduce(
        self,
        signed_delta: float,
        price: float,
        fees: float,
    ) -> FillResult:
        """Apply a fill that reduces, closes, or flips the position."""
        abs_delta = abs(signed_delta)
        abs_qty = abs(self.qty)

        if abs_delta <= abs_qty:
            # Partial close or exact close.
            realized_pnl = self._compute_realized_pnl(abs_delta, price, fees)
            self.qty += signed_delta
            closed = self.qty == 0.0

            if closed:
                self.cost_basis_usd = 0.0
                self.first_open_ts = None
            else:
                self.cost_basis_usd = abs(self.qty) * self.avg_cost

            return FillResult(realized_pnl=realized_pnl, closed=closed)

        # Position flip: close existing + open in opposite direction.
        # Step 1: Close the existing position entirely.
        close_pnl = self._compute_realized_pnl(abs_qty, price, fees)

        # Step 2: Open new position with the remainder.
        remainder = abs_delta - abs_qty
        # New position is in the direction of signed_delta.
        if signed_delta > 0:
            self.qty = remainder
        else:
            self.qty = -remainder
        self.avg_cost = price
        self.cost_basis_usd = remainder * price
        self.first_open_ts = self.last_fill_ts

        return FillResult(realized_pnl=close_pnl, closed=False)

    def _compute_realized_pnl(
        self,
        close_qty: float,
        price: float,
        fees: float,
    ) -> float:
        """Compute realized PnL for closing close_qty units.

        For long positions: pnl = close_qty * (price - avg_cost) - fees
        For short positions: pnl = close_qty * (avg_cost - price) - fees
        """
        if self.qty > 0:
            return close_qty * (price - self.avg_cost) - fees
        return close_qty * (self.avg_cost - price) - fees
