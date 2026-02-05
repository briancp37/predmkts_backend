"""Events service layer for ClickHouse queries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from prediction_data.api.clickhouse import (
    build_pagination,
    execute_query,
    execute_query_count,
)

if TYPE_CHECKING:
    from clickhouse_connect.driver.client import Client


async def get_events(
    client: Client,
    *,
    category: str | None = None,
    search: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch events from ClickHouse with filtering.

    Args:
        client: ClickHouse client.
        category: Filter by category (exact match).
        search: Search query for title/description (ILIKE).
        status: Filter by status (exact match).
        limit: Maximum number of results.
        offset: Offset for pagination.

    Returns:
        Tuple of (list of event dicts formatted for EventResponse, total count).
    """
    # Build WHERE conditions
    conditions: list[str] = []
    params: dict[str, Any] = {}

    if search:
        conditions.append(
            "(e.title ILIKE {search:String} OR e.description ILIKE {search:String})"
        )
        params["search"] = f"%{search}%"

    if category:
        conditions.append("e.category = {category:String}")
        params["category"] = category

    if status:
        conditions.append("e.status = {status:String}")
        params["status"] = status

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Build pagination
    pagination_clause, pagination_params = build_pagination(
        limit=limit, offset=offset, max_limit=500
    )
    params.update(pagination_params)

    # Get total count first
    count_query = f"""
        SELECT COUNT(DISTINCT e.platform_event_id)
        FROM prediction_gold.dim_event e
        WHERE {where_clause}
    """
    total = await execute_query_count(count_query, params, client=client)

    # Get events with market count
    events_query = f"""
        SELECT
            e.platform_event_id AS id,
            e.platform_event_id AS polymarketEventId,
            e.title,
            e.description,
            e.slug,
            e.status,
            e.category,
            e.updated_at AS updatedAt,
            count(m.platform_market_id) AS marketCount
        FROM prediction_gold.dim_event e
        LEFT JOIN prediction_gold.dim_market m
            ON m.platform = e.platform AND m.event_id = e.platform_event_id
        WHERE {where_clause}
        GROUP BY
            e.platform_event_id,
            e.title,
            e.description,
            e.slug,
            e.status,
            e.category,
            e.updated_at
        ORDER BY e.updated_at DESC
        {pagination_clause}
    """
    event_rows = await execute_query(events_query, params, client=client)

    if not event_rows:
        return [], total

    # Build response dicts (without full market details for list view)
    results: list[dict[str, Any]] = []
    for row in event_rows:
        results.append(
            {
                "id": row["id"],
                "polymarketEventId": row["polymarketEventId"],
                "title": row["title"] or "",
                "description": row.get("description"),
                "slug": row.get("slug") or "",
                "status": row.get("status") or "",
                "category": row.get("category"),
                "markets": [],  # Empty for list view, populated in detail view
            }
        )

    return results, total


async def get_event_by_id(
    client: Client,
    event_id: str,
) -> dict[str, Any] | None:
    """Fetch a single event by ID from ClickHouse.

    The event_id can be:
    - Platform event ID (platform_event_id)
    - Event slug

    Args:
        client: ClickHouse client.
        event_id: Event identifier (ID or slug).

    Returns:
        Event dict formatted for EventResponse with markets, or None if not found.
    """
    # Query event with flexible ID matching (ID or slug)
    event_query = """
        SELECT
            e.platform_event_id AS id,
            e.platform_event_id AS polymarketEventId,
            e.title,
            e.description,
            e.slug,
            e.status,
            e.category
        FROM prediction_gold.dim_event e
        WHERE e.platform_event_id = {event_id:String}
           OR e.slug = {event_id:String}
        LIMIT 1
    """
    event_rows = await execute_query(
        event_query, {"event_id": event_id}, client=client
    )

    if not event_rows:
        return None

    row = event_rows[0]
    event_id_resolved = row["id"]

    # Query associated markets
    markets_query = """
        SELECT
            m.platform_market_id AS id,
            m.platform_market_id AS polymarketId,
            m.canonical_market_id AS conditionId,
            m.market_slug AS slug,
            m.question,
            m.description,
            m.status,
            m.updated_at AS updatedAt
        FROM prediction_gold.dim_market m
        WHERE m.platform = 'polymarket'
            AND m.event_id = {event_id:String}
        ORDER BY m.updated_at DESC
    """
    market_rows = await execute_query(
        markets_query, {"event_id": event_id_resolved}, client=client
    )

    # Build markets list
    markets: list[dict[str, Any]] = []
    for market in market_rows:
        # Format updated_at as ISO string
        updated_at = market.get("updatedAt")
        created_at_str = ""
        if updated_at:
            if hasattr(updated_at, "isoformat"):
                created_at_str = updated_at.isoformat()
            else:
                created_at_str = str(updated_at)

        markets.append(
            {
                "id": market["id"],
                "polymarketId": market["polymarketId"],
                "conditionId": market.get("conditionId"),
                "slug": market.get("slug"),
                "question": market.get("question") or "",
                "description": market.get("description"),
                "category": row.get("category"),  # Use event category
                "endDate": None,  # Not in current schema
                "resolved": market.get("status") == "resolved",
                "totalVolume": 0.0,  # Would come from market_mark_daily aggregate
                "liquidity": 0.0,  # Would come from CLOB or market_mark_daily
                "createdAt": created_at_str,
                "imageUrl": None,  # Not in current schema
            }
        )

    return {
        "id": event_id_resolved,
        "polymarketEventId": row["polymarketEventId"],
        "title": row["title"] or "",
        "description": row.get("description"),
        "slug": row.get("slug") or "",
        "status": row.get("status") or "",
        "category": row.get("category"),
        "markets": markets,
    }
