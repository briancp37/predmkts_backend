"""Markets service layer for ClickHouse queries."""

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


async def get_markets(
    client: Client,
    *,
    category: str | None = None,
    search: str | None = None,
    resolved: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch markets from ClickHouse with filtering.

    Args:
        client: ClickHouse client.
        category: Filter by category (exact match via event join).
        search: Search query for question/description (ILIKE).
        resolved: Filter by resolved status (True = "resolved", False = others).
        limit: Maximum number of results.
        offset: Offset for pagination.

    Returns:
        Tuple of (list of market dicts formatted for MarketResponse, total count).
    """
    # Build WHERE conditions
    conditions: list[str] = []
    params: dict[str, Any] = {}

    if search:
        conditions.append(
            "(m.question ILIKE {search:String} OR m.description ILIKE {search:String})"
        )
        params["search"] = f"%{search}%"

    if resolved is not None:
        if resolved:
            conditions.append("m.status = 'resolved'")
        else:
            conditions.append("m.status != 'resolved'")

    if category:
        conditions.append("e.category = {category:String}")
        params["category"] = category

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Build pagination
    pagination_clause, pagination_params = build_pagination(
        limit=limit, offset=offset, max_limit=500
    )
    params.update(pagination_params)

    # Get total count first
    count_query = f"""
        SELECT COUNT(DISTINCT m.platform_market_id)
        FROM prediction_gold.dim_market m
        LEFT JOIN prediction_gold.dim_event e
            ON m.platform = e.platform AND m.event_id = e.platform_event_id
        WHERE {where_clause}
    """
    total = await execute_query_count(count_query, params, client=client)

    # Get markets with outcomes aggregated
    # Order by market_slug as a proxy for activity (markets with slugs are typically more active)
    # In future, this should order by volume from market_mark_daily
    markets_query = f"""
        SELECT
            m.platform_market_id AS id,
            m.platform_market_id AS polymarketId,
            m.canonical_market_id AS conditionId,
            m.market_slug AS slug,
            m.question,
            m.description,
            e.category,
            m.status,
            m.tokens,
            m.updated_at AS updatedAt
        FROM prediction_gold.dim_market m
        LEFT JOIN prediction_gold.dim_event e
            ON m.platform = e.platform AND m.event_id = e.platform_event_id
        WHERE {where_clause}
        ORDER BY m.updated_at DESC
        {pagination_clause}
    """
    market_rows = await execute_query(markets_query, params, client=client)

    if not market_rows:
        return [], total

    # Get market IDs for outcome lookup
    market_ids = [row["id"] for row in market_rows]

    # Query outcomes for these markets
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
                "currentPrice": 0.5,  # Default price, real-time comes from CLOB
                "volume": 0.0,  # Volume comes from market_mark_daily
            }
        )

    # Build response dicts
    results: list[dict[str, Any]] = []
    for row in market_rows:
        market_id = row["id"]

        # Parse tokens JSON if outcomes not in dim_outcome
        market_outcomes = outcomes_by_market.get(market_id, [])
        if not market_outcomes and row.get("tokens"):
            market_outcomes = _parse_tokens_to_outcomes(market_id, row["tokens"])

        # Format updated_at as ISO string
        updated_at = row.get("updatedAt")
        created_at_str = ""
        if updated_at:
            if hasattr(updated_at, "isoformat"):
                created_at_str = updated_at.isoformat()
            else:
                created_at_str = str(updated_at)

        results.append(
            {
                "id": market_id,
                "polymarketId": row["polymarketId"],
                "conditionId": row.get("conditionId"),
                "slug": row.get("slug"),
                "question": row["question"] or "",
                "description": row.get("description"),
                "category": row.get("category"),
                "endDate": None,  # Not in current schema
                "resolved": row.get("status") == "resolved",
                "totalVolume": 0.0,  # Would come from market_mark_daily aggregate
                "liquidity": 0.0,  # Would come from CLOB or market_mark_daily
                "createdAt": created_at_str,
                "imageUrl": None,  # Not in current schema
                "outcomes": market_outcomes,
            }
        )

    return results, total


def _parse_tokens_to_outcomes(
    market_id: str, tokens_json: str | None
) -> list[dict[str, Any]]:
    """Parse tokens JSON string into outcome dicts.

    Args:
        market_id: The market ID for generating outcome IDs.
        tokens_json: JSON string of tokens array.

    Returns:
        List of outcome dicts with id, tokenId, outcomeName, currentPrice, volume.
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
            }
        )

    return outcomes
