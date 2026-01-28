"""Kalshi data ingestion functions."""

import asyncio

import structlog

from prediction_data.bronze.kalshi.auth import load_credentials_from_settings
from prediction_data.bronze.kalshi.client import (
    KALSHI_API_BASE_URL,
    KalshiClient,
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
    ticker: str | None = None,
    min_ts: int | None = None,
    max_ts: int | None = None,
) -> str:
    """Ingest Kalshi trades for a given date.

    Fetches all trades from the Kalshi API and stores them
    in the Bronze layer as gzip-compressed JSONL files.

    Args:
        dt: Data partition date in YYYY-MM-DD format.
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).
        ticker: Optional market ticker to filter by.
        min_ts: Optional minimum Unix timestamp to filter trades.
        max_ts: Optional maximum Unix timestamp to filter trades.

    Returns:
        The run_id for this ingestion run.
    """
    settings = get_settings()
    bucket = bucket or settings.bronze_bucket
    logger: structlog.stdlib.BoundLogger = get_logger(__name__)

    # Create run context for tracking
    run_ctx = RunContext(platform="kalshi", entity="trades")
    run_ctx.bind_to_logger(dt=dt)
    run_ctx.log_start(logger)

    logger.info(
        "Starting Kalshi trades ingestion",
        dt=dt,
        bucket=bucket,
        ticker=ticker,
        min_ts=min_ts,
        max_ts=max_ts,
    )

    # Load credentials and fetch trades from API
    credentials = load_credentials_from_settings()
    async with KalshiClient(credentials) as client:
        trades = await client.fetch_all_trades(
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
        )

    logger.info("Fetched trades from API", record_count=len(trades))

    # Upload to S3
    async with S3Client(bucket=bucket) as s3_client:
        # Upload JSONL data
        data_key, row_count = await s3_client.upload_jsonl(
            records=trades,
            platform="kalshi",
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
            platform="kalshi",
            entity="trades",
            dt=dt,
            bucket=bucket,
            key=data_key,
            row_count=row_count,
            api_base_url=KALSHI_API_BASE_URL,
            pagination="cursor",
            cursor=None,  # Final cursor not tracked since we paginate to completion
        )

        manifest_key = await s3_client.upload_manifest(manifest)
        logger.info("Uploaded manifest to S3", key=manifest_key)

    # Mark run complete
    run_ctx.mark_complete()
    run_ctx.log_end(logger)

    return run_ctx.run_id


def run_ingest_trades(
    dt: str,
    *,
    bucket: str | None = None,
    ticker: str | None = None,
    min_ts: int | None = None,
    max_ts: int | None = None,
) -> str:
    """Synchronous wrapper for ingest_trades.

    This is a convenience function for CLI usage.

    Args:
        dt: Data partition date in YYYY-MM-DD format.
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).
        ticker: Optional market ticker to filter by.
        min_ts: Optional minimum Unix timestamp to filter trades.
        max_ts: Optional maximum Unix timestamp to filter trades.

    Returns:
        The run_id for this ingestion run.
    """
    return asyncio.run(
        ingest_trades(
            dt,
            bucket=bucket,
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
        )
    )


async def ingest_markets(
    dt: str,
    *,
    bucket: str | None = None,
    event_ticker: str | None = None,
    series_ticker: str | None = None,
    status: str | None = None,
) -> str:
    """Ingest Kalshi markets snapshot for a given date.

    Fetches all markets from the Kalshi API and stores them
    in the Bronze layer as gzip-compressed JSONL files.

    Args:
        dt: Data partition date in YYYY-MM-DD format.
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).
        event_ticker: Optional event ticker to filter by.
        series_ticker: Optional series ticker to filter by.
        status: Optional market status to filter by (unopened, open, paused, closed, settled).

    Returns:
        The run_id for this ingestion run.
    """
    settings = get_settings()
    bucket = bucket or settings.bronze_bucket
    logger: structlog.stdlib.BoundLogger = get_logger(__name__)

    # Create run context for tracking
    run_ctx = RunContext(platform="kalshi", entity="markets")
    run_ctx.bind_to_logger(dt=dt)
    run_ctx.log_start(logger)

    logger.info(
        "Starting Kalshi markets ingestion",
        dt=dt,
        bucket=bucket,
        event_ticker=event_ticker,
        series_ticker=series_ticker,
        status=status,
    )

    # Load credentials and fetch markets from API
    credentials = load_credentials_from_settings()
    async with KalshiClient(credentials) as client:
        markets = await client.fetch_all_markets(
            event_ticker=event_ticker,
            series_ticker=series_ticker,
            status=status,
        )

    logger.info("Fetched markets from API", record_count=len(markets))

    # Upload to S3
    async with S3Client(bucket=bucket) as s3_client:
        # Upload JSONL data
        data_key, row_count = await s3_client.upload_jsonl(
            records=markets,
            platform="kalshi",
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
            platform="kalshi",
            entity="markets",
            dt=dt,
            bucket=bucket,
            key=data_key,
            row_count=row_count,
            api_base_url=KALSHI_API_BASE_URL,
            pagination="cursor",
            cursor=None,  # Final cursor not tracked since we paginate to completion
        )

        manifest_key = await s3_client.upload_manifest(manifest)
        logger.info("Uploaded manifest to S3", key=manifest_key)

    # Mark run complete
    run_ctx.mark_complete()
    run_ctx.log_end(logger)

    return run_ctx.run_id


def run_ingest_markets(
    dt: str,
    *,
    bucket: str | None = None,
    event_ticker: str | None = None,
    series_ticker: str | None = None,
    status: str | None = None,
) -> str:
    """Synchronous wrapper for ingest_markets.

    This is a convenience function for CLI usage.

    Args:
        dt: Data partition date in YYYY-MM-DD format.
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).
        event_ticker: Optional event ticker to filter by.
        series_ticker: Optional series ticker to filter by.
        status: Optional market status to filter by (unopened, open, paused, closed, settled).

    Returns:
        The run_id for this ingestion run.
    """
    return asyncio.run(
        ingest_markets(
            dt,
            bucket=bucket,
            event_ticker=event_ticker,
            series_ticker=series_ticker,
            status=status,
        )
    )
