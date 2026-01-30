#!/usr/bin/env python3
"""Convert historical order_filled parquet data into bronze JSONL.gz format.

Reads the monolithic parquet file at s3://polymarket-bcp892/raw/polymarket/order_filled.parquet
(~15 GB, 313M rows) and converts to per-day bronze JSONL.gz files.

Performance: Uses a single-pass scan over all 3,994 row groups, bucketing rows by
date as they are read. This means the 15 GB file is streamed exactly once regardless
of how many days are in the requested range (O(row_groups) vs O(days * row_groups)).

Memory management: Since the parquet is roughly sorted by timestamp, completed days
are detected when a row group's min timestamp advances past them. Those days are
immediately uploaded to bronze and freed from memory, keeping usage proportional to
~1-2 days of data rather than the entire 313M-row file.

Token ID resolution: The parquet stores asset IDs as float-notation strings
(e.g. '6.58e+76') due to precision loss. Full-precision token IDs are resolved
by building a mapping from bronze markets JSONL data (clobTokenIds field).

Field conversions:
  - snake_case -> camelCase (transaction_hash -> transactionHash, etc.)
  - Amounts: float USDC values multiplied by 1e6 to match subgraph base units
  - Timestamp: datetime -> Unix epoch int (seconds)
  - Asset IDs: float-notation strings resolved to full-precision token IDs
  - Missing fields set to null: orderHash, fee, id

Usage:
    python scripts/backfill_order_filled_from_parquet.py --start-date 2022-11-01 --end-date 2026-01-31
    python scripts/backfill_order_filled_from_parquet.py --start-date 2024-06-01 --end-date 2024-06-30 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import sys
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any

import pyarrow as pa
import pyarrow.fs as pafs
import pyarrow.parquet as pq
import structlog

from prediction_data.core.config import get_settings
from prediction_data.core.run import RunContext
from prediction_data.storage.manifest import create_manifest
from prediction_data.storage.s3 import S3Client

logger = structlog.stdlib.get_logger(__name__)

SOURCE_BUCKET = "polymarket-bcp892"
SOURCE_KEY = "raw/polymarket/order_filled.parquet"
MARKETS_KEY = "raw/polymarket/markets.parquet"

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

AMOUNT_FIELDS = {"maker_amount_filled", "taker_amount_filled", "fee"}
ASSET_ID_FIELDS = {"maker_asset_id", "taker_asset_id"}


def _build_token_id_mapping(bronze_bucket: str) -> dict[str, str]:
    """Build float-string -> full-precision token ID mapping.

    The raw markets.parquet has corrupted token1/token2 columns, so we use the
    bronze markets JSONL which has full-precision clobTokenIds from the Gamma API.
    """
    import boto3

    logger.info("Building token ID mapping from bronze markets data")
    s3 = boto3.client("s3")

    # Read from bronze markets JSONL (has full-precision clobTokenIds)
    prefix = "bronze/polymarket/markets/"
    paginator = s3.get_paginator("list_objects_v2")
    data_keys: list[str] = []
    for page in paginator.paginate(Bucket=bronze_bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".jsonl.gz"):
                data_keys.append(obj["Key"])

    if not data_keys:
        logger.warning("No bronze markets data found, token IDs will not be resolved")
        return {}

    # Use the most recent file
    data_key = sorted(data_keys)[-1]
    logger.info("Reading markets from bronze", key=data_key)

    resp = s3.get_object(Bucket=bronze_bucket, Key=data_key)
    raw = gzip.decompress(resp["Body"].read())

    mapping: dict[str, str] = {}
    total_markets = 0
    for line in raw.split(b"\n"):
        if not line:
            continue
        market = json.loads(line)
        total_markets += 1
        raw_tokens = market.get("clobTokenIds")
        if not raw_tokens:
            continue
        tokens = json.loads(raw_tokens) if isinstance(raw_tokens, str) else raw_tokens
        for token_id in tokens:
            float_key = str(float(token_id))
            mapping[float_key] = token_id

    logger.info(
        "Token ID mapping built",
        total_markets=total_markets,
        unique_tokens=len(mapping),
    )
    return mapping


def _convert_record(
    row: dict[str, Any],
    token_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Convert a single parquet row to bronze camelCase format."""
    record: dict[str, Any] = {}
    for src_field, dst_field in FIELD_MAP.items():
        value = row.get(src_field)
        if value is None:
            record[dst_field] = None
            continue

        if src_field in AMOUNT_FIELDS:
            # Parquet values are scaled floats (e.g. 4.45 USDC).
            # Multiply by 1e6 to match subgraph base units.
            record[dst_field] = int(round(float(value) * 1_000_000))
        elif src_field == "timestamp":
            # Convert datetime to Unix epoch seconds
            if isinstance(value, datetime):
                record[dst_field] = int(value.replace(tzinfo=UTC).timestamp())
            elif isinstance(value, (int, float)):
                record[dst_field] = int(value)
            else:
                record[dst_field] = value
        elif src_field in ASSET_ID_FIELDS and token_map is not None:
            # Resolve float-notation asset ID to full-precision token ID
            str_value = str(value)
            record[dst_field] = token_map.get(str_value, str_value)
        else:
            record[dst_field] = value

    # Fields missing from parquet source, set to null
    for missing_field in ("orderHash", "fee", "id"):
        if missing_field not in record:
            record[missing_field] = None

    return record


def _open_parquet_file() -> pq.ParquetFile:
    """Open the monolithic parquet file from S3 using PyArrow S3 filesystem."""
    s3 = pafs.S3FileSystem(region="us-east-1")
    return pq.ParquetFile(
        s3.open_input_file(f"{SOURCE_BUCKET}/{SOURCE_KEY}")
    )


async def _upload_day(
    dt: date,
    records: list[dict[str, Any]],
    *,
    bronze_bucket: str,
    dry_run: bool = False,
) -> int:
    """Upload converted records for a single day to bronze."""
    dt_str = dt.isoformat()

    logger.info("Uploading day", dt=dt_str, count=len(records))

    if dry_run:
        logger.info(
            "Dry run — skipping S3 upload",
            dt=dt_str,
            record_count=len(records),
            sample=records[0],
        )
        return len(records)

    run_ctx = RunContext(platform="polymarket", entity="order_filled")
    run_ctx.bind_to_logger(dt=dt_str)
    run_ctx.log_start(logger)

    async with S3Client(bucket=bronze_bucket) as s3_client:
        data_key, row_count = await s3_client.upload_jsonl(
            records=records,
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
            api_base_url=f"s3://{SOURCE_BUCKET}/{SOURCE_KEY}",
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
    """Run the parquet-to-bronze conversion for a date range.

    Single-pass streaming scan with incremental flushing:
      1. Scans all row groups once (O(row_groups), not O(days * row_groups)).
      2. Buckets rows by date in memory.
      3. Since the parquet is roughly sorted by timestamp, completed days are
         detected when a row group's minimum timestamp advances past a day.
         Those days are flushed (uploaded) and freed from memory immediately.
      4. Any remaining days are flushed after the scan completes.

    This keeps memory proportional to ~1-2 days of data at a time rather than
    the entire date range (~313M rows), preventing OOM on large backfills.
    """
    settings = get_settings()
    bronze_bucket = settings.bronze_bucket

    # Build token ID mapping upfront (float-notation -> full-precision)
    token_map = _build_token_id_mapping(bronze_bucket)

    # Open the monolithic parquet file once (streams row groups on demand)
    logger.info("Opening parquet file", bucket=SOURCE_BUCKET, key=SOURCE_KEY)
    pf = _open_parquet_file()
    logger.info(
        "Parquet file opened",
        row_groups=pf.metadata.num_row_groups,
        total_rows=pf.metadata.num_rows,
    )

    range_start = int(datetime(start_date.year, start_date.month, start_date.day, tzinfo=UTC).timestamp())
    range_end = int(datetime(end_date.year, end_date.month, end_date.day, tzinfo=UTC).timestamp()) + 86400

    columns = list(FIELD_MAP.keys())
    parquet_columns = [c for c in columns if c in pf.schema_arrow.names]

    buckets: dict[date, list[dict[str, Any]]] = defaultdict(list)
    total_records = 0
    days_converted = 0
    days_failed = 0
    failed_dates: list[str] = []
    rows_scanned = 0
    rows_matched = 0
    rg_skipped = 0

    async def _flush_completed_days(before_epoch: int) -> None:
        """Upload and free days whose timestamps are entirely before before_epoch."""
        nonlocal total_records, days_converted, days_failed
        before_date = datetime.fromtimestamp(before_epoch, tz=UTC).date()
        completed = sorted(d for d in buckets if d < before_date)
        for dt in completed:
            records = buckets.pop(dt)
            try:
                count = await _upload_day(
                    dt, records, bronze_bucket=bronze_bucket, dry_run=dry_run,
                )
                if count > 0:
                    days_converted += 1
                    total_records += count
            except Exception:
                logger.exception("Failed to upload day", dt=dt.isoformat())
                days_failed += 1
                failed_dates.append(dt.isoformat())

    # Single-pass scan with incremental flush
    for rg_idx in range(pf.metadata.num_row_groups):
        table = pf.read_row_group(rg_idx, columns=parquet_columns)
        ts_arr = table.column("timestamp").cast(pa.int64())
        ts_list = ts_arr.to_pylist()

        if not ts_list:
            continue

        rows_scanned += len(ts_list)

        rg_min = min(ts_list)
        rg_max = max(ts_list)
        if rg_max < range_start or rg_min >= range_end:
            rg_skipped += 1
            continue

        # Flush any days that are fully behind the current row group's min timestamp
        if buckets and rg_min > range_start:
            await _flush_completed_days(rg_min)

        table_dict = table.to_pydict()
        for i, ts_val in enumerate(ts_list):
            if ts_val < range_start or ts_val >= range_end:
                continue
            row = {col: table_dict[col][i] for col in parquet_columns}
            row["timestamp"] = ts_val
            record = _convert_record(row, token_map=token_map)
            row_date = datetime.fromtimestamp(ts_val, tz=UTC).date()
            buckets[row_date].append(record)
            rows_matched += 1

        if (rg_idx + 1) % 500 == 0:
            logger.info(
                "Scan progress",
                row_groups_processed=rg_idx + 1,
                total_row_groups=pf.metadata.num_row_groups,
                rows_matched=rows_matched,
                days_in_memory=len(buckets),
                days_flushed=days_converted,
            )

    logger.info(
        "Scan complete",
        row_groups_total=pf.metadata.num_row_groups,
        row_groups_skipped=rg_skipped,
        rows_scanned=rows_scanned,
        rows_matched=rows_matched,
        days_remaining=len(buckets),
    )

    # Flush remaining days
    for dt in sorted(buckets.keys()):
        records = buckets.pop(dt)
        try:
            count = await _upload_day(
                dt, records, bronze_bucket=bronze_bucket, dry_run=dry_run,
            )
            if count > 0:
                days_converted += 1
                total_records += count
        except Exception:
            logger.exception("Failed to upload day", dt=dt.isoformat())
            days_failed += 1
            failed_dates.append(dt.isoformat())

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
        description="Convert order_filled.parquet to bronze JSONL.gz format",
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
