"""Convert Silver trades into maker + taker fill events.

Each Silver trade row represents a single match between a maker and a taker.
This module splits each trade into two fill records—one per counterparty—so
the accounting engine can track positions for every wallet independently.

Outcome ID mapping:
    nonusdc_side "token1" → outcome_id = "{market_id}_0"
    nonusdc_side "token2" → outcome_id = "{market_id}_1"
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any


@dataclasses.dataclass(slots=True, frozen=True)
class Fill:
    """A single fill event for one side of a trade."""

    ts: datetime
    wallet: str
    platform: str
    market_id: str
    outcome_id: str
    side: str
    qty_delta: float
    price: float
    fees_usd: float


_NONUSDC_SIDE_TO_INDEX: dict[str, int] = {
    "token1": 0,
    "token2": 1,
}


def nonusdc_side_to_outcome_id(market_id: str, nonusdc_side: str) -> str:
    """Map a nonusdc_side value to an outcome_id.

    Args:
        market_id: The platform market ID.
        nonusdc_side: One of ``"token1"`` or ``"token2"``.

    Returns:
        Deterministic outcome ID of the form ``"{market_id}_{idx}"``.

    Raises:
        ValueError: If *nonusdc_side* is not ``"token1"`` or ``"token2"``.
    """
    idx = _NONUSDC_SIDE_TO_INDEX.get(nonusdc_side)
    if idx is None:
        msg = f"nonusdc_side must be 'token1' or 'token2', got {nonusdc_side!r}"
        raise ValueError(msg)
    return f"{market_id}_{idx}"


def split_trade_to_fills(
    trade: dict[str, Any],
    *,
    platform: str = "polymarket",
) -> tuple[Fill, Fill]:
    """Split a single Silver trade row into maker and taker fills.

    Args:
        trade: A dict with Silver trade fields (``event_ts``,
            ``platform_market_id``, ``maker``, ``taker``,
            ``nonusdc_side``, ``maker_direction``, ``taker_direction``,
            ``token_amount``, ``price``).
        platform: Platform identifier (default ``"polymarket"``).

    Returns:
        A ``(maker_fill, taker_fill)`` tuple.

    Raises:
        KeyError: If a required field is missing from *trade*.
        ValueError: If *nonusdc_side* is invalid.
    """
    market_id: str = trade["platform_market_id"]
    outcome_id = nonusdc_side_to_outcome_id(market_id, trade["nonusdc_side"])

    ts: datetime = trade["event_ts"]
    qty: float = float(trade["token_amount"])
    price: float = float(trade["price"])

    maker_fill = Fill(
        ts=ts,
        wallet=trade["maker"],
        platform=platform,
        market_id=market_id,
        outcome_id=outcome_id,
        side=trade["maker_direction"],
        qty_delta=qty,
        price=price,
        fees_usd=0.0,
    )

    taker_fill = Fill(
        ts=ts,
        wallet=trade["taker"],
        platform=platform,
        market_id=market_id,
        outcome_id=outcome_id,
        side=trade["taker_direction"],
        qty_delta=qty,
        price=price,
        fees_usd=0.0,
    )

    return maker_fill, taker_fill


def trades_to_fills(
    trades: list[dict[str, Any]],
    *,
    platform: str = "polymarket",
) -> list[Fill]:
    """Convert a batch of Silver trades into sorted fill events.

    Each trade produces two fills (one per counterparty). The resulting list
    is sorted by timestamp, which is critical for correct position accounting.

    Args:
        trades: List of Silver trade dicts.
        platform: Platform identifier (default ``"polymarket"``).

    Returns:
        List of :class:`Fill` objects sorted by ``ts``.
    """
    fills: list[Fill] = []
    for trade in trades:
        maker_fill, taker_fill = split_trade_to_fills(trade, platform=platform)
        fills.append(maker_fill)
        fills.append(taker_fill)

    fills.sort(key=lambda f: f.ts)
    return fills
