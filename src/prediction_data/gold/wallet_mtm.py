"""Compute daily mark-to-market for watchlist wallets.

For each active watchlist wallet, loads current positions from
wallet_position_state, joins with market_mark_daily mark prices,
and computes portfolio-level MTM metrics.

Produces one row per (day_utc, wallet) with:
- equity_usd: sum of position values (qty * mark_price)
- unrealized_pnl_usd: sum of qty * (mark_price - avg_cost)
- exposure_gross_usd: sum of abs(qty * mark_price)
- exposure_net_usd: sum of qty * mark_price (signed)
- positions_count: number of open positions
- missing_marks_count: positions skipped due to missing mark prices
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pyarrow as pa
import structlog

logger = structlog.stdlib.get_logger(__name__)

WALLET_MTM_DAILY_SCHEMA = pa.schema(
    [
        pa.field("day_utc", pa.date32()),
        pa.field("wallet", pa.string()),
        pa.field("equity_usd", pa.float64()),
        pa.field("unrealized_pnl_usd", pa.float64()),
        pa.field("exposure_gross_usd", pa.float64()),
        pa.field("exposure_net_usd", pa.float64()),
        pa.field("positions_count", pa.uint64()),
        pa.field("missing_marks_count", pa.uint64()),
    ]
)

WALLET_MTM_DAILY_COLUMNS = [f.name for f in WALLET_MTM_DAILY_SCHEMA]


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
        (row[0], row[1], row[2]): float(row[3])
        for row in result.result_rows
    }


def compute_mtm_for_day(
    positions: list[dict[str, Any]],
    marks: dict[tuple[str, str, str], float],
    dt: date,
) -> pa.Table:
    """Compute wallet_mtm_daily rows from positions and mark prices.

    Args:
        positions: List of position dicts (wallet, platform, market_id,
            outcome_id, qty, avg_cost).
        marks: Dict mapping (platform, market_id, outcome_id) to mark_price.
        dt: The date being computed.

    Returns:
        PyArrow table conforming to WALLET_MTM_DAILY_SCHEMA.
    """
    # Group positions by wallet.
    wallet_positions: dict[str, list[dict[str, Any]]] = {}
    for pos in positions:
        wallet = str(pos.get("wallet", "") or "")
        if not wallet:
            continue
        wallet_positions.setdefault(wallet, []).append(pos)

    rows: dict[str, list[Any]] = {col: [] for col in WALLET_MTM_DAILY_COLUMNS}

    for wallet, pos_list in wallet_positions.items():
        equity = 0.0
        unrealized_pnl = 0.0
        exposure_gross = 0.0
        exposure_net = 0.0
        positions_count = 0
        missing_marks = 0

        for pos in pos_list:
            platform = str(pos.get("platform", "") or "")
            market_id = str(pos.get("market_id", "") or "")
            outcome_id = str(pos.get("outcome_id", "") or "")
            qty = float(pos.get("qty") or 0.0)
            avg_cost = float(pos.get("avg_cost") or 0.0)

            mark_key = (platform, market_id, outcome_id)
            mark_price = marks.get(mark_key)

            if mark_price is None:
                missing_marks += 1
                logger.debug(
                    "missing_mark_for_position",
                    wallet=wallet,
                    platform=platform,
                    market_id=market_id,
                    outcome_id=outcome_id,
                )
                continue

            position_value = qty * mark_price
            equity += position_value
            unrealized_pnl += qty * (mark_price - avg_cost)
            exposure_gross += abs(position_value)
            exposure_net += position_value
            positions_count += 1

        # Only emit rows where the wallet has at least one marked position.
        if positions_count > 0 or missing_marks > 0:
            rows["day_utc"].append(dt)
            rows["wallet"].append(wallet)
            rows["equity_usd"].append(equity)
            rows["unrealized_pnl_usd"].append(unrealized_pnl)
            rows["exposure_gross_usd"].append(exposure_gross)
            rows["exposure_net_usd"].append(exposure_net)
            rows["positions_count"].append(positions_count)
            rows["missing_marks_count"].append(missing_marks)

    return pa.table(rows, schema=WALLET_MTM_DAILY_SCHEMA)


def compute_wallet_mtm(
    *,
    dt: date,
    gold_bucket: str | None = None,
    s3_client: Any | None = None,
    clickhouse_client: Any | None = None,
    dry_run: bool = False,
) -> int:
    """Compute and store wallet_mtm_daily for a single day.

    Reads watchlist wallets, their positions from wallet_position_state,
    and mark prices from market_mark_daily. Computes MTM metrics and
    writes to S3 Gold Parquet + ClickHouse.

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
        "computing_wallet_mtm",
        day=str(dt),
        watchlist_wallets=len(wallets),
        positions=len(positions),
        marks=len(marks),
    )

    mtm_table = compute_mtm_for_day(positions, marks, dt)
    num_rows: int = mtm_table.num_rows

    logger.info("wallet_mtm_computed", day=str(dt), rows=num_rows)

    if dry_run:
        logger.info("dry_run_wallet_mtm", rows=num_rows, day=str(dt))
        return num_rows

    if gold_bucket:
        from prediction_data.gold.s3_writer import write_gold_parquet

        write_gold_parquet(
            mtm_table,
            gold_bucket,
            "wallet_mtm_daily",
            str(dt),
            s3_client=s3_client,
        )

    # Insert into ClickHouse.
    if clickhouse_client is None:
        from prediction_data.gold.clickhouse import get_client

        clickhouse_client = get_client()

    if num_rows > 0:
        clickhouse_client.insert(
            "wallet_mtm_daily",
            data=mtm_table.to_pylist(),
            column_names=WALLET_MTM_DAILY_COLUMNS,
        )

    logger.info("loaded_wallet_mtm", day=str(dt), rows=num_rows)
    return num_rows
