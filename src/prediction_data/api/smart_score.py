"""Smart score computation for traders.

This module implements the smart score calculation algorithm that evaluates
trader performance across multiple dimensions. Smart scores are computed
from ClickHouse data (wallet_pnl_daily, wallet_position_ledger).

Smart Score Components (0-100 range):
- Accuracy (30%): Win rate on closed positions (0-30 points)
- Consistency (25%): Trade regularity and return consistency (0-25 points)
- Sizing (25%): Volume and position size discipline (0-25 points)
- Timing (20%): ROI efficiency relative to volume traded (-20 to +20 points)

The algorithm requires a minimum of 5 trades for meaningful scores.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from prediction_data.api.clickhouse import execute_query

if TYPE_CHECKING:
    from clickhouse_connect.driver.client import Client


@dataclass
class SmartScoreComponents:
    """Individual components that make up a smart score."""

    accuracy: float  # 0-30 based on win rate
    consistency: float  # 0-25 based on trade regularity
    sizing: float  # 0-25 based on volume (log scale)
    timing: float  # -20 to +20 based on ROI


@dataclass
class SmartScoreResult:
    """Result of smart score computation for a trader."""

    address: str
    smart_score: float
    components: SmartScoreComponents


def _clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value between min and max."""
    return max(min_val, min(max_val, value))


def _compute_score_from_stats(
    *,
    total_pnl: float,
    total_trades: int,
    wins: int,
    losses: int,
    total_volume: float,
    trade_days: int,
    lookback_days: int = 30,
) -> tuple[float, SmartScoreComponents]:
    """Calculate smart score from trader statistics.

    The scoring algorithm mirrors the frontend implementation with 4 weighted
    components that sum to a final score in the range [0, 100]:

    1. Accuracy (0-30 points): Based on win rate
       - 50% win rate = 15 points
       - 70% win rate = 21 points
       - 100% win rate = 30 points

    2. Consistency (0-25 points): Based on trading regularity
       - How many days they traded relative to the lookback period
       - Trading every day = 25 points

    3. Sizing/Volume (0-25 points): Log-scale based on total volume
       - $10 = 5 pts, $100 = 10 pts, $1,000 = 15 pts
       - $10,000 = 20 pts, $100,000 = 25 pts

    4. Timing/ROI (-20 to +20 points): Return on investment
       - Positive ROI increases score
       - Negative ROI decreases score
       - Capped at ±20 points

    Args:
        total_pnl: Total realized PnL in USD.
        total_trades: Total number of trades.
        wins: Number of winning trades.
        losses: Number of losing trades.
        total_volume: Total volume traded in USD.
        trade_days: Number of unique days with trades.
        lookback_days: The period over which stats were computed (default 30).

    Returns:
        Tuple of (final_score, components).
    """
    # Default components if insufficient data
    if total_trades < 5:
        return 0.0, SmartScoreComponents(
            accuracy=0.0, consistency=0.0, sizing=0.0, timing=0.0
        )

    # 1. Accuracy (0-30 points): Win rate
    total_closed = wins + losses
    win_rate = wins / total_closed if total_closed > 0 else 0.0
    accuracy_score = win_rate * 30

    # 2. Consistency (0-25 points): Trade regularity
    # How often they trade relative to the lookback period
    consistency_ratio = min(trade_days / lookback_days, 1.0)
    consistency_score = consistency_ratio * 25

    # 3. Sizing/Volume (0-25 points): Log-scale volume score
    # $10 = 5, $100 = 10, $1000 = 15, $10000 = 20, $100000 = 25
    if total_volume > 0:
        sizing_score = _clamp(math.log10(total_volume) * 5, 0, 25)
    else:
        sizing_score = 0.0

    # 4. Timing/ROI (-20 to +20 points): Return on investment
    # Based on PnL relative to volume traded
    if total_volume > 0:
        roi_percent = (total_pnl / total_volume) * 100
        timing_score = _clamp(roi_percent * 0.2, -20, 20)
    else:
        timing_score = 0.0

    # Combine all components
    raw_score = accuracy_score + consistency_score + sizing_score + timing_score

    # Final score range: 0-100 (clamped from theoretical -20 to +100)
    final_score = _clamp(raw_score, 0, 100)

    components = SmartScoreComponents(
        accuracy=round(accuracy_score, 2),
        consistency=round(consistency_score, 2),
        sizing=round(sizing_score, 2),
        timing=round(timing_score, 2),
    )

    return round(final_score, 2), components


async def compute_smart_score(
    client: Client,
    wallet_address: str,
    *,
    lookback_days: int = 30,
) -> SmartScoreResult | None:
    """Compute smart score for a single wallet.

    Queries ClickHouse to get trader statistics over the lookback period
    and computes the smart score with component breakdown.

    Args:
        client: ClickHouse client.
        wallet_address: Wallet address (will be normalized to lowercase).
        lookback_days: Number of days to look back for statistics.

    Returns:
        SmartScoreResult with score and components, or None if trader not found.
    """
    address = wallet_address.lower()

    # Query aggregated stats from wallet_pnl_daily
    query = """
        SELECT
            wallet,
            SUM(realized_pnl_usd) AS total_pnl,
            SUM(trades_count) AS total_trades,
            SUM(wins) AS wins,
            SUM(losses) AS losses,
            SUM(volume_usd) AS total_volume,
            COUNT(DISTINCT day_utc) AS trade_days
        FROM prediction_gold.wallet_pnl_daily
        WHERE wallet = {address:String}
            AND day_utc >= today() - {lookback_days:UInt32}
        GROUP BY wallet
    """

    rows = await execute_query(
        query, {"address": address, "lookback_days": lookback_days}, client=client
    )

    if not rows:
        return None

    row = rows[0]
    total_pnl = float(row["total_pnl"])
    total_trades = int(row["total_trades"])
    wins = int(row["wins"])
    losses = int(row["losses"])
    total_volume = float(row["total_volume"])
    trade_days = int(row["trade_days"])

    score, components = _compute_score_from_stats(
        total_pnl=total_pnl,
        total_trades=total_trades,
        wins=wins,
        losses=losses,
        total_volume=total_volume,
        trade_days=trade_days,
        lookback_days=lookback_days,
    )

    return SmartScoreResult(
        address=address,
        smart_score=score,
        components=components,
    )


async def compute_smart_scores_batch(
    client: Client,
    *,
    min_score: float = 0.0,
    lookback_days: int = 30,
    limit: int = 100,
    time_window: str | None = None,
) -> list[SmartScoreResult]:
    """Compute smart scores for multiple wallets.

    Queries ClickHouse to get trader statistics for all wallets with
    sufficient trading activity and computes smart scores in batch.

    Args:
        client: ClickHouse client.
        min_score: Minimum smart score to include in results.
        lookback_days: Number of days to look back for statistics.
            Overridden by time_window if provided.
        limit: Maximum number of results.
        time_window: Time window string ('7d', '30d', '90d', 'all').
            Overrides lookback_days if provided.

    Returns:
        List of SmartScoreResult ordered by smart_score DESC.
    """
    # Translate time_window to lookback_days
    if time_window == "7d":
        lookback_days = 7
    elif time_window == "30d":
        lookback_days = 30
    elif time_window == "90d":
        lookback_days = 90
    elif time_window == "all":
        lookback_days = 36500  # ~100 years, effectively all-time

    # Build date filter
    if time_window == "all":
        date_filter = "1=1"
    else:
        date_filter = "day_utc >= today() - {lookback_days:UInt32}"

    # Query aggregated stats from wallet_pnl_daily for all wallets
    query = f"""
        SELECT
            wallet,
            SUM(realized_pnl_usd) AS total_pnl,
            SUM(trades_count) AS total_trades,
            SUM(wins) AS wins,
            SUM(losses) AS losses,
            SUM(volume_usd) AS total_volume,
            COUNT(DISTINCT day_utc) AS trade_days
        FROM prediction_gold.wallet_pnl_daily
        WHERE {date_filter}
        GROUP BY wallet
        HAVING SUM(trades_count) >= 5
        ORDER BY SUM(realized_pnl_usd) DESC
    """

    params: dict[str, Any] = {"lookback_days": lookback_days}
    rows = await execute_query(query, params, client=client)

    # Compute scores for all wallets
    results: list[SmartScoreResult] = []
    for row in rows:
        total_pnl = float(row["total_pnl"])
        total_trades = int(row["total_trades"])
        wins = int(row["wins"])
        losses = int(row["losses"])
        total_volume = float(row["total_volume"])
        trade_days = int(row["trade_days"])

        score, components = _compute_score_from_stats(
            total_pnl=total_pnl,
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            total_volume=total_volume,
            trade_days=trade_days,
            lookback_days=lookback_days if time_window != "all" else trade_days,
        )

        if score >= min_score:
            results.append(
                SmartScoreResult(
                    address=str(row["wallet"]),
                    smart_score=score,
                    components=components,
                )
            )

    # Sort by smart_score DESC and limit
    results.sort(key=lambda x: x.smart_score, reverse=True)
    return results[:limit]
