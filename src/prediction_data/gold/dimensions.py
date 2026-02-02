"""Gold dimension table loaders."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pyarrow as pa
import structlog

from prediction_data.gold.clickhouse import get_client
from prediction_data.gold.s3_writer import write_gold_parquet

logger = structlog.stdlib.get_logger(__name__)

# Static platform data.
PLATFORMS = [
    {
        "platform_id": "polymarket",
        "platform_name": "Polymarket",
        "url": "https://polymarket.com",
    },
    {
        "platform_id": "kalshi",
        "platform_name": "Kalshi",
        "url": "https://kalshi.com",
    },
]

DIM_PLATFORM_SCHEMA = pa.schema(
    [
        pa.field("platform_id", pa.string()),
        pa.field("platform_name", pa.string()),
        pa.field("url", pa.string()),
    ]
)


def _platforms_to_arrow() -> pa.Table:
    """Convert static platform data to a PyArrow table."""
    return pa.table(
        {
            "platform_id": [p["platform_id"] for p in PLATFORMS],
            "platform_name": [p["platform_name"] for p in PLATFORMS],
            "url": [p["url"] for p in PLATFORMS],
        },
        schema=DIM_PLATFORM_SCHEMA,
    )


def load_dim_platform(
    *,
    gold_bucket: str | None = None,
    s3_client: Any | None = None,
    clickhouse_client: Any | None = None,
    dry_run: bool = False,
) -> int:
    """Load the dim_platform dimension table.

    Writes static platform rows to S3 Gold Parquet and inserts into ClickHouse.

    Args:
        gold_bucket: S3 bucket for Gold output. Skips S3 write if *None*.
        s3_client: Optional boto3 S3 client.
        clickhouse_client: Optional ClickHouse client. Creates one if *None*.
        dry_run: Preview without writing.

    Returns:
        Number of rows loaded.
    """
    table = _platforms_to_arrow()
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    num_rows: int = table.num_rows

    if dry_run:
        logger.info("dry_run_dim_platform", rows=num_rows, day=day)
        return num_rows

    # Write to S3 if bucket configured.
    if gold_bucket:
        write_gold_parquet(
            table,
            gold_bucket,
            "dim_platform",
            day,
            s3_client=s3_client,
        )

    # Insert into ClickHouse.
    ch = clickhouse_client or get_client()
    ch.insert(
        "dim_platform",
        data=[[p["platform_id"], p["platform_name"], p["url"]] for p in PLATFORMS],
        column_names=["platform_id", "platform_name", "url"],
    )

    logger.info("loaded_dim_platform", rows=num_rows, day=day)
    return num_rows
