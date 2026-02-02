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


async def ingest_trades(
    dt: str,
    *,
    bucket: str | None = None,
    market: str | None = None,
    event_id: str | None = None,
    taker_only: bool = True,
) -> str:
    """Ingest Polymarket trades for a given date.

    Fetches all trades from the Polymarket Data API and stores them
    in the Bronze layer as gzip-compressed JSONL files.

    Args:
        dt: Data partition date in YYYY-MM-DD format.
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).
        market: Optional comma-separated condition IDs to filter by.
        event_id: Optional comma-separated event IDs to filter by.
        taker_only: Whether to only include taker trades (default True).

    Returns:
        The run_id for this ingestion run.

    Raises:
        ValueError: If both market and event_id are specified.
    """
    settings = get_settings()
    bucket = bucket or settings.bronze_bucket
    logger: structlog.stdlib.BoundLogger = get_logger(__name__)

    # Create run context for tracking
    run_ctx = RunContext(platform="polymarket", entity="trades")
    run_ctx.bind_to_logger(dt=dt)
    run_ctx.log_start(logger)

    logger.info(
        "Starting Polymarket trades ingestion",
        dt=dt,
        bucket=bucket,
        market=market,
        event_id=event_id,
        taker_only=taker_only,
    )

    # Fetch trades from API
    async with PolymarketClient() as client:
        trades, was_truncated = await client.fetch_trades(
            market=market,
            event_id=event_id,
            taker_only=taker_only,
        )

    if was_truncated:
        logger.warning(
            "Trades fetch was truncated due to API offset limit",
            total_fetched=len(trades),
        )

    logger.info("Fetched trades from API", record_count=len(trades))

    # Upload to S3
    async with S3Client(bucket=bucket) as s3_client:
        # Upload JSONL data
        data_key, row_count = await s3_client.upload_jsonl(
            records=trades,
            platform="polymarket",
            entity="trades",
            dt=dt,
            run_id=run_ctx.run_id,
        )

        logger.info(
            "Uploaded trades data to S3",
            key=data_key,
            row_count=row_count,
        )

        # Create and upload manifest
        manifest = create_manifest(
            run_id=run_ctx.run_id,
            platform="polymarket",
            entity="trades",
            dt=dt,
            bucket=bucket,
            key=data_key,
            row_count=row_count,
            api_base_url=DATA_API_BASE_URL,
            pagination="offset",
            cursor=None,  # Offset pagination doesn't use cursors
        )

        manifest_key = await s3_client.upload_manifest(manifest)
        logger.info("Uploaded manifest to S3", key=manifest_key)

    # Mark run complete
    run_ctx.mark_complete()
    run_ctx.log_end(logger)

    return run_ctx.run_id


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


def run_ingest_trades(
    dt: str,
    *,
    bucket: str | None = None,
    market: str | None = None,
    event_id: str | None = None,
    taker_only: bool = True,
) -> str:
    """Synchronous wrapper for ingest_trades.

    This is a convenience function for CLI usage.

    Args:
        dt: Data partition date in YYYY-MM-DD format.
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).
        market: Optional comma-separated condition IDs to filter by.
        event_id: Optional comma-separated event IDs to filter by.
        taker_only: Whether to only include taker trades (default True).

    Returns:
        The run_id for this ingestion run.
    """
    return asyncio.run(
        ingest_trades(
            dt,
            bucket=bucket,
            market=market,
            event_id=event_id,
            taker_only=taker_only,
        )
    )


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
    """Ingest Polymarket OrderFilledEvents for a given date via Goldsky subgraph.

    Fetches all OrderFilledEvents from the Goldsky orderbook subgraph
    and stores them in the Bronze layer as gzip-compressed JSONL files.

    When ``since_timestamp`` is provided, only records newer than that timestamp
    are fetched (incremental mode).  Otherwise the full day is fetched.

    Args:
        dt: Data partition date in YYYY-MM-DD format.
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).
        since_timestamp: If provided, fetch only records with
            ``timestamp_gte=since_timestamp`` instead of using day boundaries.

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

    if since_timestamp is not None:
        # Incremental mode: fetch from since_timestamp to now
        start_ts = since_timestamp
        end_ts = calendar.timegm(datetime.utcnow().timetuple())
    else:
        # Full-day mode: compute day boundaries as Unix timestamps
        dt_date = date_type.fromisoformat(dt)
        start_ts = calendar.timegm(
            datetime(dt_date.year, dt_date.month, dt_date.day, 0, 0, 0).timetuple()
        )
        end_ts = calendar.timegm(
            datetime(dt_date.year, dt_date.month, dt_date.day, 23, 59, 59).timetuple()
        )

    logger.info(
        "Starting Polymarket order_filled ingestion",
        dt=dt,
        bucket=bucket,
        timestamp_gte=start_ts,
        timestamp_lte=end_ts,
        incremental=since_timestamp is not None,
    )

    # Fetch OrderFilledEvents from Goldsky subgraph
    async with GoldskyClient() as client:
        events = await client.fetch_all_order_filled_events(
            timestamp_gte=start_ts, timestamp_lte=end_ts,
        )

    logger.info("Fetched order_filled events from Goldsky", record_count=len(events))

    # Compute latest_timestamp from fetched records
    max_ts: int | None = None
    for evt in events:
        ts_val = evt.get("timestamp")
        if ts_val is not None:
            ts_int = int(ts_val)
            if max_ts is None or ts_int > max_ts:
                max_ts = ts_int

    # Upload to S3
    async with S3Client(bucket=bucket) as s3_client:
        data_key, row_count = await s3_client.upload_jsonl(
            records=events,
            platform="polymarket",
            entity="order_filled",
            dt=dt,
            run_id=run_ctx.run_id,
        )

        logger.info(
            "Uploaded order_filled data to S3",
            key=data_key,
            row_count=row_count,
        )

        manifest = create_manifest(
            run_id=run_ctx.run_id,
            platform="polymarket",
            entity="order_filled",
            dt=dt,
            bucket=bucket,
            key=data_key,
            row_count=row_count,
            api_base_url=GOLDSKY_API_BASE_URL,
            pagination="cursor",
            cursor=None,
            latest_timestamp=max_ts,
        )

        manifest_key = await s3_client.upload_manifest(manifest)
        logger.info("Uploaded manifest to S3", key=manifest_key)

    # Mark run complete
    run_ctx.mark_complete()
    run_ctx.log_end(logger)

    return run_ctx.run_id


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
