"""Generic S3 Gold Parquet -> ClickHouse loader.

Reads day-partitioned Parquet files from S3 Gold and inserts them
into the corresponding ClickHouse tables.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pyarrow as pa
import structlog

from prediction_data.gold.config import DEFAULT_TTL_DAYS

logger = structlog.stdlib.get_logger(__name__)

# ---------------------------------------------------------------------------
# Table registry: maps Gold table names to their ClickHouse column lists.
# ---------------------------------------------------------------------------

LOADABLE_GOLD_TABLES: dict[str, list[str]] = {}
"""Populated lazily by _get_table_columns() to avoid circular imports."""


def _get_table_columns(table_name: str) -> list[str]:
    """Return the ordered column list for a Gold table.

    Raises ``ValueError`` if *table_name* is not a known Gold table.
    """
    if table_name in LOADABLE_GOLD_TABLES:
        return LOADABLE_GOLD_TABLES[table_name]

    if table_name == "market_mark_daily":
        from prediction_data.gold.market_marks import MARKET_MARK_DAILY_COLUMNS

        cols = MARKET_MARK_DAILY_COLUMNS
    elif table_name == "wallet_pnl_daily":
        from prediction_data.gold.wallet_pnl import WALLET_PNL_DAILY_COLUMNS

        cols = WALLET_PNL_DAILY_COLUMNS
    elif table_name == "wallet_mtm_daily":
        from prediction_data.gold.wallet_mtm import WALLET_MTM_DAILY_COLUMNS

        cols = WALLET_MTM_DAILY_COLUMNS
    elif table_name == "wallet_position_snapshot_daily":
        from prediction_data.gold.wallet_position_snapshot import (
            WALLET_POSITION_SNAPSHOT_DAILY_COLUMNS,
        )

        cols = WALLET_POSITION_SNAPSHOT_DAILY_COLUMNS
    elif table_name == "wallet_position_ledger":
        from prediction_data.gold.ledger import LEDGER_COLUMNS

        cols = LEDGER_COLUMNS
    elif table_name == "wallet_position_state":
        from prediction_data.gold.position_state import POSITION_STATE_COLUMNS

        cols = POSITION_STATE_COLUMNS
    else:
        raise ValueError(
            f"Unknown Gold table: {table_name}. "
            f"Supported: {', '.join(ALL_GOLD_TABLES)}"
        )

    LOADABLE_GOLD_TABLES[table_name] = cols
    return cols


# Ordered list of all Gold fact tables that can be loaded into ClickHouse.
ALL_GOLD_TABLES: list[str] = [
    "market_mark_daily",
    "wallet_pnl_daily",
    "wallet_mtm_daily",
    "wallet_position_snapshot_daily",
    "wallet_position_ledger",
    "wallet_position_state",
]


def _read_gold_parquet_for_day(
    gold_bucket: str,
    table_name: str,
    day: str,
    *,
    s3_client: Any | None = None,
) -> pa.Table | None:
    """Read a single Gold partition from S3, returning *None* if missing."""
    import io

    import pyarrow.parquet as pq

    if s3_client is None:
        import boto3

        s3_client = boto3.client("s3")

    key = f"gold/{table_name}/day={day}/part-000.parquet"
    try:
        resp = s3_client.get_object(Bucket=gold_bucket, Key=key)
        buf = io.BytesIO(resp["Body"].read())
        return pq.read_table(buf)
    except s3_client.exceptions.NoSuchKey:
        return None
    except Exception:
        logger.debug("could_not_read_gold_partition", table=table_name, day=day, key=key)
        return None


def load_gold_table_to_clickhouse(
    *,
    table_name: str,
    gold_bucket: str,
    lookback_days: int = DEFAULT_TTL_DAYS,
    s3_client: Any | None = None,
    clickhouse_client: Any | None = None,
) -> int:
    """Load a single Gold table from S3 Parquet partitions into ClickHouse.

    Scans the most recent *lookback_days* of day partitions in S3 and
    inserts them into the ClickHouse table.

    Args:
        table_name: Gold table name (e.g. ``"market_mark_daily"``).
        gold_bucket: S3 bucket containing Gold Parquet files.
        lookback_days: Number of days to look back from today.
        s3_client: Optional boto3 S3 client.
        clickhouse_client: Optional ClickHouse client.

    Returns:
        Total number of rows loaded.
    """
    columns = _get_table_columns(table_name)

    if clickhouse_client is None:
        from prediction_data.gold.clickhouse import get_client

        clickhouse_client = get_client()

    if s3_client is None:
        import boto3

        s3_client = boto3.client("s3")

    today = date.today()
    total_rows = 0
    days_loaded = 0

    for offset in range(lookback_days):
        day = today - timedelta(days=offset)
        tbl = _read_gold_parquet_for_day(gold_bucket, table_name, str(day), s3_client=s3_client)
        if tbl is None or tbl.num_rows == 0:
            continue
        # Convert to list of tuples (clickhouse_connect format)
        data_dicts = tbl.to_pylist()
        data_tuples = [tuple(d[c] for c in columns) for d in data_dicts]
        clickhouse_client.insert(
            table_name,
            data=data_tuples,
            column_names=columns,
        )
        total_rows += tbl.num_rows
        days_loaded += 1

    logger.info(
        "loaded_gold_table_to_ch",
        table=table_name,
        lookback_days=lookback_days,
        days_loaded=days_loaded,
        total_rows=total_rows,
    )
    return total_rows
