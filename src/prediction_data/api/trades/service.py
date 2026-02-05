"""Trades service layer for ClickHouse queries.

This module provides service functions for global trade queries
including smart trades (from high-performing traders) and whale trades.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from prediction_data.api.clickhouse import execute_query

if TYPE_CHECKING:
    from clickhouse_connect.driver.client import Client


async def get_smart_trades(
    client: Client,
    *,
    min_score: float = 70.0,
    min_amount: float | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch recent trades from smart traders.

    Queries wallet_position_ledger for recent trades, filtered to traders
    with high smart scores. Since smart scores are not yet pre-computed,
    this currently uses total realized PnL as a proxy for "smartness".

    Args:
        client: ClickHouse client.
        min_score: Minimum smart score (0-100). Currently uses PnL-based proxy.
        min_amount: Minimum USD value of trade. If None, no minimum.
        limit: Maximum number of results (1-200).

    Returns:
        List of trade dicts formatted for SmartTradeResponse.
    """
    # Clamp limit
    actual_limit = min(max(limit, 1), 200)

    # Build amount filter
    amount_filter = ""
    if min_amount is not None:
        amount_filter = "AND ABS(l.qty_delta) * l.price >= {min_amount:Float64}"

    # Query recent trades from wallets with high PnL (proxy for smart score)
    # Join with aggregated PnL to filter for "smart" traders
    # Smart score is computed as: normalized PnL rank (0-100)
    query = f"""
        WITH smart_wallets AS (
            SELECT
                wallet,
                SUM(realized_pnl_usd) AS total_pnl,
                -- Compute a simple smart score based on PnL rank
                -- Top traders get higher scores
                100.0 * (1 - (ROW_NUMBER() OVER (ORDER BY SUM(realized_pnl_usd) DESC) - 1.0)
                    / NULLIF(COUNT(*) OVER (), 0)) AS smart_score
            FROM prediction_gold.wallet_pnl_daily
            GROUP BY wallet
            HAVING SUM(realized_pnl_usd) > 0
        )
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
            formatDateTime(l.ts, '%Y-%m-%dT%H:%i:%S.000Z') AS timestamp,
            sw.smart_score AS smartScore
        FROM prediction_gold.wallet_position_ledger l
        INNER JOIN smart_wallets sw ON l.wallet = sw.wallet
        LEFT JOIN prediction_gold.dim_market m
            ON l.market_id = m.platform_market_id
            AND l.platform = m.platform
        LEFT JOIN prediction_gold.dim_outcome o
            ON l.outcome_id = o.outcome_id
            AND l.platform = o.platform
        WHERE l.platform = 'polymarket'
            AND sw.smart_score >= {{min_score:Float64}}
            {amount_filter}
        ORDER BY l.ts DESC
        LIMIT {{limit:UInt64}}
    """

    params: dict[str, Any] = {"min_score": min_score, "limit": actual_limit}
    if min_amount is not None:
        params["min_amount"] = min_amount

    rows = await execute_query(query, params, client=client)

    # Convert rows to response format
    results: list[dict[str, Any]] = []
    for row in rows:
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
                "smartScore": float(row["smartScore"]),
            }
        )

    return results


async def get_whale_trades(
    client: Client,
    *,
    min_amount: float = 10000.0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch recent large trades (whale trades).

    Queries wallet_position_ledger for trades with USD value >= minAmount,
    ordered by timestamp descending.

    Args:
        client: ClickHouse client.
        min_amount: Minimum USD value of trade (default 10000).
        limit: Maximum number of results (1-200).

    Returns:
        List of trade dicts formatted for WhaleTradeResponse.
    """
    # Clamp limit
    actual_limit = min(max(limit, 1), 200)

    # Query recent large trades with wallet total value
    query = """
        WITH wallet_values AS (
            SELECT
                wallet,
                SUM(ABS(qty) * avg_cost) AS total_value
            FROM prediction_gold.wallet_position_state FINAL
            WHERE platform = 'polymarket'
            GROUP BY wallet
        )
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
            formatDateTime(l.ts, '%Y-%m-%dT%H:%i:%S.000Z') AS timestamp,
            COALESCE(wv.total_value, 0) AS totalWalletValue
        FROM prediction_gold.wallet_position_ledger l
        LEFT JOIN prediction_gold.dim_market m
            ON l.market_id = m.platform_market_id
            AND l.platform = m.platform
        LEFT JOIN prediction_gold.dim_outcome o
            ON l.outcome_id = o.outcome_id
            AND l.platform = o.platform
        LEFT JOIN wallet_values wv ON l.wallet = wv.wallet
        WHERE l.platform = 'polymarket'
            AND ABS(l.qty_delta) * l.price >= {min_amount:Float64}
        ORDER BY l.ts DESC
        LIMIT {limit:UInt64}
    """

    params: dict[str, Any] = {"min_amount": min_amount, "limit": actual_limit}
    rows = await execute_query(query, params, client=client)

    # Convert rows to response format
    results: list[dict[str, Any]] = []
    for row in rows:
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
                "totalWalletValue": float(row["totalWalletValue"]),
            }
        )

    return results
