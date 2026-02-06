"""Events service layer for ClickHouse queries."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from prediction_data.api.clickhouse import (
    build_pagination,
    execute_query,
    execute_query_count,
)

if TYPE_CHECKING:
    from clickhouse_connect.driver.client import Client


def _parse_tokens_to_outcomes(
    market_id: str, tokens_json: str | None
) -> list[dict[str, Any]]:
    """Parse tokens JSON string into outcome dicts.

    Args:
        market_id: The market ID for generating outcome IDs.
        tokens_json: JSON string of tokens array.

    Returns:
        List of outcome dicts with id, tokenId, outcomeName, currentPrice, volume,
        priceChange24h.
    """
    if not tokens_json:
        return []

    try:
        tokens = json.loads(tokens_json)
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(tokens, list):
        return []

    outcomes: list[dict[str, Any]] = []
    for idx, token in enumerate(tokens):
        if not isinstance(token, dict):
            continue

        token_id = str(token.get("token_id", ""))
        outcome_name = str(token.get("outcome", f"Outcome {idx + 1}"))

        outcomes.append(
            {
                "id": f"{market_id}_{idx}",
                "tokenId": token_id,
                "outcomeName": outcome_name,
                "currentPrice": 0.5,
                "volume": 0.0,
                "priceChange24h": 0.0,
            }
        )

    return outcomes


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

    Returns event with nested markets, each containing outcomes with:
    - Current prices from market_mark_daily
    - 24h price changes calculated from market_mark_daily
    - Volume per outcome

    Args:
        client: ClickHouse client.
        event_id: Event identifier (ID or slug).

    Returns:
        Event dict formatted for EventResponse with markets and outcomes,
        or None if not found.
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

    # Query associated markets with tokens JSON for fallback parsing
    markets_query = """
        SELECT
            m.platform_market_id AS id,
            m.platform_market_id AS polymarketId,
            m.canonical_market_id AS conditionId,
            m.market_slug AS slug,
            m.question,
            m.description,
            m.status,
            m.updated_at AS updatedAt,
            m.tokens
        FROM prediction_gold.dim_market m
        WHERE m.platform = 'polymarket'
            AND m.event_id = {event_id:String}
        ORDER BY m.updated_at DESC
    """
    market_rows = await execute_query(
        markets_query, {"event_id": event_id_resolved}, client=client
    )

    if not market_rows:
        return {
            "id": event_id_resolved,
            "polymarketEventId": row["polymarketEventId"],
            "title": row["title"] or "",
            "description": row.get("description"),
            "slug": row.get("slug") or "",
            "status": row.get("status") or "",
            "category": row.get("category"),
            "markets": [],
        }

    market_ids = [m["id"] for m in market_rows]

    # Query outcomes for all markets in this event
    outcomes_query = """
        SELECT
            o.market_id,
            o.outcome_id AS id,
            o.token_id AS tokenId,
            o.outcome_label AS outcomeName,
            o.side
        FROM prediction_gold.dim_outcome o
        WHERE o.platform = 'polymarket'
            AND o.market_id IN {market_ids:Array(String)}
    """
    outcome_rows = await execute_query(
        outcomes_query, {"market_ids": market_ids}, client=client
    )

    # Group outcomes by market_id
    outcomes_by_market: dict[str, list[dict[str, Any]]] = {}
    for outcome in outcome_rows:
        market_id = outcome["market_id"]
        if market_id not in outcomes_by_market:
            outcomes_by_market[market_id] = []
        outcomes_by_market[market_id].append(
            {
                "id": outcome["id"],
                "tokenId": outcome["tokenId"],
                "outcomeName": outcome["outcomeName"] or outcome["side"],
                "currentPrice": 0.5,  # Default, will be updated from market_mark_daily
                "volume": 0.0,
                "priceChange24h": 0.0,
            }
        )

    # Query market_mark_daily for current prices, volume, and price changes
    # Get the latest 2 days to calculate 24h price change
    marks_query = """
        SELECT
            m.market_id,
            m.outcome_id,
            m.day_utc,
            m.mark_price,
            m.volume_usd_24h
        FROM prediction_gold.market_mark_daily m
        WHERE m.market_id IN {market_ids:Array(String)}
            AND m.day_utc >= (
                SELECT MAX(day_utc) - INTERVAL 1 DAY
                FROM prediction_gold.market_mark_daily
                WHERE market_id IN {market_ids:Array(String)}
            )
        ORDER BY m.market_id, m.outcome_id, m.day_utc DESC
    """
    marks_rows = await execute_query(
        marks_query, {"market_ids": market_ids}, client=client
    )

    # Build price data lookup: market_id -> outcome_id -> {price, volume, prev_price}
    price_data: dict[str, dict[str, dict[str, float]]] = {}
    for mark in marks_rows:
        market_id = mark["market_id"]
        outcome_id = mark["outcome_id"]

        if market_id not in price_data:
            price_data[market_id] = {}
        if outcome_id not in price_data[market_id]:
            price_data[market_id][outcome_id] = {
                "price": 0.0,
                "volume": 0.0,
                "prev_price": 0.0,
            }

        # First row (most recent) sets the current price and volume
        if price_data[market_id][outcome_id]["price"] == 0.0:
            price_data[market_id][outcome_id]["price"] = float(
                mark.get("mark_price") or 0.5
            )
            price_data[market_id][outcome_id]["volume"] = float(
                mark.get("volume_usd_24h") or 0.0
            )
        else:
            # Second row sets the previous day price for change calculation
            price_data[market_id][outcome_id]["prev_price"] = float(
                mark.get("mark_price") or 0.0
            )

    # Calculate 24h volume per market (sum of all outcomes)
    volume_24h_by_market: dict[str, float] = {}
    for market_id, outcomes in price_data.items():
        volume_24h_by_market[market_id] = sum(
            data["volume"] for data in outcomes.values()
        )

    # Build markets list with enriched outcomes
    markets: list[dict[str, Any]] = []
    for market in market_rows:
        market_id = market["id"]

        # Format updated_at as ISO string
        updated_at = market.get("updatedAt")
        created_at_str = ""
        if updated_at:
            if hasattr(updated_at, "isoformat"):
                created_at_str = updated_at.isoformat()
            else:
                created_at_str = str(updated_at)

        # Get outcomes from dim_outcome, fallback to parsing tokens JSON
        market_outcomes = outcomes_by_market.get(market_id, [])
        if not market_outcomes and market.get("tokens"):
            market_outcomes = _parse_tokens_to_outcomes(market_id, market["tokens"])

        # Enrich outcomes with price data from market_mark_daily
        market_price_data = price_data.get(market_id, {})
        for outcome in market_outcomes:
            outcome_id = outcome["id"]
            if outcome_id in market_price_data:
                data = market_price_data[outcome_id]
                outcome["currentPrice"] = data["price"]
                outcome["volume"] = data["volume"]
                # Calculate absolute price change
                if data["prev_price"] > 0:
                    outcome["priceChange24h"] = data["price"] - data["prev_price"]
                else:
                    outcome["priceChange24h"] = 0.0

        markets.append(
            {
                "id": market_id,
                "polymarketId": market["polymarketId"],
                "conditionId": market.get("conditionId"),
                "slug": market.get("slug"),
                "question": market.get("question") or "",
                "description": market.get("description"),
                "category": row.get("category"),  # Use event category
                "endDate": None,  # Not in current schema
                "resolved": market.get("status") == "resolved",
                "totalVolume": 0.0,  # Would require historical aggregate
                "liquidity": 0.0,  # Would come from CLOB
                "createdAt": created_at_str,
                "imageUrl": None,  # Not in current schema
                "outcomes": market_outcomes,
                "volume24h": volume_24h_by_market.get(market_id, 0.0),
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
