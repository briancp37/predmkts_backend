"""Traders service layer for ClickHouse queries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from prediction_data.api.clickhouse import (
    build_pagination,
    execute_query,
    execute_query_count,
)
from prediction_data.api.traders.schemas import TraderPosition

if TYPE_CHECKING:
    from clickhouse_connect.driver.client import Client

# Mapping from API sort field names to ClickHouse column expressions
SORT_FIELD_MAPPING = {
    "totalPnl": "total_pnl",
    "totalTrades": "total_trades",
    "winRate": "win_rate",
    "smartScore": "total_pnl",  # Smart score not yet computed, use totalPnl as proxy
}


async def get_traders(
    client: Client,
    *,
    search: str | None = None,
    sort_by: str = "totalPnl",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch traders from ClickHouse with filtering.

    Joins dim_wallet with wallet_pnl_daily to get aggregated PnL and trade counts.
    Win rate is calculated from wins / (wins + losses).

    Args:
        client: ClickHouse client.
        search: Search query for wallet address (ILIKE prefix match).
        sort_by: Field to sort by (totalPnl, totalTrades, winRate, smartScore).
        sort_order: Sort direction ('asc' or 'desc').
        limit: Maximum number of results.
        offset: Offset for pagination.

    Returns:
        Tuple of (list of trader dicts formatted for TraderResponse, total count).
    """
    # Build WHERE conditions
    conditions: list[str] = []
    params: dict[str, Any] = {}

    if search:
        # Search by wallet address prefix (ILIKE)
        conditions.append("w.wallet_address ILIKE {search:String}")
        params["search"] = f"{search}%"

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Validate sort field and direction
    sort_column = SORT_FIELD_MAPPING.get(sort_by, "total_pnl")
    direction = "DESC" if sort_order.lower() == "desc" else "ASC"

    # Build pagination
    pagination_clause, pagination_params = build_pagination(
        limit=limit, offset=offset, max_limit=500
    )
    params.update(pagination_params)

    # Get total count of traders matching filters
    count_query = f"""
        SELECT COUNT(DISTINCT w.wallet_address)
        FROM prediction_gold.dim_wallet w
        WHERE w.platform = 'polymarket'
            AND {where_clause}
    """
    total = await execute_query_count(count_query, params, client=client)

    # Main query: Join dim_wallet with aggregated wallet_pnl_daily
    # Aggregate PnL data across all days for each wallet
    traders_query = f"""
        SELECT
            w.wallet_address AS address,
            NULL AS username,
            formatDateTime(w.first_trade_ts, '%Y-%m-%dT%H:%i:%S.000Z') AS firstSeen,
            COALESCE(pnl.total_pnl, 0) AS total_pnl,
            COALESCE(pnl.realized_pnl, 0) AS realized_pnl,
            COALESCE(pnl.total_trades, 0) AS total_trades,
            COALESCE(pnl.wins, 0) AS wins,
            COALESCE(pnl.losses, 0) AS losses,
            CASE
                WHEN COALESCE(pnl.wins, 0) + COALESCE(pnl.losses, 0) > 0
                THEN COALESCE(pnl.wins, 0) * 100.0 / (COALESCE(pnl.wins, 0) + COALESCE(pnl.losses, 0))
                ELSE 0
            END AS win_rate,
            w.wallet_address AS id,
            NULL AS smartScore,
            formatDateTime(w.first_trade_ts, '%Y-%m-%dT%H:%i:%S.000Z') AS createdAt,
            formatDateTime(w.last_trade_ts, '%Y-%m-%dT%H:%i:%S.000Z') AS updatedAt
        FROM prediction_gold.dim_wallet w
        LEFT JOIN (
            SELECT
                wallet,
                SUM(realized_pnl_usd) AS total_pnl,
                SUM(realized_pnl_usd) AS realized_pnl,
                SUM(trades_count) AS total_trades,
                SUM(wins) AS wins,
                SUM(losses) AS losses
            FROM prediction_gold.wallet_pnl_daily
            GROUP BY wallet
        ) pnl ON w.wallet_address = pnl.wallet
        WHERE w.platform = 'polymarket'
            AND {where_clause}
        ORDER BY {sort_column} {direction}
        {pagination_clause}
    """
    trader_rows = await execute_query(traders_query, params, client=client)

    # Convert rows to response format
    results: list[dict[str, Any]] = []
    for row in trader_rows:
        results.append(
            {
                "id": row["id"],
                "address": row["address"],
                "username": row["username"],
                "firstSeen": row["firstSeen"],
                "totalPnl": float(row["total_pnl"]),
                "realizedPnl": float(row["realized_pnl"]),
                "totalTrades": int(row["total_trades"]),
                "winCount": int(row["wins"]),
                "lossCount": int(row["losses"]),
                "smartScore": row["smartScore"],
                "createdAt": row["createdAt"],
                "updatedAt": row["updatedAt"],
            }
        )

    return results, total


async def get_trader_by_address(
    client: Client,
    address: str,
) -> dict[str, Any] | None:
    """Fetch a single trader by wallet address from ClickHouse.

    Joins dim_wallet with wallet_pnl_daily for PnL aggregates, queries
    wallet_position_state for current positions, and joins with dim_market
    and dim_outcome for position details.

    Args:
        client: ClickHouse client.
        address: Wallet address (will be normalized to lowercase).

    Returns:
        Trader dict formatted for TraderDetailResponse, or None if not found.
    """
    # Normalize address to lowercase
    address = address.lower()

    # Query trader metadata with aggregated PnL
    trader_query = """
        SELECT
            w.wallet_address AS address,
            NULL AS username,
            formatDateTime(w.first_trade_ts, '%Y-%m-%dT%H:%i:%S.000Z') AS firstSeen,
            COALESCE(pnl.total_pnl, 0) AS total_pnl,
            COALESCE(pnl.realized_pnl, 0) AS realized_pnl,
            COALESCE(pnl.total_trades, 0) AS total_trades,
            COALESCE(pnl.wins, 0) AS wins,
            COALESCE(pnl.losses, 0) AS losses,
            w.wallet_address AS id,
            NULL AS smartScore,
            formatDateTime(w.first_trade_ts, '%Y-%m-%dT%H:%i:%S.000Z') AS createdAt,
            formatDateTime(w.last_trade_ts, '%Y-%m-%dT%H:%i:%S.000Z') AS updatedAt
        FROM prediction_gold.dim_wallet w
        LEFT JOIN (
            SELECT
                wallet,
                SUM(realized_pnl_usd) AS total_pnl,
                SUM(realized_pnl_usd) AS realized_pnl,
                SUM(trades_count) AS total_trades,
                SUM(wins) AS wins,
                SUM(losses) AS losses
            FROM prediction_gold.wallet_pnl_daily
            GROUP BY wallet
        ) pnl ON w.wallet_address = pnl.wallet
        WHERE w.platform = 'polymarket'
            AND w.wallet_address = {address:String}
        LIMIT 1
    """
    trader_rows = await execute_query(trader_query, {"address": address}, client=client)

    if not trader_rows:
        return None

    trader = trader_rows[0]

    # Query current open positions from wallet_position_state
    # Join with dim_market for market details and dim_outcome for outcome names
    positions_query = """
        SELECT
            ps.market_id AS marketId,
            COALESCE(m.question, '') AS marketQuestion,
            ps.outcome_id AS outcomeId,
            COALESCE(o.outcome_label, o.side, '') AS outcomeName,
            ps.qty AS quantity,
            ps.avg_cost AS avgCost,
            COALESCE(mark.last_price, 0.5) AS currentPrice,
            ps.qty * (COALESCE(mark.last_price, 0.5) - ps.avg_cost) AS unrealizedPnl,
            0 AS realizedPnl
        FROM prediction_gold.wallet_position_state FINAL ps
        LEFT JOIN prediction_gold.dim_market m
            ON ps.market_id = m.platform_market_id
            AND ps.platform = m.platform
        LEFT JOIN prediction_gold.dim_outcome o
            ON ps.outcome_id = o.outcome_id
            AND ps.platform = o.platform
        LEFT JOIN (
            SELECT
                market_id,
                outcome_id,
                last_price
            FROM prediction_gold.market_mark_daily
            WHERE day = (SELECT MAX(day) FROM prediction_gold.market_mark_daily)
        ) mark ON ps.market_id = mark.market_id AND ps.outcome_id = mark.outcome_id
        WHERE ps.wallet = {address:String}
            AND ps.platform = 'polymarket'
            AND ps.qty != 0
        ORDER BY ABS(ps.qty * ps.avg_cost) DESC
    """
    position_rows = await execute_query(
        positions_query, {"address": address}, client=client
    )

    # Convert position rows to TraderPosition objects
    positions: list[TraderPosition] = []
    for row in position_rows:
        positions.append(
            TraderPosition(
                marketId=row["marketId"],
                marketQuestion=row["marketQuestion"],
                outcomeId=row["outcomeId"],
                outcomeName=row["outcomeName"],
                quantity=float(row["quantity"]),
                avgCost=float(row["avgCost"]),
                currentPrice=float(row["currentPrice"]),
                unrealizedPnl=float(row["unrealizedPnl"]),
                realizedPnl=float(row["realizedPnl"]),
            )
        )

    # Calculate win rate
    wins = int(trader["wins"])
    losses = int(trader["losses"])
    total_closed = wins + losses
    win_rate = (wins * 100.0 / total_closed) if total_closed > 0 else 0.0

    return {
        "id": trader["id"],
        "address": trader["address"],
        "username": trader["username"],
        "firstSeen": trader["firstSeen"],
        "totalPnl": float(trader["total_pnl"]),
        "realizedPnl": float(trader["realized_pnl"]),
        "totalTrades": int(trader["total_trades"]),
        "winCount": wins,
        "lossCount": losses,
        "smartScore": trader["smartScore"],
        "createdAt": trader["createdAt"],
        "updatedAt": trader["updatedAt"],
        "positions": [p.model_dump() for p in positions],
        "tradeCount": int(trader["total_trades"]),
        "winRate": win_rate,
    }


async def get_leaderboard(
    client: Client,
    *,
    period: str = "7d",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Fetch PnL leaderboard from ClickHouse.

    Aggregates wallet_pnl_daily by the specified time period and returns
    ranked traders by realized PnL.

    Args:
        client: ClickHouse client.
        period: Time period for aggregation ('1d', '7d', '30d', 'all').
        limit: Maximum number of results (1-500).

    Returns:
        List of leaderboard entry dicts formatted for LeaderboardResponse.
    """
    # Build date filter based on period
    if period == "1d":
        date_filter = "day = today()"
    elif period == "7d":
        date_filter = "day >= today() - 7"
    elif period == "30d":
        date_filter = "day >= today() - 30"
    else:  # 'all'
        date_filter = "1=1"

    # Clamp limit
    actual_limit = min(max(limit, 1), 500)

    # Query aggregated PnL by wallet for the period
    leaderboard_query = f"""
        SELECT
            wallet AS traderAddress,
            SUM(realized_pnl_usd) AS pnl,
            SUM(trades_count) AS tradeCount,
            SUM(wins) AS wins,
            SUM(losses) AS losses
        FROM prediction_gold.wallet_pnl_daily
        WHERE {date_filter}
        GROUP BY wallet
        HAVING pnl != 0
        ORDER BY pnl DESC
        LIMIT {{limit:UInt64}}
    """

    rows = await execute_query(leaderboard_query, {"limit": actual_limit}, client=client)

    # Convert rows to response format with ranks
    results: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        wins = int(row["wins"])
        losses = int(row["losses"])
        total_closed = wins + losses
        win_rate = (wins * 100.0 / total_closed) if total_closed > 0 else 0.0

        results.append(
            {
                "rank": idx,
                "traderAddress": row["traderAddress"],
                "pnl": float(row["pnl"]),
                "tradeCount": int(row["tradeCount"]),
                "winRate": win_rate,
            }
        )

    return results


async def get_trader_trades(
    client: Client,
    address: str,
    *,
    limit: int = 100,
    offset: int = 0,
    start_date: str | None = None,
    end_date: str | None = None,
    market_id: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch trades for a specific trader from ClickHouse.

    Queries wallet_position_ledger for the trader's transactions,
    joined with dim_market and dim_outcome for readable names.

    Args:
        client: ClickHouse client.
        address: Wallet address (will be normalized to lowercase).
        limit: Maximum number of results (1-1000).
        offset: Offset for pagination.
        start_date: Filter trades on or after this date (YYYY-MM-DD).
        end_date: Filter trades on or before this date (YYYY-MM-DD).
        market_id: Filter to a specific market.

    Returns:
        Tuple of (list of trade dicts formatted for TradeResponse, total count).
    """
    # Normalize address to lowercase
    address = address.lower()

    # Build WHERE conditions
    conditions: list[str] = ["l.wallet = {address:String}", "l.platform = 'polymarket'"]
    params: dict[str, Any] = {"address": address}

    if start_date:
        conditions.append("l.ts >= toDateTime({start_date:String})")
        params["start_date"] = f"{start_date} 00:00:00"

    if end_date:
        conditions.append("l.ts <= toDateTime({end_date:String})")
        params["end_date"] = f"{end_date} 23:59:59"

    if market_id:
        conditions.append("l.market_id = {market_id:String}")
        params["market_id"] = market_id

    where_clause = " AND ".join(conditions)

    # Build pagination
    pagination_clause, pagination_params = build_pagination(
        limit=limit, offset=offset, max_limit=1000
    )
    params.update(pagination_params)

    # Get total count of trades matching filters
    count_query = f"""
        SELECT COUNT(*)
        FROM prediction_gold.wallet_position_ledger l
        WHERE {where_clause}
    """
    total = await execute_query_count(count_query, params, client=client)

    # Main query: Join wallet_position_ledger with dim_market and dim_outcome
    trades_query = f"""
        SELECT
            concat(l.wallet, '-', toString(l.ts), '-', l.market_id, '-', l.outcome_id) AS id,
            l.wallet AS traderAddress,
            l.market_id AS marketId,
            COALESCE(m.question, '') AS marketQuestion,
            l.outcome_id AS outcomeId,
            COALESCE(o.outcome_label, o.side, '') AS outcomeName,
            CASE WHEN l.qty_delta > 0 THEN 'BUY' ELSE 'SELL' END AS side,
            l.price AS price,
            ABS(l.qty_delta) AS quantity,
            ABS(l.qty_delta) * l.price AS usdValue,
            l.fees_usd AS fees,
            l.realized_pnl_this_fill_usd AS realizedPnl,
            formatDateTime(l.ts, '%Y-%m-%dT%H:%i:%S.000Z') AS timestamp
        FROM prediction_gold.wallet_position_ledger l
        LEFT JOIN prediction_gold.dim_market m
            ON l.market_id = m.platform_market_id
            AND l.platform = m.platform
        LEFT JOIN prediction_gold.dim_outcome o
            ON l.outcome_id = o.outcome_id
            AND l.platform = o.platform
        WHERE {where_clause}
        ORDER BY l.ts DESC
        {pagination_clause}
    """
    trade_rows = await execute_query(trades_query, params, client=client)

    # Convert rows to response format
    results: list[dict[str, Any]] = []
    for row in trade_rows:
        # Only include realizedPnl if there was a realized profit/loss (closing trade)
        realized_pnl = float(row["realizedPnl"]) if row["realizedPnl"] != 0 else None
        results.append(
            {
                "id": row["id"],
                "traderAddress": row["traderAddress"],
                "marketId": row["marketId"],
                "marketQuestion": row["marketQuestion"],
                "outcomeId": row["outcomeId"],
                "outcomeName": row["outcomeName"],
                "side": row["side"],
                "price": float(row["price"]),
                "quantity": float(row["quantity"]),
                "usdValue": float(row["usdValue"]),
                "fees": float(row["fees"]),
                "realizedPnl": realized_pnl,
                "timestamp": row["timestamp"],
            }
        )

    return results, total
