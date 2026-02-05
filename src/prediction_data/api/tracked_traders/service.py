"""Tracked traders service layer for business logic."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import CursorResult

from prediction_data.api.clickhouse import execute_query
from prediction_data.db.models.tracked_trader import TrackedTrader
from prediction_data.db.models.user import User, UserTier

if TYPE_CHECKING:
    from clickhouse_connect.driver.client import Client
    from sqlalchemy.ext.asyncio import AsyncSession


# Tier limits for tracked traders
TIER_LIMITS: dict[UserTier, int] = {
    UserTier.FREE: 6,
    UserTier.PRO: 50,
}


def get_tier_limit(tier: UserTier) -> int:
    """Get the tracked traders limit for a user tier.

    Args:
        tier: User's subscription tier.

    Returns:
        Maximum number of tracked traders allowed.
    """
    return TIER_LIMITS.get(tier, TIER_LIMITS[UserTier.FREE])


async def get_tracked_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Get count of tracked traders for a user.

    Args:
        db: Database session.
        user_id: User's UUID.

    Returns:
        Number of tracked traders.
    """
    result = await db.execute(
        select(func.count()).select_from(TrackedTrader).where(
            TrackedTrader.user_id == user_id
        )
    )
    return result.scalar_one()


def check_tier_limit(tier: UserTier, current_count: int) -> bool:
    """Check if user can add more tracked traders.

    Args:
        tier: User's subscription tier.
        current_count: Current number of tracked traders.

    Returns:
        True if user can add more, False if limit reached.
    """
    limit = get_tier_limit(tier)
    return current_count < limit


async def get_user_tracked_traders(
    db: AsyncSession, user_id: uuid.UUID
) -> list[TrackedTrader]:
    """Get all tracked traders for a user.

    Args:
        db: Database session.
        user_id: User's UUID.

    Returns:
        List of TrackedTrader entries ordered by created_at DESC.
    """
    result = await db.execute(
        select(TrackedTrader)
        .where(TrackedTrader.user_id == user_id)
        .order_by(TrackedTrader.created_at.desc())
    )
    return list(result.scalars().all())


async def get_tracked_trader_by_id(
    db: AsyncSession, user_id: uuid.UUID, tracker_id: uuid.UUID
) -> TrackedTrader | None:
    """Get a single tracked trader by ID for a user.

    Args:
        db: Database session.
        user_id: User's UUID.
        tracker_id: TrackedTrader UUID.

    Returns:
        TrackedTrader if found and owned by user, None otherwise.
    """
    result = await db.execute(
        select(TrackedTrader).where(
            TrackedTrader.id == tracker_id,
            TrackedTrader.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_tracked_trader_by_address(
    db: AsyncSession, user_id: uuid.UUID, address: str
) -> TrackedTrader | None:
    """Check if a trader address is already tracked by user.

    Args:
        db: Database session.
        user_id: User's UUID.
        address: Trader wallet address (normalized to lowercase).

    Returns:
        TrackedTrader if exists, None otherwise.
    """
    result = await db.execute(
        select(TrackedTrader).where(
            TrackedTrader.user_id == user_id,
            TrackedTrader.trader_address == address.lower(),
        )
    )
    return result.scalar_one_or_none()


async def add_tracked_trader(
    db: AsyncSession,
    user_id: uuid.UUID,
    address: str,
    custom_name: str | None = None,
) -> TrackedTrader:
    """Add a trader to user's tracked list.

    Args:
        db: Database session.
        user_id: User's UUID.
        address: Trader wallet address.
        custom_name: Optional custom name for the trader.

    Returns:
        Created TrackedTrader entry.
    """
    tracker = TrackedTrader(
        user_id=user_id,
        trader_address=address.lower(),
        custom_name=custom_name,
    )
    db.add(tracker)
    await db.flush()
    await db.refresh(tracker)
    return tracker


async def remove_tracked_trader(
    db: AsyncSession, user_id: uuid.UUID, tracker_id: uuid.UUID
) -> bool:
    """Remove a trader from user's tracked list.

    Args:
        db: Database session.
        user_id: User's UUID.
        tracker_id: TrackedTrader UUID.

    Returns:
        True if an entry was deleted, False if not found.
    """
    result = await db.execute(
        delete(TrackedTrader).where(
            TrackedTrader.id == tracker_id,
            TrackedTrader.user_id == user_id,
        )
    )
    cursor_result = cast(CursorResult[Any], result)
    return cursor_result.rowcount > 0


async def update_tracked_trader(
    db: AsyncSession,
    user_id: uuid.UUID,
    tracker_id: uuid.UUID,
    custom_name: str | None,
) -> TrackedTrader | None:
    """Update a tracked trader's custom name.

    Args:
        db: Database session.
        user_id: User's UUID.
        tracker_id: TrackedTrader UUID.
        custom_name: New custom name (or None to clear).

    Returns:
        Updated TrackedTrader if found, None otherwise.
    """
    result = await db.execute(
        update(TrackedTrader)
        .where(
            TrackedTrader.id == tracker_id,
            TrackedTrader.user_id == user_id,
        )
        .values(custom_name=custom_name)
        .returning(TrackedTrader)
    )
    return result.scalar_one_or_none()


async def get_tracked_addresses(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """Get list of all tracked trader addresses for a user.

    Args:
        db: Database session.
        user_id: User's UUID.

    Returns:
        List of trader addresses (lowercase).
    """
    result = await db.execute(
        select(TrackedTrader.trader_address).where(TrackedTrader.user_id == user_id)
    )
    return list(result.scalars().all())


async def trader_exists_in_clickhouse(ch: Client, address: str) -> bool:
    """Check if a trader/wallet exists in ClickHouse dim_wallet.

    Args:
        ch: ClickHouse client.
        address: Wallet address to check.

    Returns:
        True if wallet exists in dim_wallet.
    """
    query = """
        SELECT 1
        FROM prediction_gold.dim_wallet
        WHERE wallet_address = {address:String}
        LIMIT 1
    """
    rows = await execute_query(query, {"address": address.lower()}, client=ch)
    return len(rows) > 0


async def get_trader_stats(
    ch: Client, addresses: list[str]
) -> dict[str, dict[str, Any]]:
    """Get trader stats from ClickHouse.

    Args:
        ch: ClickHouse client.
        addresses: List of wallet addresses.

    Returns:
        Dict mapping address to stats (totalPnl, recentTrades, smartScore).
    """
    if not addresses:
        return {}

    # Normalize addresses to lowercase
    normalized = [addr.lower() for addr in addresses]

    # Get total PnL from wallet_pnl_daily
    pnl_query = """
        SELECT
            wallet_address,
            sum(realized_pnl) AS total_pnl
        FROM prediction_gold.wallet_pnl_daily
        WHERE wallet_address IN {addresses:Array(String)}
        GROUP BY wallet_address
    """

    # Get recent trade count (last 7 days)
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
        "%Y-%m-%d"
    )
    trades_query = """
        SELECT
            wallet_address,
            count(*) AS trade_count
        FROM prediction_gold.wallet_position_ledger
        WHERE wallet_address IN {addresses:Array(String)}
          AND day >= {seven_days_ago:String}
        GROUP BY wallet_address
    """

    results: dict[str, dict[str, Any]] = {addr: {} for addr in normalized}

    try:
        pnl_rows = await execute_query(pnl_query, {"addresses": normalized}, client=ch)
        for row in pnl_rows:
            addr = row["wallet_address"]
            if addr in results:
                results[addr]["totalPnl"] = float(row.get("total_pnl", 0) or 0)
    except Exception:
        pass

    try:
        trade_rows = await execute_query(
            trades_query,
            {"addresses": normalized, "seven_days_ago": seven_days_ago},
            client=ch,
        )
        for row in trade_rows:
            addr = row["wallet_address"]
            if addr in results:
                results[addr]["recentTrades"] = int(row.get("trade_count", 0) or 0)
    except Exception:
        pass

    # Fill in defaults
    for addr in normalized:
        if "totalPnl" not in results[addr]:
            results[addr]["totalPnl"] = 0.0
        if "recentTrades" not in results[addr]:
            results[addr]["recentTrades"] = 0
        results[addr]["smartScore"] = None  # TODO: implement smart score lookup

    return results


async def get_tracked_trader_activity(
    ch: Client,
    addresses: list[str],
    limit: int = 50,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """Get recent activity for tracked traders.

    Args:
        ch: ClickHouse client.
        addresses: List of wallet addresses.
        limit: Maximum number of activities to return.
        start_date: Optional start date filter (YYYY-MM-DD).
        end_date: Optional end date filter (YYYY-MM-DD).

    Returns:
        List of activity records with trade details.
    """
    if not addresses:
        return []

    normalized = [addr.lower() for addr in addresses]

    # Build date filter
    date_filters = []
    params: dict[str, Any] = {"addresses": normalized, "limit": limit}

    if start_date:
        date_filters.append("wpl.day >= {start_date:String}")
        params["start_date"] = start_date

    if end_date:
        date_filters.append("wpl.day <= {end_date:String}")
        params["end_date"] = end_date

    date_clause = f"AND {' AND '.join(date_filters)}" if date_filters else ""

    query = f"""
        SELECT
            wpl.id AS trade_id,
            wpl.wallet_address AS trader_address,
            wpl.market_id,
            m.question AS market_question,
            wpl.outcome_id,
            o.name AS outcome_name,
            wpl.side,
            wpl.price,
            wpl.qty_delta AS quantity,
            wpl.price * wpl.qty_delta AS usd_value,
            wpl.fees,
            wpl.realized_pnl,
            wpl.timestamp
        FROM prediction_gold.wallet_position_ledger wpl
        LEFT JOIN prediction_gold.dim_market m
            ON wpl.market_id = m.platform_market_id
        LEFT JOIN prediction_gold.dim_outcome o
            ON wpl.outcome_id = o.platform_outcome_id
        WHERE wpl.wallet_address IN {{addresses:Array(String)}}
        {date_clause}
        ORDER BY wpl.timestamp DESC
        LIMIT {{limit:UInt32}}
    """

    try:
        rows = await execute_query(query, params, client=ch)
        return list(rows)
    except Exception:
        return []
