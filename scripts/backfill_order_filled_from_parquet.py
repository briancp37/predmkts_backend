#!/usr/bin/env python3
"""Convert existing S3 parquet order_filled data into bronze JSONL.gz format.

Reads parquet files from s3://polymarket-bcp892/raw/polymarket/order_filled/,
converts fields to match the Goldsky subgraph schema (camelCase, base units),
and writes to the bronze bucket as JSONL.gz.

Field conversions:
  - snake_case -> camelCase (transaction_hash -> transactionHash, etc.)
  - Amounts: float * 1e6 -> int (e.g. 4.45 -> 4450000) to match subgraph base units
  - Timestamp: datetime -> Unix epoch int (seconds)
  - Missing fields set to null: orderHash, fee, id

Usage:
    python scripts/backfill_order_filled_from_parquet.py --start-date 2024-01-01 --end-date 2024-01-31
    python scripts/backfill_order_filled_from_parquet.py --start-date 2024-06-01 --end-date 2024-06-30 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pyarrow.parquet as pq
import structlog

from prediction_data.core.config import get_settings
from prediction_data.core.run import RunContext
from prediction_data.storage.manifest import create_manifest
from prediction_data.storage.s3 import S3Client

logger = structlog.stdlib.get_logger(__name__)

SOURCE_BUCKET = "polymarket-bcp892"
SOURCE_PREFIX = "raw/polymarket/order_filled/"

# snake_case parquet field -> camelCase subgraph field
FIELD_MAP: dict[str, str] = {
    "transaction_hash": "transactionHash",
    "order_hash": "orderHash",
    "timestamp": "timestamp",
    "maker": "maker",
    "taker": "taker",
    "maker_asset_id": "makerAssetId",
    "taker_asset_id": "takerAssetId",
    "maker_amount_filled": "makerAmountFilled",
    "taker_amount_filled": "takerAmountFilled",
    "fee": "fee",
}

# Fields whose float values should be scaled to base units (multiply by 1e6)
AMOUNT_FIELDS = {"maker_amount_filled", "taker_amount_filled", "fee"}


def _convert_record(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a single parquet row to bronze camelCase format."""
    record: dict[str, Any] = {}
    for src_field, dst_field in FIELD_MAP.items():
        value = row.get(src_field)
        if value is None:
            record[dst_field] = None
            continue

        if src_field in AMOUNT_FIELDS:
            # Scale float to base units (1e6) and cast to int
            record[dst_field] = int(round(float(value) * 1_000_000))
        elif src_field == "timestamp":
            # Convert datetime to Unix epoch seconds
            if isinstance(value, datetime):
                record[dst_field] = int(value.replace(tzinfo=UTC).timestamp())
            elif isinstance(value, (int, float)):
                record[dst_field] = int(value)
            else:
                record[dst_field] = value
        else:
            record[dst_field] = value

    # Fields missing from parquet source, set to null
    for missing_field in ("orderHash", "fee", "id"):
        if missing_field not in record:
            record[missing_field] = None

    return record


def _list_parquet_keys_for_date(
    s3_client: Any, bucket: str, prefix: str, dt: date
) -> list[str]:
    """List parquet file keys for a given date partition."""
    # Try hive-style partition dt=YYYY-MM-DD
    date_prefix = f"{prefix}dt={dt.isoformat()}/"
    keys = _list_s3_keys(s3_client, bucket, date_prefix)
    if keys:
        return [k for k in keys if k.endswith(".parquet")]

    # Try flat prefix with date in filename
    flat_prefix = f"{prefix}{dt.isoformat()}"
    keys = _list_s3_keys(s3_client, bucket, flat_prefix)
    return [k for k in keys if k.endswith(".parquet")]


def _list_s3_keys(s3_client: Any, bucket: str, prefix: str) -> list[str]:
    """List all S3 keys under a prefix."""
    paginator = s3_client.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def _read_parquet_from_s3(s3_client: Any, bucket: str, key: str) -> list[dict[str, Any]]:
    """Read a parquet file from S3 and return as list of dicts."""
    response = s3_client.get_object(Bucket=bucket, Key=key)
    import io

    buffer = io.BytesIO(response["Body"].read())
    table = pq.read_table(buffer)
    return table.to_pydict()  # type: ignore[no-any-return]


def _table_dict_to_rows(table_dict: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Convert pyarrow columnar dict to list of row dicts."""
    if not table_dict:
        return []
    columns = list(table_dict.keys())
    n_rows = len(table_dict[columns[0]])
    return [{col: table_dict[col][i] for col in columns} for i in range(n_rows)]


async def convert_day(
    dt: date,
    *,
    bronze_bucket: str,
    dry_run: bool = False,
) -> int:
    """Convert parquet data for a single day to bronze JSONL.gz.

    Returns the number of records converted.
    """
    import boto3

    raw_s3 = boto3.client("s3")
    dt_str = dt.isoformat()

    parquet_keys = _list_parquet_keys_for_date(raw_s3, SOURCE_BUCKET, SOURCE_PREFIX, dt)
    if not parquet_keys:
        logger.info("No parquet files found for date", dt=dt_str)
        return 0

    # Read and convert all records for this day
    all_records: list[dict[str, Any]] = []
    for key in parquet_keys:
        logger.info("Reading parquet file", bucket=SOURCE_BUCKET, key=key)
        table_dict = _read_parquet_from_s3(raw_s3, SOURCE_BUCKET, key)
        rows = _table_dict_to_rows(table_dict)
        for row in rows:
            all_records.append(_convert_record(row))

    if not all_records:
        logger.info("No records in parquet files for date", dt=dt_str)
        return 0

    logger.info("Converted records", dt=dt_str, count=len(all_records))

    if dry_run:
        logger.info(
            "Dry run — skipping S3 upload",
            dt=dt_str,
            record_count=len(all_records),
            sample=all_records[0],
        )
        return len(all_records)

    # Upload to bronze
    run_ctx = RunContext(platform="polymarket", entity="order_filled")
    run_ctx.bind_to_logger(dt=dt_str)
    run_ctx.log_start(logger)

    async with S3Client(bucket=bronze_bucket) as s3_client:
        data_key, row_count = await s3_client.upload_jsonl(
            records=all_records,
            platform="polymarket",
            entity="order_filled",
            dt=dt_str,
            run_id=run_ctx.run_id,
        )

        manifest = create_manifest(
            run_id=run_ctx.run_id,
            platform="polymarket",
            entity="order_filled",
            dt=dt_str,
            bucket=bronze_bucket,
            key=data_key,
            row_count=row_count,
            api_base_url=f"s3://{SOURCE_BUCKET}/{SOURCE_PREFIX}",
            pagination="none",
        )

        await s3_client.upload_manifest(manifest)

    run_ctx.mark_complete()
    run_ctx.log_end(logger)
    return row_count


async def main(
    start_date: date,
    end_date: date,
    *,
    dry_run: bool = False,
) -> None:
    """Run the parquet-to-bronze conversion for a date range."""
    settings = get_settings()
    bronze_bucket = settings.bronze_bucket

    current = start_date
    total_records = 0
    days_converted = 0
    days_failed = 0
    failed_dates: list[str] = []

    while current <= end_date:
        try:
            count = await convert_day(current, bronze_bucket=bronze_bucket, dry_run=dry_run)
            if count > 0:
                days_converted += 1
                total_records += count
        except Exception:
            logger.exception("Failed to convert day", dt=current.isoformat())
            days_failed += 1
            failed_dates.append(current.isoformat())
        current += timedelta(days=1)

    logger.info(
        "Backfill complete",
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        days_converted=days_converted,
        days_failed=days_failed,
        total_records=total_records,
        dry_run=dry_run,
    )

    if failed_dates:
        logger.warning("Failed dates", dates=failed_dates)
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Convert parquet order_filled data to bronze JSONL.gz format",
    )
    parser.add_argument(
        "--start-date",
        type=date.fromisoformat,
        required=True,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        required=True,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview conversion without writing to S3",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.start_date, args.end_date, dry_run=args.dry_run))
