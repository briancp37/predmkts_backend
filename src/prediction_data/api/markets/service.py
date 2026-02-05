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


async def get_market_by_id(
    client: Client,
    market_id: str,
) -> dict[str, Any] | None:
    """Fetch a single market by ID from ClickHouse.

    The market_id can be:
    - Internal ID (platform_market_id)
    - Polymarket ID (same as platform_market_id for Polymarket)
    - Market slug

    Args:
        client: ClickHouse client.
        market_id: Market identifier (ID, polymarketId, or slug).

    Returns:
        Market dict formatted for MarketResponse, or None if not found.
    """
    # Query market with flexible ID matching (ID or slug)
    market_query = """
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
        WHERE m.platform_market_id = {market_id:String}
           OR m.market_slug = {market_id:String}
        LIMIT 1
    """
    market_rows = await execute_query(
        market_query, {"market_id": market_id}, client=client
    )

    if not market_rows:
        return None

    row = market_rows[0]
    market_id_resolved = row["id"]

    # Query outcomes for this market
    outcomes_query = """
        SELECT
            o.outcome_id AS id,
            o.token_id AS tokenId,
            o.outcome_label AS outcomeName,
            o.side
        FROM prediction_gold.dim_outcome o
        WHERE o.platform = 'polymarket'
            AND o.market_id = {market_id:String}
    """
    outcome_rows = await execute_query(
        outcomes_query, {"market_id": market_id_resolved}, client=client
    )

    # Build outcomes list
    market_outcomes: list[dict[str, Any]] = []
    for outcome in outcome_rows:
        market_outcomes.append(
            {
                "id": outcome["id"],
                "tokenId": outcome["tokenId"],
                "outcomeName": outcome["outcomeName"] or outcome["side"],
                "currentPrice": 0.5,  # Default price, real-time comes from CLOB
                "volume": 0.0,  # Volume comes from market_mark_daily
            }
        )

    # Fall back to parsing tokens JSON if no outcomes found in dim_outcome
    if not market_outcomes and row.get("tokens"):
        market_outcomes = _parse_tokens_to_outcomes(market_id_resolved, row["tokens"])

    # Format updated_at as ISO string
    updated_at = row.get("updatedAt")
    created_at_str = ""
    if updated_at:
        if hasattr(updated_at, "isoformat"):
            created_at_str = updated_at.isoformat()
        else:
            created_at_str = str(updated_at)

    return {
        "id": market_id_resolved,
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


async def get_market_trades(
    client: Client,
    market_id: str,
    *,
    limit: int = 100,
    offset: int = 0,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch trades for a market from ClickHouse.

    Queries the wallet_position_ledger table for all trades associated with
    a given market. Trades are returned in reverse chronological order
    (most recent first).

    Args:
        client: ClickHouse client.
        market_id: Market identifier (platform_market_id).
        limit: Maximum number of results (default 100, max 1000).
        offset: Offset for pagination.
        start_date: Filter trades after this date (YYYY-MM-DD format).
        end_date: Filter trades before this date (YYYY-MM-DD format).

    Returns:
        Tuple of (list of trade dicts formatted for TradeResponse, total count).
    """
    # Build WHERE conditions
    conditions: list[str] = ["l.market_id = {market_id:String}"]
    params: dict[str, Any] = {"market_id": market_id}

    if start_date:
        conditions.append("l.ts >= {start_date:DateTime64(6, 'UTC')}")
        params["start_date"] = start_date

    if end_date:
        conditions.append("l.ts <= {end_date:DateTime64(6, 'UTC')}")
        params["end_date"] = end_date

    where_clause = " AND ".join(conditions)

    # Build pagination with max limit clamping
    pagination_clause, pagination_params = build_pagination(
        limit=limit, offset=offset, max_limit=1000
    )
    params.update(pagination_params)

    # Get total count first
    count_query = f"""
        SELECT COUNT(*)
        FROM prediction_gold.wallet_position_ledger l
        WHERE {where_clause}
    """
    total = await execute_query_count(count_query, params, client=client)

    if total == 0:
        return [], 0

    # Get trades with outcome name from dim_outcome
    trades_query = f"""
        SELECT
            l.ts,
            l.wallet,
            l.market_id,
            l.outcome_id,
            l.side,
            l.qty_delta,
            l.price,
            l.fees_usd,
            o.outcome_label,
            o.side AS outcome_side
        FROM prediction_gold.wallet_position_ledger l
        LEFT JOIN prediction_gold.dim_outcome o
            ON o.platform = l.platform
            AND o.market_id = l.market_id
            AND o.outcome_id = l.outcome_id
        WHERE {where_clause}
        ORDER BY l.ts DESC
        {pagination_clause}
    """
    trade_rows = await execute_query(trades_query, params, client=client)

    if not trade_rows:
        return [], total

    # Format trades for TradeResponse
    results: list[dict[str, Any]] = []
    for idx, row in enumerate(trade_rows):
        # Generate a synthetic ID from timestamp + wallet + market + outcome
        ts = row.get("ts")
        ts_str = ""
        if ts:
            if hasattr(ts, "isoformat"):
                ts_str = ts.isoformat()
            else:
                ts_str = str(ts)

        # Generate unique ID for the trade
        trade_id = f"{row['market_id']}_{row['wallet']}_{ts_str}_{idx + offset}"

        # Determine outcome name from outcome_label or fallback to side
        outcome_name = row.get("outcome_label") or row.get("outcome_side") or "Unknown"

        # Map side to BUY/SELL
        side_raw = str(row.get("side", "")).upper()
        side = "BUY" if side_raw in ("BUY", "LONG") else "SELL"

        # Calculate USD value (qty * price)
        qty = float(row.get("qty_delta", 0))
        price = float(row.get("price", 0))
        usd_value = abs(qty * price)

        results.append(
            {
                "id": trade_id,
                "traderAddress": row.get("wallet", ""),
                "marketId": row.get("market_id", ""),
                "outcomeId": row.get("outcome_id", ""),
                "outcomeName": outcome_name,
                "side": side,
                "price": price,
                "amount": abs(qty),
                "usdValue": usd_value,
                "txHash": None,  # Not available in wallet_position_ledger
                "timestamp": ts_str,
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
