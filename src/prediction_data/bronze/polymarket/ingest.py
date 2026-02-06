"""Polymarket data ingestion functions."""

import asyncio
import calendar
from datetime import UTC, datetime
from typing import Literal

import structlog

from prediction_data.bronze.polymarket.client import (
    DATA_API_BASE_URL,
    GAMMA_API_BASE_URL,
    PolymarketClient,
)
from prediction_data.core.config import get_settings
from prediction_data.core.logging import get_logger
from prediction_data.core.run import RunContext
from prediction_data.storage.manifest import create_manifest
from prediction_data.storage.s3 import S3Client


async def ingest_trades_clob(
    dt: str,
    *,
    bucket: str | None = None,
) -> str:
    """Ingest Polymarket trades for a given date via CLOB API.

    Uses the CLOB API with L2 auth and cursor-based pagination,
    which has no offset limit unlike the Data API.

    Args:
        dt: Data partition date in YYYY-MM-DD format.
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).

    Returns:
        The run_id for this ingestion run.
    """
    import calendar
    from datetime import date as date_type
    from datetime import datetime

    from prediction_data.bronze.polymarket.clob import (
        CLOB_API_BASE_URL,
        PolymarketClobClient,
        load_clob_credentials,
    )

    settings = get_settings()
    bucket = bucket or settings.bronze_bucket
    logger: structlog.stdlib.BoundLogger = get_logger(__name__)

    # Create run context for tracking
    run_ctx = RunContext(platform="polymarket", entity="trades")
    run_ctx.bind_to_logger(dt=dt)
    run_ctx.log_start(logger)

    # Compute day boundaries as Unix timestamps
    dt_date = date_type.fromisoformat(dt)
    start_ts = calendar.timegm(
        datetime(dt_date.year, dt_date.month, dt_date.day, 0, 0, 0).timetuple()
    )
    end_ts = calendar.timegm(
        datetime(dt_date.year, dt_date.month, dt_date.day, 23, 59, 59).timetuple()
    )

    logger.info(
        "Starting Polymarket CLOB trades ingestion",
        dt=dt,
        bucket=bucket,
        after=start_ts,
        before=end_ts,
    )

    # Fetch trades from CLOB API
    credentials = load_clob_credentials()
    async with PolymarketClobClient(credentials) as client:
        trades = await client.fetch_all_trades(after=start_ts, before=end_ts)

    logger.info("Fetched CLOB trades from API", record_count=len(trades))

    # Upload to S3
    async with S3Client(bucket=bucket) as s3_client:
        data_key, row_count = await s3_client.upload_jsonl(
            records=trades,
            platform="polymarket",
            entity="trades",
            dt=dt,
            run_id=run_ctx.run_id,
        )

        logger.info(
            "Uploaded CLOB trades data to S3",
            key=data_key,
            row_count=row_count,
        )

        manifest = create_manifest(
            run_id=run_ctx.run_id,
            platform="polymarket",
            entity="trades",
            dt=dt,
            bucket=bucket,
            key=data_key,
            row_count=row_count,
            api_base_url=CLOB_API_BASE_URL,
            pagination="cursor",
            cursor=None,
        )

        manifest_key = await s3_client.upload_manifest(manifest)
        logger.info("Uploaded manifest to S3", key=manifest_key)

    # Mark run complete
    run_ctx.mark_complete()
    run_ctx.log_end(logger)

    return run_ctx.run_id


def run_ingest_trades_clob(
    dt: str,
    *,
    bucket: str | None = None,
) -> str:
    """Synchronous wrapper for ingest_trades_clob.

    Args:
        dt: Data partition date in YYYY-MM-DD format.
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).

    Returns:
        The run_id for this ingestion run.
    """
    return asyncio.run(ingest_trades_clob(dt, bucket=bucket))


def _iso_to_epoch(iso_str: str) -> int:
    """Convert ISO 8601 datetime string to Unix epoch seconds."""
    # Handle Z suffix and parse
    cleaned = iso_str.replace("Z", "+00:00")
    dt_obj = datetime.fromisoformat(cleaned)
    return calendar.timegm(dt_obj.utctimetuple())


def _epoch_to_iso(epoch: int) -> str:
    """Convert Unix epoch seconds to ISO 8601 datetime string."""
    return datetime.fromtimestamp(epoch, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def ingest_markets(
    dt: str,
    *,
    bucket: str | None = None,
    include_closed: bool = True,
    since_updated_at: str | None = None,
) -> str:
    """Ingest Polymarket markets for a given date.

    When ``since_updated_at`` is provided, uses incremental mode — fetches only
    markets updated after the cutoff and stores as a delta partition. Otherwise
    fetches a full snapshot.

    Args:
        dt: Data partition date in YYYY-MM-DD format.
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).
        include_closed: Whether to include closed/resolved markets.
        since_updated_at: ISO 8601 cutoff for incremental fetch. When provided,
            only records with updatedAt > this value are fetched.

    Returns:
        The run_id for this ingestion run.
    """
    settings = get_settings()
    bucket = bucket or settings.bronze_bucket
    logger: structlog.stdlib.BoundLogger = get_logger(__name__)

    incremental = since_updated_at is not None
    snapshot_type: Literal["snapshot", "delta"] = "delta" if incremental else "snapshot"

    # Create run context for tracking
    run_ctx = RunContext(platform="polymarket", entity="markets")
    run_ctx.bind_to_logger(dt=dt)
    run_ctx.log_start(logger)

    logger.info(
        "Starting Polymarket markets ingestion",
        dt=dt,
        bucket=bucket,
        include_closed=include_closed,
        incremental=incremental,
        since_updated_at=since_updated_at,
    )

    # Fetch markets from API
    max_updated_at: str | None = None
    async with PolymarketClient() as client:
        if incremental:
            assert since_updated_at is not None
            markets, max_updated_at = await client.fetch_markets_incremental(
                since_updated_at=since_updated_at,
                include_closed=include_closed,
            )
        else:
            markets = await client.fetch_all_markets(include_closed=include_closed)
            # Extract max updatedAt from full snapshot for cursor tracking
            # so subsequent catchup runs can use incremental mode.
            if markets:
                updated_values = [m.get("updatedAt", "") for m in markets]
                max_val = max((v for v in updated_values if v), default=None)
                if max_val:
                    max_updated_at = max_val

    logger.info(
        "Fetched markets from API",
        record_count=len(markets),
        incremental=incremental,
        max_updated_at=max_updated_at,
    )

    # Compute latest_timestamp for manifest (epoch seconds)
    latest_timestamp: int | None = None
    if max_updated_at is not None and max_updated_at != since_updated_at:
        latest_timestamp = _iso_to_epoch(max_updated_at)
    elif since_updated_at is not None and not markets:
        # Zero-change incremental: preserve the original cursor
        latest_timestamp = _iso_to_epoch(since_updated_at)

    # Upload to S3
    async with S3Client(bucket=bucket) as s3_client:
        # Upload JSONL data
        data_key, row_count = await s3_client.upload_jsonl(
            records=markets,
            platform="polymarket",
            entity="markets",
            dt=dt,
            run_id=run_ctx.run_id,
        )

        logger.info(
            "Uploaded markets data to S3",
            key=data_key,
            row_count=row_count,
        )

        # Create and upload manifest
        manifest = create_manifest(
            run_id=run_ctx.run_id,
            platform="polymarket",
            entity="markets",
            dt=dt,
            bucket=bucket,
            key=data_key,
            row_count=row_count,
            api_base_url=GAMMA_API_BASE_URL,
            pagination="offset",
            cursor=None,
            snapshot_type=snapshot_type,
            latest_timestamp=latest_timestamp,
        )

        manifest_key = await s3_client.upload_manifest(manifest)
        logger.info("Uploaded manifest to S3", key=manifest_key)

    # Mark run complete
    run_ctx.mark_complete()
    run_ctx.log_end(logger)

    return run_ctx.run_id


async def ingest_events(
    dt: str,
    *,
    bucket: str | None = None,
    include_closed: bool = True,
    since_updated_at: str | None = None,
) -> str:
    """Ingest Polymarket events for a given date.

    When ``since_updated_at`` is provided, uses incremental mode — fetches only
    events updated after the cutoff and stores as a delta partition. Otherwise
    fetches a full snapshot.

    Args:
        dt: Data partition date in YYYY-MM-DD format.
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).
        include_closed: Whether to include closed/resolved events.
        since_updated_at: ISO 8601 cutoff for incremental fetch. When provided,
            only records with updatedAt > this value are fetched.

    Returns:
        The run_id for this ingestion run.
    """
    settings = get_settings()
    bucket = bucket or settings.bronze_bucket
    logger: structlog.stdlib.BoundLogger = get_logger(__name__)

    incremental = since_updated_at is not None
    snapshot_type: Literal["snapshot", "delta"] = "delta" if incremental else "snapshot"

    # Create run context for tracking
    run_ctx = RunContext(platform="polymarket", entity="events")
    run_ctx.bind_to_logger(dt=dt)
    run_ctx.log_start(logger)

    logger.info(
        "Starting Polymarket events ingestion",
        dt=dt,
        bucket=bucket,
        include_closed=include_closed,
        incremental=incremental,
        since_updated_at=since_updated_at,
    )

    # Fetch events from API
    max_updated_at: str | None = None
    async with PolymarketClient() as client:
        if incremental:
            assert since_updated_at is not None
            events, max_updated_at = await client.fetch_events_incremental(
                since_updated_at=since_updated_at,
                include_closed=include_closed,
            )
        else:
            events = await client.fetch_all_events(include_closed=include_closed)
            # Extract max updatedAt from full snapshot for cursor tracking
            # so subsequent catchup runs can use incremental mode.
            if events:
                updated_values = [e.get("updatedAt", "") for e in events]
                max_val = max((v for v in updated_values if v), default=None)
                if max_val:
                    max_updated_at = max_val

    logger.info(
        "Fetched events from API",
        record_count=len(events),
        incremental=incremental,
        max_updated_at=max_updated_at,
    )

    # Compute latest_timestamp for manifest (epoch seconds)
    latest_timestamp: int | None = None
    if max_updated_at is not None and max_updated_at != since_updated_at:
        latest_timestamp = _iso_to_epoch(max_updated_at)
    elif since_updated_at is not None and not events:
        # Zero-change incremental: preserve the original cursor
        latest_timestamp = _iso_to_epoch(since_updated_at)

    # Upload to S3
    async with S3Client(bucket=bucket) as s3_client:
        # Upload JSONL data
        data_key, row_count = await s3_client.upload_jsonl(
            records=events,
            platform="polymarket",
            entity="events",
            dt=dt,
            run_id=run_ctx.run_id,
        )

        logger.info(
            "Uploaded events data to S3",
            key=data_key,
            row_count=row_count,
        )

        # Create and upload manifest
        manifest = create_manifest(
            run_id=run_ctx.run_id,
            platform="polymarket",
            entity="events",
            dt=dt,
            bucket=bucket,
            key=data_key,
            row_count=row_count,
            api_base_url=GAMMA_API_BASE_URL,
            pagination="offset",
            cursor=None,
            snapshot_type=snapshot_type,
            latest_timestamp=latest_timestamp,
        )

        manifest_key = await s3_client.upload_manifest(manifest)
        logger.info("Uploaded manifest to S3", key=manifest_key)

    # Mark run complete
    run_ctx.mark_complete()
    run_ctx.log_end(logger)

    return run_ctx.run_id


def run_ingest_events(
    dt: str,
    *,
    bucket: str | None = None,
    include_closed: bool = True,
    since_updated_at: str | None = None,
) -> str:
    """Synchronous wrapper for ingest_events.

    This is a convenience function for CLI usage.

    Args:
        dt: Data partition date in YYYY-MM-DD format.
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).
        include_closed: Whether to include closed/resolved events.
        since_updated_at: ISO 8601 cutoff for incremental fetch.

    Returns:
        The run_id for this ingestion run.
    """
    return asyncio.run(
        ingest_events(
            dt,
            bucket=bucket,
            include_closed=include_closed,
            since_updated_at=since_updated_at,
        )
    )


async def ingest_order_filled(
    dt: str,
    *,
    bucket: str | None = None,
    since_timestamp: int | None = None,
) -> str:
    """Ingest Polymarket OrderFilledEvents for a single date via Goldsky subgraph.

    Fetches OrderFilledEvents from the Goldsky orderbook subgraph for a specific
    date and stores them in the Bronze layer as gzip-compressed JSONL files.

    This function is for single-date ingestion only. For incremental catchup
    that spans multiple dates, use ``ingest_order_filled_incremental`` instead.

    Args:
        dt: Data partition date in YYYY-MM-DD format. Events are filtered to
            only include those with timestamps falling on this date.
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).
        since_timestamp: If provided, fetch only records with
            ``timestamp_gte=since_timestamp`` instead of the day start.
            Records are still filtered to only include those on ``dt``.

    Returns:
        The run_id for this ingestion run.
    """
    import calendar
    from datetime import date as date_type
    from datetime import datetime

    from prediction_data.bronze.polymarket.goldsky import (
        GOLDSKY_API_BASE_URL,
        GoldskyClient,
    )

    settings = get_settings()
    bucket = bucket or settings.bronze_bucket
    logger: structlog.stdlib.BoundLogger = get_logger(__name__)

    # Create run context for tracking
    run_ctx = RunContext(platform="polymarket", entity="order_filled")
    run_ctx.bind_to_logger(dt=dt)
    run_ctx.log_start(logger)

    # Compute day boundaries as Unix timestamps
    dt_date = date_type.fromisoformat(dt)
    day_start_ts = calendar.timegm(
        datetime(dt_date.year, dt_date.month, dt_date.day, 0, 0, 0).timetuple()
    )
    day_end_ts = calendar.timegm(
        datetime(dt_date.year, dt_date.month, dt_date.day, 23, 59, 59).timetuple()
    )

    # Use since_timestamp if provided, but cap to day boundaries
    if since_timestamp is not None:
        start_ts = max(since_timestamp, day_start_ts)
    else:
        start_ts = day_start_ts
    end_ts = day_end_ts

    logger.info(
        "Starting Polymarket order_filled ingestion",
        dt=dt,
        bucket=bucket,
        timestamp_gte=start_ts,
        timestamp_lte=end_ts,
        incremental=since_timestamp is not None,
    )

    # Fetch and upload OrderFilledEvents in batches to avoid memory exhaustion.
    # After each batch flush, write an intermediate manifest so that if the
    # process dies, the next catchup resumes from the last flushed batch.
    from datetime import timezone as tz

    from prediction_data.storage.manifest import (
        FileReference,
        Manifest,
        Source,
    )

    file_refs: list[FileReference] = []
    total_row_count = 0
    max_ts: int | None = None
    part_number = 0

    async with GoldskyClient() as client, S3Client(bucket=bucket) as s3_client:
        async for batch in client.iter_order_filled_batches(
            timestamp_gte=start_ts, timestamp_lte=end_ts,
        ):
            # Reset S3 client to get fresh connection pool, avoiding staleness
            # issues that can occur during long-running batch operations.
            s3_client.reset_client()

            # Track max timestamp across all batches
            for evt in batch:
                ts_val = evt.get("timestamp")
                if ts_val is not None:
                    ts_int = int(ts_val)
                    if max_ts is None or ts_int > max_ts:
                        max_ts = ts_int

            data_key, row_count = await s3_client.upload_jsonl(
                records=batch,
                platform="polymarket",
                entity="order_filled",
                dt=dt,
                run_id=run_ctx.run_id,
                part_number=part_number,
            )

            file_refs.append(FileReference(bucket=bucket, key=data_key))
            total_row_count += row_count
            part_number += 1

            # Write intermediate manifest after each batch so progress is
            # recoverable if the process is interrupted.
            manifest = Manifest(
                run_id=run_ctx.run_id,
                platform="polymarket",
                entity="order_filled",
                dt=dt,
                generated_at=datetime.now(tz.utc),
                files=list(file_refs),
                row_count=total_row_count,
                source=Source(
                    api_base_url=GOLDSKY_API_BASE_URL,
                    pagination="cursor",
                    cursor=None,
                    latest_timestamp=max_ts,
                ),
            )
            await s3_client.upload_manifest(manifest)

            logger.info(
                "Flushed order_filled batch to S3",
                part=part_number,
                batch_rows=row_count,
                total_rows=total_row_count,
                latest_timestamp=max_ts,
            )

    if total_row_count == 0:
        logger.info("No order_filled events found", dt=dt)
        run_ctx.mark_complete()
        run_ctx.log_end(logger)
        return run_ctx.run_id

    logger.info(
        "Order_filled ingestion complete",
        total_rows=total_row_count,
        parts=part_number,
        latest_timestamp=max_ts,
    )

    # Mark run complete
    run_ctx.mark_complete()
    run_ctx.log_end(logger)

    return run_ctx.run_id


async def ingest_order_filled_incremental(
    *,
    bucket: str | None = None,
    since_timestamp: int,
) -> dict[str, str]:
    """Ingest Polymarket OrderFilledEvents incrementally, partitioned by event date.

    Fetches all OrderFilledEvents from ``since_timestamp`` to now and writes them
    to the appropriate date partitions based on each event's timestamp. This ensures
    events are stored under ``dt=YYYY-MM-DD`` where the date corresponds to when
    the event occurred, not when the ingestion ran.

    Args:
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).
        since_timestamp: Fetch only records with ``timestamp >= since_timestamp``.

    Returns:
        A dict mapping each date partition (YYYY-MM-DD) to its run_id.
    """
    import calendar
    from collections import defaultdict
    from datetime import date as date_type
    from datetime import datetime
    from datetime import timezone as tz
    from uuid import uuid4

    from prediction_data.bronze.polymarket.goldsky import (
        GOLDSKY_API_BASE_URL,
        GoldskyClient,
    )
    from prediction_data.storage.manifest import (
        FileReference,
        Manifest,
        Source,
    )

    settings = get_settings()
    bucket = bucket or settings.bronze_bucket
    logger: structlog.stdlib.BoundLogger = get_logger(__name__)

    end_ts = calendar.timegm(datetime.utcnow().timetuple())

    logger.info(
        "Starting incremental order_filled ingestion",
        bucket=bucket,
        timestamp_gte=since_timestamp,
        timestamp_lte=end_ts,
    )

    # Track state per date partition
    # Each date gets its own run_id, files, and counters
    date_runs: dict[str, str] = {}  # dt -> run_id
    date_files: dict[str, list[FileReference]] = defaultdict(list)
    date_counts: dict[str, int] = defaultdict(int)
    date_max_ts: dict[str, int] = {}
    date_parts: dict[str, int] = defaultdict(int)

    async with GoldskyClient() as client, S3Client(bucket=bucket) as s3_client:
        async for batch in client.iter_order_filled_batches(
            timestamp_gte=since_timestamp, timestamp_lte=end_ts,
        ):
            s3_client.reset_client()

            # Group events by their timestamp date
            events_by_date: dict[str, list[dict]] = defaultdict(list)
            for evt in batch:
                ts_val = evt.get("timestamp")
                if ts_val is not None:
                    ts_int = int(ts_val)
                    evt_date = datetime.fromtimestamp(ts_int, tz=tz.utc).strftime("%Y-%m-%d")
                    events_by_date[evt_date].append(evt)

                    # Track max timestamp per date
                    if evt_date not in date_max_ts or ts_int > date_max_ts[evt_date]:
                        date_max_ts[evt_date] = ts_int

            # Write events for each date to their respective partitions
            for dt_str, events in events_by_date.items():
                # Create run_id for this date if not exists
                if dt_str not in date_runs:
                    date_runs[dt_str] = str(uuid4())

                run_id = date_runs[dt_str]
                part_number = date_parts[dt_str]

                data_key, row_count = await s3_client.upload_jsonl(
                    records=events,
                    platform="polymarket",
                    entity="order_filled",
                    dt=dt_str,
                    run_id=run_id,
                    part_number=part_number,
                )

                date_files[dt_str].append(FileReference(bucket=bucket, key=data_key))
                date_counts[dt_str] += row_count
                date_parts[dt_str] += 1

                # Write manifest for this date
                manifest = Manifest(
                    run_id=run_id,
                    platform="polymarket",
                    entity="order_filled",
                    dt=dt_str,
                    generated_at=datetime.now(tz.utc),
                    files=list(date_files[dt_str]),
                    row_count=date_counts[dt_str],
                    source=Source(
                        api_base_url=GOLDSKY_API_BASE_URL,
                        pagination="cursor",
                        cursor=None,
                        latest_timestamp=date_max_ts.get(dt_str),
                    ),
                )
                await s3_client.upload_manifest(manifest)

            # Log progress
            total_events = sum(len(evts) for evts in events_by_date.values())
            logger.info(
                "Processed order_filled batch",
                batch_size=total_events,
                dates_in_batch=list(events_by_date.keys()),
                total_dates=len(date_runs),
            )

    # Log final summary
    total_all = sum(date_counts.values())
    if total_all == 0:
        logger.info("No order_filled events found in incremental range")
    else:
        logger.info(
            "Incremental order_filled ingestion complete",
            total_rows=total_all,
            dates_processed=len(date_runs),
            date_breakdown={dt: date_counts[dt] for dt in sorted(date_runs.keys())},
        )

    return date_runs


def run_ingest_order_filled(
    dt: str,
    *,
    bucket: str | None = None,
    since_timestamp: int | None = None,
) -> str:
    """Synchronous wrapper for ingest_order_filled.

    Args:
        dt: Data partition date in YYYY-MM-DD format.
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).
        since_timestamp: If provided, fetch only records newer than this timestamp.

    Returns:
        The run_id for this ingestion run.
    """
    return asyncio.run(
        ingest_order_filled(dt, bucket=bucket, since_timestamp=since_timestamp)
    )


def run_ingest_markets(
    dt: str,
    *,
    bucket: str | None = None,
    include_closed: bool = True,
    since_updated_at: str | None = None,
) -> str:
    """Synchronous wrapper for ingest_markets.

    This is a convenience function for CLI usage.

    Args:
        dt: Data partition date in YYYY-MM-DD format.
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).
        include_closed: Whether to include closed/resolved markets.
        since_updated_at: ISO 8601 cutoff for incremental fetch.

    Returns:
        The run_id for this ingestion run.
    """
    return asyncio.run(
        ingest_markets(
            dt,
            bucket=bucket,
            include_closed=include_closed,
            since_updated_at=since_updated_at,
        )
    )
