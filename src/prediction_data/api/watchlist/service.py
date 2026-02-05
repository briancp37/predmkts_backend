"""Watchlist service layer for business logic."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult

from prediction_data.api.clickhouse import execute_query
from prediction_data.db.models.watchlist import Watchlist

if TYPE_CHECKING:
    from clickhouse_connect.driver.client import Client
    from sqlalchemy.ext.asyncio import AsyncSession


async def get_user_watchlist(db: AsyncSession, user_id: uuid.UUID) -> list[Watchlist]:
    """Get all watchlist items for a user.

    Args:
        db: Database session.
        user_id: User's UUID.

    Returns:
        List of Watchlist entries ordered by created_at DESC.
    """
    result = await db.execute(
        select(Watchlist)
        .where(Watchlist.user_id == user_id)
        .order_by(Watchlist.created_at.desc())
    )
    return list(result.scalars().all())


async def add_to_watchlist(
    db: AsyncSession, user_id: uuid.UUID, market_id: str
) -> Watchlist:
    """Add a market to user's watchlist.

    Args:
        db: Database session.
        user_id: User's UUID.
        market_id: Market ID to add.

    Returns:
        Created Watchlist entry.
    """
    watchlist = Watchlist(user_id=user_id, market_id=market_id)
    db.add(watchlist)
    await db.flush()
    await db.refresh(watchlist)
    return watchlist


async def remove_from_watchlist(
    db: AsyncSession, user_id: uuid.UUID, market_id: str
) -> bool:
    """Remove a market from user's watchlist.

    Args:
        db: Database session.
        user_id: User's UUID.
        market_id: Market ID to remove.

    Returns:
        True if an entry was deleted, False if not found.
    """
    result = await db.execute(
        delete(Watchlist).where(
            Watchlist.user_id == user_id,
            Watchlist.market_id == market_id,
        )
    )
    cursor_result = cast(CursorResult[Any], result)
    return cursor_result.rowcount > 0


async def is_in_watchlist(
    db: AsyncSession, user_id: uuid.UUID, market_id: str
) -> bool:
    """Check if a market is in user's watchlist.

    Args:
        db: Database session.
        user_id: User's UUID.
        market_id: Market ID to check.

    Returns:
        True if market is in watchlist.
    """
    result = await db.execute(
        select(Watchlist.id).where(
            Watchlist.user_id == user_id,
            Watchlist.market_id == market_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def market_exists(ch: Client, market_id: str) -> bool:
    """Check if a market exists in ClickHouse.

    Args:
        ch: ClickHouse client.
        market_id: Market ID to check.

    Returns:
        True if market exists.
    """
    query = """
        SELECT 1
        FROM prediction_gold.dim_market
        WHERE platform_market_id = {market_id:String}
        LIMIT 1
    """
    rows = await execute_query(query, {"market_id": market_id}, client=ch)
    return len(rows) > 0


async def get_market_details(
    ch: Client, market_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """Get market details from ClickHouse for enrichment.

    Args:
        ch: ClickHouse client.
        market_ids: List of market IDs to fetch.

    Returns:
        Dict mapping market_id to market details.
    """
    if not market_ids:
        return {}

    # Get market info with event category
    market_query = """
        SELECT
            m.platform_market_id AS market_id,
            m.question,
            e.category,
            m.status
        FROM prediction_gold.dim_market m
        LEFT JOIN prediction_gold.dim_event e
            ON m.platform = e.platform AND m.event_id = e.platform_event_id
        WHERE m.platform_market_id IN {market_ids:Array(String)}
    """
    market_rows = await execute_query(
        market_query, {"market_ids": market_ids}, client=ch
    )

    # Get latest prices and 24h changes from market_mark_daily
    price_query = """
        SELECT
            market_id,
            argMax(close_price, day) AS current_price,
            arrayElement(
                groupArray((day, close_price)) AS prices,
                length(prices) - 1
            ).2 AS prev_price
        FROM prediction_gold.market_mark_daily
        WHERE market_id IN {market_ids:Array(String)}
        GROUP BY market_id
    """
    try:
        price_rows = await execute_query(
            price_query, {"market_ids": market_ids}, client=ch
        )
    except Exception:
        # If market_mark_daily doesn't exist or has issues, continue without prices
        price_rows = []

    # Build price lookup
    price_by_market: dict[str, dict[str, float]] = {}
    for row in price_rows:
        market_id = row["market_id"]
        current = row.get("current_price", 0.5)
        prev = row.get("prev_price", 0.5)
        price_change = current - prev if prev else 0.0
        price_by_market[market_id] = {
            "currentPrice": float(current or 0.5),
            "priceChange24h": float(price_change),
        }

    # Build result dict
    results: dict[str, dict[str, Any]] = {}
    for row in market_rows:
        market_id = row["market_id"]
        prices = price_by_market.get(
            market_id, {"currentPrice": 0.5, "priceChange24h": 0.0}
        )
        results[market_id] = {
            "marketQuestion": row["question"] or "",
            "marketCategory": row.get("category"),
            "resolved": row.get("status") == "resolved",
            **prices,
        }

    return results
