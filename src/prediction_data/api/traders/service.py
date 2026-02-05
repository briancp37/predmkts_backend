"""Traders service layer for ClickHouse queries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from prediction_data.api.clickhouse import (
    build_pagination,
    execute_query,
    execute_query_count,
)

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
