"""Markets service layer for ClickHouse queries."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from prediction_data.api.clickhouse import (
    build_pagination,
    execute_query,
    execute_query_count,
)
from prediction_data.api.clob_client import ClobApiClient, OrderBookSummary

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
            e.slug AS eventSlug,
            m.question AS question,
            m.description AS description,
            e.category,
            m.status AS status,
            m.tokens AS tokens,
            m.updated_at AS updatedAt,
            e.image_url AS imageUrl
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

        # Get image URL from event, use empty string if not available
        image_url = row.get("imageUrl") or None

        results.append(
            {
                "id": market_id,
                "polymarketId": row["polymarketId"],
                "conditionId": row.get("conditionId"),
                "slug": row.get("slug"),
                "eventSlug": row.get("eventSlug"),
                "question": row["question"] or "",
                "description": row.get("description"),
                "category": row.get("category"),
                "endDate": None,  # Not in current schema
                "resolved": row.get("status") == "resolved",
                "totalVolume": 0.0,  # Would come from market_mark_daily aggregate
                "liquidity": 0.0,  # Would come from CLOB or market_mark_daily
                "createdAt": created_at_str,
                "imageUrl": image_url,
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
            e.slug AS eventSlug,
            m.question AS question,
            m.description AS description,
            e.category,
            m.status AS status,
            m.tokens AS tokens,
            m.updated_at AS updatedAt,
            e.image_url AS imageUrl
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

    # Get image URL from event
    image_url = row.get("imageUrl") or None

    return {
        "id": market_id_resolved,
        "polymarketId": row["polymarketId"],
        "conditionId": row.get("conditionId"),
        "slug": row.get("slug"),
        "eventSlug": row.get("eventSlug"),
        "question": row["question"] or "",
        "description": row.get("description"),
        "category": row.get("category"),
        "endDate": None,  # Not in current schema
        "resolved": row.get("status") == "resolved",
        "totalVolume": 0.0,  # Would come from market_mark_daily aggregate
        "liquidity": 0.0,  # Would come from CLOB or market_mark_daily
        "createdAt": created_at_str,
        "imageUrl": image_url,
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


async def get_market_price_history(
    client: Client,
    market_id: str,
    *,
    interval: str = "1d",
    start_date: str | None = None,
    end_date: str | None = None,
    outcome_id: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch price history for a market from ClickHouse.

    Queries the market_mark_daily table for historical price data.
    Results are returned in chronological order (oldest first) for chart rendering.

    Args:
        client: ClickHouse client.
        market_id: Market identifier (platform_market_id).
        interval: Time interval for aggregation (1h, 4h, 1d, 1w).
            Note: Currently only daily data is available, so 1h/4h return daily data.
        start_date: Start date filter (YYYY-MM-DD format).
        end_date: End date filter (YYYY-MM-DD format).
        outcome_id: Specific outcome ID to filter. If None, returns YES outcome or first.

    Returns:
        List of price history point dicts with timestamp, price, volume.
    """
    # Build WHERE conditions
    conditions: list[str] = ["m.market_id = {market_id:String}"]
    params: dict[str, Any] = {"market_id": market_id}

    if start_date:
        conditions.append("m.day_utc >= {start_date:Date}")
        params["start_date"] = start_date

    if end_date:
        conditions.append("m.day_utc <= {end_date:Date}")
        params["end_date"] = end_date

    if outcome_id:
        conditions.append("m.outcome_id = {outcome_id:String}")
        params["outcome_id"] = outcome_id

    where_clause = " AND ".join(conditions)

    # For interval 1w, aggregate by week; otherwise return daily data
    # Note: 1h and 4h intervals are not supported with current daily data
    if interval == "1w":
        # Aggregate by week (using toMonday for week start)
        query = f"""
            SELECT
                toMonday(m.day_utc) AS week_start,
                argMax(m.mark_price, m.day_utc) AS price,
                sum(m.volume_usd_24h) AS volume,
                m.outcome_id
            FROM prediction_gold.market_mark_daily m
            WHERE {where_clause}
            GROUP BY toMonday(m.day_utc), m.outcome_id
            ORDER BY week_start ASC
        """
    else:
        # Return daily data (handles 1d, 1h, 4h - hourly not available)
        query = f"""
            SELECT
                m.day_utc,
                m.mark_price AS price,
                m.volume_usd_24h AS volume,
                m.outcome_id
            FROM prediction_gold.market_mark_daily m
            WHERE {where_clause}
            ORDER BY m.day_utc ASC
        """

    rows = await execute_query(query, params, client=client)

    if not rows:
        return []

    # If no specific outcome_id was requested, filter to a single outcome
    # Prefer "Yes" outcome or just take the first one consistently
    if not outcome_id and rows:
        # Get unique outcome IDs
        outcome_ids = list({row["outcome_id"] for row in rows})
        if len(outcome_ids) > 1:
            # Try to find a YES outcome by looking it up in dim_outcome
            yes_query = """
                SELECT o.outcome_id
                FROM prediction_gold.dim_outcome o
                WHERE o.market_id = {market_id:String}
                    AND o.outcome_id IN {outcome_ids:Array(String)}
                    AND (o.side = 'Yes' OR o.outcome_label ILIKE '%yes%')
                LIMIT 1
            """
            yes_rows = await execute_query(
                yes_query,
                {"market_id": market_id, "outcome_ids": outcome_ids},
                client=client,
            )
            if yes_rows:
                selected_outcome = yes_rows[0]["outcome_id"]
            else:
                # Just pick the first outcome consistently
                selected_outcome = sorted(outcome_ids)[0]

            rows = [r for r in rows if r["outcome_id"] == selected_outcome]

    # Format results
    results: list[dict[str, Any]] = []
    for row in rows:
        # Format timestamp based on interval
        if interval == "1w":
            day_val = row.get("week_start")
        else:
            day_val = row.get("day_utc")

        if day_val:
            if hasattr(day_val, "isoformat"):
                ts_str = day_val.isoformat()
            else:
                ts_str = str(day_val)
        else:
            ts_str = ""

        price = row.get("price")
        volume = row.get("volume", 0.0)

        # Skip rows with no price data
        if price is None:
            continue

        results.append({
            "timestamp": ts_str,
            "price": float(price),
            "volume": float(volume) if volume else 0.0,
        })

    return results


async def get_markets_advanced(
    client: Client,
    clob_client: ClobApiClient,
    *,
    category: str | None = None,
    exclude_categories: list[str] | None = None,
    search: str | None = None,
    resolved: bool | None = None,
    active_only: bool = True,
    sort_by: str = "volume",
    sort_order: str = "desc",
    min_volume: float | None = None,
    max_volume: float | None = None,
    min_liquidity: float | None = None,
    max_liquidity: float | None = None,
    min_spread: float | None = None,
    max_spread: float | None = None,
    min_change: float | None = None,
    max_change: float | None = None,
    include_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch markets with CLOB bid/ask data from ClickHouse.

    Enriches market data with real-time order book information from
    the Polymarket CLOB API.

    Args:
        client: ClickHouse client.
        clob_client: CLOB API client for bid/ask data.
        category: Filter by category (exact match via event join).
        search: Search query for question/description (ILIKE).
        resolved: Filter by resolved status (True = "resolved", False = others).
        active_only: If True (default), only include markets with recent trading
            activity (within last 1-2 days). This filters out expired/resolved markets.
        sort_by: Sort field (volume, liquidity, spread, priceChange).
        sort_order: Sort direction (asc, desc).
        min_volume: Minimum 24h volume filter.
        max_volume: Maximum 24h volume filter.
        min_liquidity: Minimum liquidity filter.
        max_liquidity: Maximum liquidity filter.
        min_spread: Minimum spread filter (cents).
        max_spread: Maximum spread filter (cents).
        min_change: Minimum 24h price change filter.
        max_change: Maximum 24h price change filter.
        include_tags: Include only markets whose events have at least one of these tags.
        exclude_tags: Exclude markets whose events have any of these tags.
        limit: Maximum number of results.
        offset: Offset for pagination.

    Returns:
        Tuple of (list of market dicts formatted for MarketAdvancedResponse, total count).
    """
    # Build WHERE conditions for base query
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

    if exclude_categories:
        conditions.append("(e.category IS NULL OR e.category NOT IN {exclude_categories:Array(String)})")
        params["exclude_categories"] = exclude_categories

    # Tag filtering using ClickHouse array functions on dim_event.tags
    if include_tags:
        # Market must belong to an event that has at least one of the include tags
        conditions.append("hasAny(e.tags, {include_tags:Array(String)})")
        params["include_tags"] = include_tags

    if exclude_tags:
        # Market must NOT belong to an event that has any of the exclude tags
        # Using NOT hasAny() to exclude events with any matching tags
        conditions.append("NOT hasAny(e.tags, {exclude_tags:Array(String)})")
        params["exclude_tags"] = exclude_tags

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Build the recent activity subquery - used for both filtering and data
    # When active_only=True, filter to markets with activity in recent days
    # Uses MAX(day_utc) as reference to handle data lag/timezone issues
    # Note: dim_market may lag behind market_mark_daily, so we use a 4-day window
    # to ensure overlap between the two tables
    recent_activity_days = 4
    recent_activity_subquery = f"""
        SELECT
            market_id,
            sum(volume_usd_24h) AS volume_24h,
            0.0 AS price_change_24h
        FROM prediction_gold.market_mark_daily
        WHERE day_utc >= (SELECT MAX(day_utc) FROM prediction_gold.market_mark_daily) - {recent_activity_days}
        GROUP BY market_id
        HAVING sum(volume_usd_24h) > 0
    """

    # Get total count first (without advanced filters that need CLOB data)
    if active_only:
        count_query = f"""
            SELECT COUNT(DISTINCT m.platform_market_id)
            FROM prediction_gold.dim_market m
            LEFT JOIN prediction_gold.dim_event e
                ON m.platform = e.platform AND m.event_id = e.platform_event_id
            INNER JOIN ({recent_activity_subquery}) mark_recent
                ON mark_recent.market_id = m.platform_market_id
            WHERE {where_clause}
        """
    else:
        count_query = f"""
            SELECT COUNT(DISTINCT m.platform_market_id)
            FROM prediction_gold.dim_market m
            LEFT JOIN prediction_gold.dim_event e
                ON m.platform = e.platform AND m.event_id = e.platform_event_id
            WHERE {where_clause}
        """
    base_total = await execute_query_count(count_query, params, client=client)

    if base_total == 0:
        return [], 0

    # Fetch more markets than needed to allow for post-filtering on CLOB data
    # We may need to filter out some markets after enrichment
    fetch_limit = min(limit * 3, 500)  # Fetch up to 3x the limit, max 500

    # Get markets with volume data from market_mark_daily
    # When active_only=True, use INNER JOIN to only get markets with recent activity
    # Otherwise use LEFT JOIN to include all markets and sort by total volume
    if active_only:
        recent_join_type = "INNER JOIN"
        recent_volume_filter = f"WHERE day_utc >= (SELECT MAX(day_utc) FROM prediction_gold.market_mark_daily) - {recent_activity_days}"
        order_clause = "ORDER BY COALESCE(mark_recent.volume_24h, 0) DESC"
    else:
        recent_join_type = "LEFT JOIN"
        recent_volume_filter = ""  # No date filter - get all volume
        order_clause = "ORDER BY COALESCE(mark_total.total_volume, 0) DESC"

    markets_query = f"""
        SELECT
            m.platform_market_id AS id,
            m.platform_market_id AS polymarketId,
            m.canonical_market_id AS conditionId,
            m.market_slug AS slug,
            e.slug AS eventSlug,
            m.question AS question,
            m.description AS description,
            e.category,
            m.status AS status,
            m.tokens AS tokens,
            m.updated_at AS updatedAt,
            e.image_url AS imageUrl,
            mark_recent.volume_24h,
            mark_recent.price_change_24h,
            mark_total.total_volume
        FROM prediction_gold.dim_market m
        LEFT JOIN prediction_gold.dim_event e
            ON m.platform = e.platform AND m.event_id = e.platform_event_id
        {recent_join_type} (
            -- Recent volume: markets with activity in last N days (relative to latest data)
            SELECT
                market_id,
                sum(volume_usd_24h) AS volume_24h,
                0.0 AS price_change_24h
            FROM prediction_gold.market_mark_daily
            {recent_volume_filter}
            GROUP BY market_id
            HAVING sum(volume_usd_24h) > 0
        ) mark_recent ON mark_recent.market_id = m.platform_market_id
        LEFT JOIN (
            -- Total historical volume: sum across all available days
            SELECT
                market_id,
                sum(volume_usd_24h) AS total_volume
            FROM prediction_gold.market_mark_daily
            GROUP BY market_id
        ) mark_total ON mark_total.market_id = m.platform_market_id
        WHERE {where_clause}
        {order_clause}
        LIMIT {fetch_limit}
    """
    market_rows = await execute_query(markets_query, params, client=client)

    if not market_rows:
        return [], base_total

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
    token_ids_to_fetch: list[str] = []

    for outcome in outcome_rows:
        market_id = outcome["market_id"]
        if market_id not in outcomes_by_market:
            outcomes_by_market[market_id] = []

        token_id = outcome["tokenId"]
        if token_id:
            token_ids_to_fetch.append(token_id)

        outcomes_by_market[market_id].append(
            {
                "id": outcome["id"],
                "tokenId": token_id,
                "outcomeName": outcome["outcomeName"] or outcome["side"],
                "currentPrice": 0.5,  # Will be updated with CLOB data
                "volume": 0.0,
            }
        )

    # Fetch CLOB data for all token IDs
    clob_data: dict[str, OrderBookSummary] = {}
    if token_ids_to_fetch:
        clob_data = await clob_client.get_order_books(token_ids_to_fetch)

    # Build response dicts with CLOB enrichment
    results: list[dict[str, Any]] = []

    for row in market_rows:
        market_id = row["id"]

        # Parse tokens JSON if outcomes not in dim_outcome
        market_outcomes = outcomes_by_market.get(market_id, [])
        if not market_outcomes and row.get("tokens"):
            market_outcomes = _parse_tokens_to_outcomes(market_id, row["tokens"])
            # Collect token IDs from parsed outcomes for CLOB lookup
            for outcome in market_outcomes:
                token_id = outcome.get("tokenId")
                if token_id and token_id not in clob_data:
                    # Fetch individually if not in batch
                    summary = await clob_client.get_order_book(token_id)
                    if summary:
                        clob_data[token_id] = summary

        # Update outcomes with CLOB prices and aggregate CLOB data for the market
        best_bid: float | None = None
        best_ask: float | None = None
        spread: float | None = None
        spread_percent: float | None = None
        spread_cents: float | None = None

        for outcome in market_outcomes:
            token_id = outcome.get("tokenId")
            if token_id and token_id in clob_data:
                summary = clob_data[token_id]
                # Use midpoint as current price if both bid and ask exist
                if summary.bid is not None and summary.ask is not None:
                    outcome["currentPrice"] = (summary.bid + summary.ask) / 2

                    # Use the first outcome's CLOB data for the market-level fields
                    if best_bid is None:
                        best_bid = summary.bid
                        best_ask = summary.ask
                        spread = summary.spread
                        spread_percent = summary.spread_percent
                        spread_cents = summary.spread_cents
                elif summary.bid is not None:
                    outcome["currentPrice"] = summary.bid
                elif summary.ask is not None:
                    outcome["currentPrice"] = summary.ask

        # Get volume and price change from the query
        volume_24h = float(row.get("volume_24h") or 0.0)
        total_volume = float(row.get("total_volume") or 0.0)
        price_change_24h = float(row.get("price_change_24h") or 0.0)

        # Apply advanced filters
        if min_volume is not None and volume_24h < min_volume:
            continue
        if max_volume is not None and volume_24h > max_volume:
            continue
        if min_spread is not None and (spread_cents is None or spread_cents < min_spread):
            continue
        if max_spread is not None and (spread_cents is None or spread_cents > max_spread):
            continue
        if min_change is not None and price_change_24h < min_change:
            continue
        if max_change is not None and price_change_24h > max_change:
            continue

        # Estimate liquidity from CLOB data (rough approximation)
        liquidity = 0.0
        if best_bid is not None and best_ask is not None:
            # Use spread as a proxy for liquidity (tighter spread = more liquid)
            # This is a placeholder - real liquidity would come from order book depth
            liquidity = 1.0 / (spread_cents + 1) * 1000 if spread_cents else 0.0

        if min_liquidity is not None and liquidity < min_liquidity:
            continue
        if max_liquidity is not None and liquidity > max_liquidity:
            continue

        # Format updated_at as ISO string
        updated_at = row.get("updatedAt")
        created_at_str = ""
        if updated_at:
            if hasattr(updated_at, "isoformat"):
                created_at_str = updated_at.isoformat()
            else:
                created_at_str = str(updated_at)

        # Get image URL from event
        image_url = row.get("imageUrl") or None

        results.append(
            {
                "id": market_id,
                "polymarketId": row["polymarketId"],
                "conditionId": row.get("conditionId"),
                "slug": row.get("slug"),
                "eventSlug": row.get("eventSlug"),
                "question": row["question"] or "",
                "description": row.get("description"),
                "category": row.get("category"),
                "endDate": None,  # Not in current schema
                "resolved": row.get("status") == "resolved",
                "totalVolume": total_volume,  # Sum of all available daily volumes
                "liquidity": liquidity,
                "createdAt": created_at_str,
                "imageUrl": image_url,
                "outcomes": market_outcomes,
                # Advanced CLOB fields
                "bid": best_bid,
                "ask": best_ask,
                "spread": spread,
                "spreadPercent": spread_percent,
                "spreadCents": spread_cents,
                "volume24h": volume_24h,
                "priceChange24h": price_change_24h,
            }
        )

    # Sort results based on sort_by
    def sort_key(m: dict[str, Any]) -> Any:
        if sort_by == "volume":
            return m.get("totalVolume", 0.0) or 0.0
        elif sort_by == "liquidity":
            return m.get("liquidity", 0.0) or 0.0
        elif sort_by == "spread":
            return m.get("spreadCents", float("inf")) or float("inf")
        elif sort_by == "priceChange":
            return abs(m.get("priceChange24h", 0.0) or 0.0)
        return m.get("totalVolume", 0.0) or 0.0

    results.sort(key=sort_key, reverse=(sort_order == "desc"))

    # Apply pagination after filtering and sorting
    total_after_filter = len(results)
    results = results[offset : offset + limit]

    return results, total_after_filter


async def get_markets_screener(
    client: Client,
    *,
    time_window: str = "24h",
    category: str | None = None,
    search: str | None = None,
    resolved: bool | None = None,
    sort_by: str = "volume",
    sort_order: str = "desc",
    min_volume: float | None = None,
    max_volume: float | None = None,
    min_price_change: float | None = None,
    max_price_change: float | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch markets with time-based price and volume metrics from ClickHouse.

    This screener endpoint calculates price change and volume over a specific
    time window using historical market_mark_daily data.

    Args:
        client: ClickHouse client.
        time_window: Time window for calculations (6h, 12h, 24h, 7d).
            Note: Currently only daily data is available, so 6h and 12h
            behave like 24h until hourly data is computed.
        category: Filter by category (exact match via event join).
        search: Search query for question/description (ILIKE).
        resolved: Filter by resolved status (True = "resolved", False = others).
        sort_by: Sort field (volume, priceChange).
        sort_order: Sort direction (asc, desc).
        min_volume: Minimum volume filter for the time window.
        max_volume: Maximum volume filter for the time window.
        min_price_change: Minimum price change filter (e.g., -0.1 for -10%).
        max_price_change: Maximum price change filter (e.g., 0.1 for +10%).
        limit: Maximum number of results.
        offset: Offset for pagination.

    Returns:
        Tuple of (list of market dicts formatted for MarketAdvancedResponse, total count).
    """
    # Map time window to days for ClickHouse query
    # Note: Sub-daily windows use 1 day since only daily data is available
    days_back = {
        "6h": 1,
        "12h": 1,
        "24h": 1,
        "7d": 7,
    }.get(time_window, 1)

    # Build WHERE conditions for base query
    conditions: list[str] = []
    params: dict[str, Any] = {"days_back": days_back}

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

    # Get total count first (without price/volume filters)
    count_query = f"""
        SELECT COUNT(DISTINCT m.platform_market_id)
        FROM prediction_gold.dim_market m
        LEFT JOIN prediction_gold.dim_event e
            ON m.platform = e.platform AND m.event_id = e.platform_event_id
        WHERE {where_clause}
    """
    base_total = await execute_query_count(count_query, params, client=client)

    if base_total == 0:
        return [], 0

    # Fetch more markets than needed to allow for post-filtering
    fetch_limit = min(limit * 3, 500)

    # Get markets with aggregated price change and volume over the time window
    # Price change is calculated from the earliest mark price to the latest
    # Volume is summed over the period
    markets_query = f"""
        SELECT
            m.platform_market_id AS id,
            m.platform_market_id AS polymarketId,
            m.canonical_market_id AS conditionId,
            m.market_slug AS slug,
            e.slug AS eventSlug,
            m.question AS question,
            m.description AS description,
            e.category,
            m.status AS status,
            m.tokens AS tokens,
            m.updated_at AS updatedAt,
            e.image_url AS imageUrl,
            metrics.window_volume,
            metrics.price_change,
            metrics.latest_price,
            metrics.earliest_price
        FROM prediction_gold.dim_market m
        LEFT JOIN prediction_gold.dim_event e
            ON m.platform = e.platform AND m.event_id = e.platform_event_id
        LEFT JOIN (
            SELECT
                market_id,
                sum(volume_usd_24h) AS window_volume,
                -- Get latest price (most recent day in window)
                argMax(mark_price, day_utc) AS latest_price,
                -- Get earliest price (oldest day in window)
                argMin(mark_price, day_utc) AS earliest_price,
                -- Calculate price change as percentage
                CASE
                    WHEN argMin(mark_price, day_utc) > 0
                    THEN (argMax(mark_price, day_utc) - argMin(mark_price, day_utc))
                         / argMin(mark_price, day_utc)
                    ELSE 0
                END AS price_change
            FROM prediction_gold.market_mark_daily
            WHERE day_utc >= today() - {{days_back:UInt32}}
            GROUP BY market_id
        ) metrics ON metrics.market_id = m.platform_market_id
        WHERE {where_clause}
        ORDER BY COALESCE(metrics.window_volume, 0) DESC
        LIMIT {fetch_limit}
    """
    market_rows = await execute_query(markets_query, params, client=client)

    if not market_rows:
        return [], base_total

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
                "currentPrice": 0.5,  # Will be updated with latest price
                "volume": 0.0,
            }
        )

    # Build response dicts with screener metrics
    results: list[dict[str, Any]] = []

    for row in market_rows:
        market_id = row["id"]

        # Get volume and price change from the query
        window_volume = float(row.get("window_volume") or 0.0)
        price_change = float(row.get("price_change") or 0.0)
        latest_price = row.get("latest_price")

        # Apply volume filters
        if min_volume is not None and window_volume < min_volume:
            continue
        if max_volume is not None and window_volume > max_volume:
            continue

        # Apply price change filters
        if min_price_change is not None and price_change < min_price_change:
            continue
        if max_price_change is not None and price_change > max_price_change:
            continue

        # Parse tokens JSON if outcomes not in dim_outcome
        market_outcomes = outcomes_by_market.get(market_id, [])
        if not market_outcomes and row.get("tokens"):
            market_outcomes = _parse_tokens_to_outcomes(market_id, row["tokens"])

        # Update outcome prices with latest mark price if available
        if latest_price is not None:
            for outcome in market_outcomes:
                # Set YES outcome to latest_price, NO to 1-latest_price
                outcome_name = outcome.get("outcomeName", "").lower()
                if "yes" in outcome_name:
                    outcome["currentPrice"] = float(latest_price)
                elif "no" in outcome_name:
                    outcome["currentPrice"] = 1.0 - float(latest_price)
                else:
                    outcome["currentPrice"] = float(latest_price)

        # Format updated_at as ISO string
        updated_at = row.get("updatedAt")
        created_at_str = ""
        if updated_at:
            if hasattr(updated_at, "isoformat"):
                created_at_str = updated_at.isoformat()
            else:
                created_at_str = str(updated_at)

        # Get image URL from event
        image_url = row.get("imageUrl") or None

        results.append(
            {
                "id": market_id,
                "polymarketId": row["polymarketId"],
                "conditionId": row.get("conditionId"),
                "slug": row.get("slug"),
                "eventSlug": row.get("eventSlug"),
                "question": row["question"] or "",
                "description": row.get("description"),
                "category": row.get("category"),
                "endDate": None,  # Not in current schema
                "resolved": row.get("status") == "resolved",
                "totalVolume": window_volume,
                "liquidity": 0.0,  # Not computed for screener
                "createdAt": created_at_str,
                "imageUrl": image_url,
                "outcomes": market_outcomes,
                # Advanced fields (no CLOB data for screener)
                "bid": None,
                "ask": None,
                "spread": None,
                "spreadPercent": None,
                "spreadCents": None,
                "volume24h": window_volume,  # Use window volume
                "priceChange24h": price_change,  # Use window price change
            }
        )

    # Sort results based on sort_by
    def sort_key(m: dict[str, Any]) -> Any:
        if sort_by == "volume":
            return m.get("volume24h", 0.0) or 0.0
        elif sort_by == "priceChange":
            return abs(m.get("priceChange24h", 0.0) or 0.0)
        return m.get("volume24h", 0.0) or 0.0

    results.sort(key=sort_key, reverse=(sort_order == "desc"))

    # Apply pagination after filtering and sorting
    total_after_filter = len(results)
    results = results[offset : offset + limit]

    return results, total_after_filter


def _parse_tokens_to_outcomes(
    market_id: str, tokens_json: str | None
) -> list[dict[str, Any]]:
    """Parse tokens JSON string into outcome dicts.

    Handles two formats:
    - List of token ID strings: ["token_id_1", "token_id_2"]
    - List of token dicts: [{"token_id": "...", "outcome": "..."}]

    For binary markets (2 tokens), assigns "Yes"/"No" as default names.

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

    # Default outcome names for binary markets
    default_names = ["Yes", "No"] if len(tokens) == 2 else None

    outcomes: list[dict[str, Any]] = []
    for idx, token in enumerate(tokens):
        # Handle string token IDs (current format from clobTokenIds)
        if isinstance(token, str):
            token_id = token
            if default_names and idx < len(default_names):
                outcome_name = default_names[idx]
            else:
                outcome_name = f"Outcome {idx + 1}"
        # Handle dict format (legacy or future format)
        elif isinstance(token, dict):
            token_id = str(token.get("token_id", ""))
            outcome_name = str(token.get("outcome", f"Outcome {idx + 1}"))
        else:
            continue

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


async def get_tags(
    client: Client,
) -> list[dict[str, Any]]:
    """Fetch available tags (categories) from ClickHouse.

    Returns a list of categories with their market counts, ordered by market count
    descending. Categories are extracted from dim_event and joined with dim_market
    to count actual markets per category.

    Args:
        client: ClickHouse client.

    Returns:
        List of tag dicts formatted for TagResponse (id, name, slug, marketCount).
    """
    # Query categories from dim_event joined with dim_market to get actual market counts
    # This gives us categories that have associated markets
    query = """
        SELECT
            e.category AS name,
            COUNT(DISTINCT m.platform_market_id) AS market_count
        FROM prediction_gold.dim_event e
        INNER JOIN prediction_gold.dim_market m
            ON m.platform = e.platform AND m.event_id = e.platform_event_id
        WHERE e.category IS NOT NULL AND e.category != ''
        GROUP BY e.category
        ORDER BY market_count DESC
    """

    rows = await execute_query(query, {}, client=client)

    # Convert to TagResponse format
    # Generate slug from category name (lowercase, hyphens for spaces)
    results: list[dict[str, Any]] = []
    for row in rows:
        name = row.get("name") or ""
        if not name:
            continue
        # Generate slug: lowercase, replace spaces with hyphens, remove special chars
        slug = name.lower().replace(" ", "-").replace("&", "and")
        # Remove any remaining non-alphanumeric characters except hyphens
        slug = "".join(c for c in slug if c.isalnum() or c == "-")

        results.append(
            {
                "id": slug,  # Use slug as ID since we don't have a separate ID
                "name": name,
                "slug": slug,
                "marketCount": int(row.get("market_count", 0)),
            }
        )

    return results
