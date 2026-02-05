"""Batch processor for Silver trades through the position accounting pipeline.

Orchestrates the full pipeline:
1. Read Silver polymarket.trades for a given date via PyIceberg
2. Load current position state from ClickHouse (or initialize empty)
3. Split trades into fills, sort by timestamp
4. Process through accounting engine via build_ledger_for_day()
5. Write ledger to S3 Gold + ClickHouse
6. Update position_state in ClickHouse

Idempotency:
- Tracks processed dates in an S3 state store (JSONL)
- Re-running for an already-processed date is a no-op unless --force-reprocess
- Ledger S3 writes use partition-level overwrite (idempotent)
- Position state uses ReplacingMergeTree (idempotent upsert)
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog

from prediction_data.gold.accounting import PositionState
from prediction_data.gold.fill_splitter import Fill, trades_to_fills
from prediction_data.gold.ledger import LedgerWriter, build_ledger_for_day
from prediction_data.gold.position_state import (
    read_position_states,
    write_position_states,
)

logger = structlog.stdlib.get_logger(__name__)

# S3 key for the Gold trade processing state store.
_STATE_KEY = "gold/_state/trade_processor/processed.jsonl"


# ---------------------------------------------------------------------------
# Silver trade reader
# ---------------------------------------------------------------------------


def _read_silver_trades_for_day(
    dt: date,
    *,
    platform: str = "polymarket",
    catalog: Any | None = None,
) -> list[dict[str, Any]]:
    """Read Silver trades for *platform* on a single day.

    Returns a list of trade dicts suitable for :func:`trades_to_fills`.
    """
    if catalog is None:
        from prediction_data.silver.catalog import get_catalog

        catalog = get_catalog()

    from pyiceberg.expressions import And, GreaterThanOrEqual, LessThan

    namespace = f"silver_{platform}"
    table = catalog.load_table((namespace, "trades"))

    day_start = datetime(dt.year, dt.month, dt.day, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)

    row_filter = And(
        GreaterThanOrEqual("event_ts", day_start.isoformat()),
        LessThan("event_ts", day_end.isoformat()),
    )

    arrow_table = table.scan(row_filter=row_filter).to_arrow()
    records: list[dict[str, Any]] = arrow_table.to_pylist()

    logger.info(
        "read_silver_trades",
        platform=platform,
        day=str(dt),
        trades=len(records),
    )
    return records


# ---------------------------------------------------------------------------
# State store (idempotency)
# ---------------------------------------------------------------------------


def _load_processed_dates(
    s3_client: Any,
    bucket: str,
) -> set[str]:
    """Load the set of already-processed dates from the S3 state store."""
    try:
        resp = s3_client.get_object(Bucket=bucket, Key=_STATE_KEY)
        body = resp["Body"].read().decode("utf-8")
        dates: set[str] = set()
        for line in body.strip().splitlines():
            if line.strip():
                entry = json.loads(line)
                if entry.get("day"):
                    dates.add(entry["day"])
        return dates
    except s3_client.exceptions.NoSuchKey:
        return set()
    except Exception:
        logger.debug("state_load_no_file", key=_STATE_KEY)
        return set()


def _mark_processed(
    s3_client: Any,
    bucket: str,
    day: str,
    *,
    fills_processed: int,
    positions_updated: int,
    realized_pnl_total: float,
) -> None:
    """Append a processed-day entry to the S3 state store."""
    entry = json.dumps(
        {
            "day": day,
            "processed_at": datetime.now(UTC).isoformat(),
            "fills_processed": fills_processed,
            "positions_updated": positions_updated,
            "realized_pnl_total": round(realized_pnl_total, 6),
        },
        separators=(",", ":"),
    )

    # Read-modify-write (safe for single-writer scenarios).
    existing = ""
    try:
        resp = s3_client.get_object(Bucket=bucket, Key=_STATE_KEY)
        existing = resp["Body"].read().decode("utf-8")
    except Exception:
        pass

    new_content = existing.rstrip("\n")
    if new_content:
        new_content += "\n"
    new_content += entry + "\n"

    s3_client.put_object(
        Bucket=bucket,
        Key=_STATE_KEY,
        Body=new_content.encode("utf-8"),
        ContentType="application/x-ndjson",
    )


# ---------------------------------------------------------------------------
# Core processor
# ---------------------------------------------------------------------------


def _compute_summary(
    writer: LedgerWriter,
    positions: dict[tuple[str, str, str, str], PositionState],
) -> tuple[int, float]:
    """Compute summary stats from a processed ledger.

    Returns:
        (positions_updated, realized_pnl_total)
    """
    positions_updated = sum(
        1 for p in positions.values() if p.last_fill_ts is not None
    )

    realized_pnl_total = sum(row.realized_pnl_this_fill_usd for row in writer.rows)

    return positions_updated, realized_pnl_total


def process_day(
    *,
    dt: date,
    platform: str = "polymarket",
    gold_bucket: str | None = None,
    s3_client: Any | None = None,
    clickhouse_client: Any | None = None,
    catalog: Any | None = None,
    dry_run: bool = False,
    force_reprocess: bool = False,
) -> int:
    """Process Silver trades for a single day through the accounting pipeline.

    This is the main entry point for the batch processor. It:
    1. Reads Silver trades for the given date
    2. Loads existing position state from ClickHouse
    3. Splits trades into fills, processes through accounting engine
    4. Writes ledger to S3 Gold Parquet + ClickHouse
    5. Updates position state in ClickHouse
    6. Records the day as processed in the S3 state store

    Args:
        dt: Date to process.
        platform: Platform identifier (default ``"polymarket"``).
        gold_bucket: S3 bucket for Gold output. Skips S3 writes when *None*.
        s3_client: Optional boto3 S3 client.
        clickhouse_client: Optional ClickHouse client.
        catalog: Optional PyIceberg catalog for reading Silver.
        dry_run: If *True*, log what would be written but don't persist.
        force_reprocess: If *True*, reprocess even if already done.

    Returns:
        Number of ledger rows written (fills processed).
    """
    day_str = str(dt)

    logger.info("process_day_start", day=day_str, platform=platform, dry_run=dry_run)

    # Resolve S3 client for state store and Gold writes.
    if s3_client is None and gold_bucket:
        import boto3

        s3_client = boto3.client("s3")

    # Idempotency check.
    if not force_reprocess and gold_bucket and s3_client is not None:
        processed = _load_processed_dates(s3_client, gold_bucket)
        if day_str in processed:
            logger.info("process_day_already_processed", day=day_str)
            return 0

    # Step 1: Read Silver trades.
    trades = _read_silver_trades_for_day(dt, platform=platform, catalog=catalog)

    if not trades:
        logger.info("process_day_no_trades", day=day_str)
        return 0

    # Step 2: Split trades into fills.
    fills: list[Fill] = trades_to_fills(trades, platform=platform)

    logger.info(
        "trades_to_fills_done",
        day=day_str,
        trades=len(trades),
        fills=len(fills),
    )

    # Step 3: Load existing position state from ClickHouse.
    positions = read_position_states(clickhouse_client=clickhouse_client)

    logger.info(
        "position_state_loaded",
        day=day_str,
        existing_positions=len(positions),
    )

    # Step 4: Process fills through accounting engine.
    writer, positions = build_ledger_for_day(fills, positions)

    positions_updated, realized_pnl_total = _compute_summary(writer, positions)

    logger.info(
        "accounting_done",
        day=day_str,
        ledger_rows=writer.count,
        positions_updated=positions_updated,
        realized_pnl_total=round(realized_pnl_total, 2),
    )

    if dry_run:
        logger.info(
            "dry_run_process_day",
            day=day_str,
            fills=writer.count,
            positions=positions_updated,
            realized_pnl=round(realized_pnl_total, 2),
        )
        return writer.count

    # Step 5: Write ledger to S3 Gold + ClickHouse.
    ledger_rows = writer.flush(
        gold_bucket=gold_bucket,
        day=day_str,
        s3_client=s3_client,
        clickhouse_client=clickhouse_client,
    )

    # Step 6: Update position state in ClickHouse.
    state_rows = write_position_states(
        positions,
        clickhouse_client=clickhouse_client,
    )

    logger.info(
        "process_day_written",
        day=day_str,
        ledger_rows=ledger_rows,
        position_state_rows=state_rows,
    )

    # Step 7: Record in state store.
    if gold_bucket and s3_client is not None:
        _mark_processed(
            s3_client,
            gold_bucket,
            day_str,
            fills_processed=ledger_rows,
            positions_updated=positions_updated,
            realized_pnl_total=realized_pnl_total,
        )

    logger.info(
        "process_day_complete",
        day=day_str,
        fills=ledger_rows,
        positions=positions_updated,
        realized_pnl=round(realized_pnl_total, 2),
    )

    return ledger_rows


def process_date_range(
    *,
    start_date: date,
    end_date: date,
    platform: str = "polymarket",
    gold_bucket: str | None = None,
    s3_client: Any | None = None,
    clickhouse_client: Any | None = None,
    catalog: Any | None = None,
    dry_run: bool = False,
    force_reprocess: bool = False,
) -> dict[str, int]:
    """Process Silver trades for a date range through the accounting pipeline.

    Processes each day sequentially (order matters for cumulative position state).

    Args:
        start_date: First date to process (inclusive).
        end_date: Last date to process (inclusive).
        platform: Platform identifier (default ``"polymarket"``).
        gold_bucket: S3 bucket for Gold output.
        s3_client: Optional boto3 S3 client.
        clickhouse_client: Optional ClickHouse client.
        catalog: Optional PyIceberg catalog.
        dry_run: Preview without writing.
        force_reprocess: Reprocess already-processed dates.

    Returns:
        Dict mapping date strings to ledger rows written.
    """
    results: dict[str, int] = {}
    current = start_date
    while current <= end_date:
        rows = process_day(
            dt=current,
            platform=platform,
            gold_bucket=gold_bucket,
            s3_client=s3_client,
            clickhouse_client=clickhouse_client,
            catalog=catalog,
            dry_run=dry_run,
            force_reprocess=force_reprocess,
        )
        results[str(current)] = rows
        current += timedelta(days=1)

    total_fills = sum(results.values())
    days_with_data = sum(1 for v in results.values() if v > 0)
    logger.info(
        "process_date_range_complete",
        start=str(start_date),
        end=str(end_date),
        total_days=len(results),
        days_with_data=days_with_data,
        total_fills=total_fills,
    )

    return results
