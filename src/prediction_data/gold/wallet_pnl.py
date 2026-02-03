"""Compute daily realized PnL aggregation from wallet_position_ledger.

Produces one row per (day_utc, wallet) with:
- Realized PnL (sum of realized_pnl_this_fill_usd)
- Fees paid (sum of fees_usd)
- Volume traded (sum of abs(qty_delta * price))
- Trade count (number of fills)
- Wins / losses (fills with positive vs negative realized PnL)

Only emits rows where trades_count > 0 (sparse output).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pyarrow as pa
import structlog

logger = structlog.stdlib.get_logger(__name__)

WALLET_PNL_DAILY_SCHEMA = pa.schema(
    [
        pa.field("day_utc", pa.date32()),
        pa.field("wallet", pa.string()),
        pa.field("realized_pnl_usd", pa.float64()),
        pa.field("fees_usd", pa.float64()),
        pa.field("volume_usd", pa.float64()),
        pa.field("trades_count", pa.uint64()),
        pa.field("wins", pa.uint64()),
        pa.field("losses", pa.uint64()),
    ]
)

WALLET_PNL_DAILY_COLUMNS = [f.name for f in WALLET_PNL_DAILY_SCHEMA]


def _read_ledger_for_day(
    dt: date,
    clickhouse_client: Any | None = None,
) -> list[dict[str, Any]]:
    """Read wallet_position_ledger rows for a single day from ClickHouse."""
    if clickhouse_client is None:
        from prediction_data.gold.clickhouse import get_client

        clickhouse_client = get_client()

    query = (
        "SELECT wallet, qty_delta, price, fees_usd, realized_pnl_this_fill_usd "
        "FROM wallet_position_ledger "
        "WHERE toDate(ts) = %(day)s"
    )
    result = clickhouse_client.query(query, parameters={"day": str(dt)})
    columns = ["wallet", "qty_delta", "price", "fees_usd", "realized_pnl_this_fill_usd"]
    return [dict(zip(columns, row)) for row in result.result_rows]


def aggregate_pnl_for_day(
    ledger_rows: list[dict[str, Any]],
    dt: date,
) -> pa.Table:
    """Aggregate ledger rows into wallet_pnl_daily rows.

    Args:
        ledger_rows: List of dicts with wallet, qty_delta, price, fees_usd,
            realized_pnl_this_fill_usd fields.
        dt: The date being computed.

    Returns:
        PyArrow table conforming to WALLET_PNL_DAILY_SCHEMA.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in ledger_rows:
        wallet = str(row.get("wallet", "") or "")
        if not wallet:
            continue
        groups.setdefault(wallet, []).append(row)

    rows: dict[str, list[Any]] = {col: [] for col in WALLET_PNL_DAILY_COLUMNS}

    for wallet, fills in groups.items():
        realized_pnl = sum(
            float(f.get("realized_pnl_this_fill_usd") or 0.0) for f in fills
        )
        fees = sum(float(f.get("fees_usd") or 0.0) for f in fills)
        volume = sum(
            abs(float(f.get("qty_delta") or 0.0) * float(f.get("price") or 0.0))
            for f in fills
        )
        trades_count = len(fills)
        wins = sum(
            1 for f in fills if float(f.get("realized_pnl_this_fill_usd") or 0.0) > 0
        )
        losses = sum(
            1 for f in fills if float(f.get("realized_pnl_this_fill_usd") or 0.0) < 0
        )

        rows["day_utc"].append(dt)
        rows["wallet"].append(wallet)
        rows["realized_pnl_usd"].append(realized_pnl)
        rows["fees_usd"].append(fees)
        rows["volume_usd"].append(volume)
        rows["trades_count"].append(trades_count)
        rows["wins"].append(wins)
        rows["losses"].append(losses)

    return pa.table(rows, schema=WALLET_PNL_DAILY_SCHEMA)


def compute_wallet_pnl(
    *,
    dt: date,
    gold_bucket: str | None = None,
    s3_client: Any | None = None,
    clickhouse_client: Any | None = None,
    dry_run: bool = False,
) -> int:
    """Compute and store wallet_pnl_daily for a single day.

    Reads wallet_position_ledger from ClickHouse, aggregates per wallet,
    and writes to S3 Gold Parquet + ClickHouse.

    Returns:
        Number of rows produced.
    """
    ledger_rows = _read_ledger_for_day(dt, clickhouse_client=clickhouse_client)

    logger.info(
        "computing_wallet_pnl",
        day=str(dt),
        ledger_rows=len(ledger_rows),
    )

    pnl_table = aggregate_pnl_for_day(ledger_rows, dt)
    num_rows: int = pnl_table.num_rows

    logger.info("wallet_pnl_computed", day=str(dt), rows=num_rows)

    if dry_run:
        logger.info("dry_run_wallet_pnl", rows=num_rows, day=str(dt))
        return num_rows

    if gold_bucket:
        from prediction_data.gold.s3_writer import write_gold_parquet

        write_gold_parquet(
            pnl_table,
            gold_bucket,
            "wallet_pnl_daily",
            str(dt),
            s3_client=s3_client,
        )

    # Insert into ClickHouse.
    if clickhouse_client is None:
        from prediction_data.gold.clickhouse import get_client

        clickhouse_client = get_client()

    clickhouse_client.insert(
        "wallet_pnl_daily",
        data=pnl_table.to_pylist(),
        column_names=WALLET_PNL_DAILY_COLUMNS,
    )

    logger.info("loaded_wallet_pnl", day=str(dt), rows=num_rows)
    return num_rows
