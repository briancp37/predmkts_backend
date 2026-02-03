"""Compute daily per-position snapshots for watchlist wallets.

For each active watchlist wallet and each open position, creates a daily
snapshot row with mark-to-market values. Unlike wallet_mtm_daily which
aggregates to wallet level, this table preserves per-position detail.

Produces one row per (day_utc, wallet, platform, market_id, outcome_id) with:
- qty: current position size
- avg_cost: average cost basis
- mark_price: mark price for the day
- position_value_usd: qty * mark_price
- unrealized_pnl_usd: qty * (mark_price - avg_cost)
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pyarrow as pa
import structlog

logger = structlog.stdlib.get_logger(__name__)

WALLET_POSITION_SNAPSHOT_DAILY_SCHEMA = pa.schema(
    [
        pa.field("day_utc", pa.date32()),
        pa.field("wallet", pa.string()),
        pa.field("platform", pa.string()),
        pa.field("market_id", pa.string()),
        pa.field("outcome_id", pa.string()),
        pa.field("qty", pa.float64()),
        pa.field("avg_cost", pa.float64()),
        pa.field("mark_price", pa.float64()),
        pa.field("position_value_usd", pa.float64()),
        pa.field("unrealized_pnl_usd", pa.float64()),
    ]
)

WALLET_POSITION_SNAPSHOT_DAILY_COLUMNS = [
    f.name for f in WALLET_POSITION_SNAPSHOT_DAILY_SCHEMA
]


def _read_watchlist_wallets(
    clickhouse_client: Any | None = None,
) -> list[str]:
    """Return list of active watchlist wallet addresses."""
    if clickhouse_client is None:
        from prediction_data.gold.clickhouse import get_client

        clickhouse_client = get_client()

    result = clickhouse_client.query(
        "SELECT wallet_address FROM gold_watchlist FINAL WHERE active = true"
    )
    return [row[0] for row in result.result_rows]


def _read_positions_for_wallets(
    wallets: list[str],
    clickhouse_client: Any | None = None,
) -> list[dict[str, Any]]:
    """Read open positions from wallet_position_state for given wallets."""
    if not wallets:
        return []

    if clickhouse_client is None:
        from prediction_data.gold.clickhouse import get_client

        clickhouse_client = get_client()

    query = (
        "SELECT wallet, platform, market_id, outcome_id, qty, avg_cost "
        "FROM wallet_position_state "
        "WHERE wallet IN %(wallets)s AND qty != 0"
    )
    result = clickhouse_client.query(query, parameters={"wallets": wallets})
    columns = ["wallet", "platform", "market_id", "outcome_id", "qty", "avg_cost"]
    return [dict(zip(columns, row)) for row in result.result_rows]


def _read_marks_for_day(
    dt: date,
    clickhouse_client: Any | None = None,
) -> dict[tuple[str, str, str], float]:
    """Read market_mark_daily from ClickHouse for a given day.

    Returns a dict of (platform, market_id, outcome_id) -> mark_price.
    """
    if clickhouse_client is None:
        from prediction_data.gold.clickhouse import get_client

        clickhouse_client = get_client()

    query = (
        "SELECT platform, market_id, outcome_id, mark_price "
        "FROM market_mark_daily FINAL "
        "WHERE day_utc = %(day)s"
    )
    result = clickhouse_client.query(query, parameters={"day": str(dt)})
    return {
        (row[0], row[1], row[2]): float(row[3]) for row in result.result_rows
    }


def compute_snapshot_for_day(
    positions: list[dict[str, Any]],
    marks: dict[tuple[str, str, str], float],
    dt: date,
) -> pa.Table:
    """Compute per-position snapshot rows from positions and mark prices.

    Args:
        positions: List of position dicts (wallet, platform, market_id,
            outcome_id, qty, avg_cost).
        marks: Dict mapping (platform, market_id, outcome_id) to mark_price.
        dt: The date being computed.

    Returns:
        PyArrow table conforming to WALLET_POSITION_SNAPSHOT_DAILY_SCHEMA.
    """
    rows: dict[str, list[Any]] = {
        col: [] for col in WALLET_POSITION_SNAPSHOT_DAILY_COLUMNS
    }

    for pos in positions:
        wallet = str(pos.get("wallet", "") or "")
        if not wallet:
            continue

        platform = str(pos.get("platform", "") or "")
        market_id = str(pos.get("market_id", "") or "")
        outcome_id = str(pos.get("outcome_id", "") or "")
        qty = float(pos.get("qty") or 0.0)
        avg_cost = float(pos.get("avg_cost") or 0.0)

        mark_key = (platform, market_id, outcome_id)
        mark_price = marks.get(mark_key)

        if mark_price is None:
            logger.debug(
                "missing_mark_for_position_snapshot",
                wallet=wallet,
                platform=platform,
                market_id=market_id,
                outcome_id=outcome_id,
            )
            continue

        position_value = qty * mark_price
        unrealized_pnl = qty * (mark_price - avg_cost)

        rows["day_utc"].append(dt)
        rows["wallet"].append(wallet)
        rows["platform"].append(platform)
        rows["market_id"].append(market_id)
        rows["outcome_id"].append(outcome_id)
        rows["qty"].append(qty)
        rows["avg_cost"].append(avg_cost)
        rows["mark_price"].append(mark_price)
        rows["position_value_usd"].append(position_value)
        rows["unrealized_pnl_usd"].append(unrealized_pnl)

    return pa.table(rows, schema=WALLET_POSITION_SNAPSHOT_DAILY_SCHEMA)


def compute_wallet_position_snapshot(
    *,
    dt: date,
    gold_bucket: str | None = None,
    s3_client: Any | None = None,
    clickhouse_client: Any | None = None,
    dry_run: bool = False,
) -> int:
    """Compute and store wallet_position_snapshot_daily for a single day.

    Reads watchlist wallets, their positions from wallet_position_state,
    and mark prices from market_mark_daily. Creates per-position snapshot
    rows and writes to S3 Gold Parquet + ClickHouse.

    Returns:
        Number of rows produced.
    """
    wallets = _read_watchlist_wallets(clickhouse_client=clickhouse_client)
    if not wallets:
        logger.info("no_watchlist_wallets", day=str(dt))
        return 0

    positions = _read_positions_for_wallets(wallets, clickhouse_client=clickhouse_client)
    marks = _read_marks_for_day(dt, clickhouse_client=clickhouse_client)

    logger.info(
        "computing_position_snapshot",
        day=str(dt),
        watchlist_wallets=len(wallets),
        positions=len(positions),
        marks=len(marks),
    )

    snapshot_table = compute_snapshot_for_day(positions, marks, dt)
    num_rows: int = snapshot_table.num_rows

    logger.info("position_snapshot_computed", day=str(dt), rows=num_rows)

    if dry_run:
        logger.info("dry_run_position_snapshot", rows=num_rows, day=str(dt))
        return num_rows

    if gold_bucket:
        from prediction_data.gold.s3_writer import write_gold_parquet

        write_gold_parquet(
            snapshot_table,
            gold_bucket,
            "wallet_position_snapshot_daily",
            str(dt),
            s3_client=s3_client,
        )

    # Insert into ClickHouse.
    if clickhouse_client is None:
        from prediction_data.gold.clickhouse import get_client

        clickhouse_client = get_client()

    if num_rows > 0:
        clickhouse_client.insert(
            "wallet_position_snapshot_daily",
            data=snapshot_table.to_pylist(),
            column_names=WALLET_POSITION_SNAPSHOT_DAILY_COLUMNS,
        )

    logger.info("loaded_position_snapshot", day=str(dt), rows=num_rows)
    return num_rows
