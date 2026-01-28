"""Polymarket data ingestion functions."""

import asyncio
from typing import Any

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


async def ingest_markets(
    dt: str,
    *,
    bucket: str | None = None,
    include_closed: bool = True,
) -> str:
    """Ingest Polymarket markets snapshot for a given date.

    Fetches all markets from the Polymarket Gamma API and stores them
    in the Bronze layer as gzip-compressed JSONL files.

    Args:
        dt: Data partition date in YYYY-MM-DD format.
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).
        include_closed: Whether to include closed/resolved markets.

    Returns:
        The run_id for this ingestion run.
    """
    settings = get_settings()
    bucket = bucket or settings.bronze_bucket
    logger: structlog.stdlib.BoundLogger = get_logger(__name__)

    # Create run context for tracking
    run_ctx = RunContext(platform="polymarket", entity="markets")
    run_ctx.bind_to_logger(dt=dt)
    run_ctx.log_start(logger)

    logger.info(
        "Starting Polymarket markets ingestion",
        dt=dt,
        bucket=bucket,
        include_closed=include_closed,
    )

    # Fetch markets from API
    async with PolymarketClient() as client:
        markets = await client.fetch_all_markets(include_closed=include_closed)

    logger.info("Fetched markets from API", record_count=len(markets))

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
            cursor=None,  # Offset pagination doesn't use cursors
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
) -> str:
    """Ingest Polymarket events snapshot for a given date.

    Fetches all events from the Polymarket Gamma API and stores them
    in the Bronze layer as gzip-compressed JSONL files.

    Args:
        dt: Data partition date in YYYY-MM-DD format.
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).
        include_closed: Whether to include closed/resolved events.

    Returns:
        The run_id for this ingestion run.
    """
    settings = get_settings()
    bucket = bucket or settings.bronze_bucket
    logger: structlog.stdlib.BoundLogger = get_logger(__name__)

    # Create run context for tracking
    run_ctx = RunContext(platform="polymarket", entity="events")
    run_ctx.bind_to_logger(dt=dt)
    run_ctx.log_start(logger)

    logger.info(
        "Starting Polymarket events ingestion",
        dt=dt,
        bucket=bucket,
        include_closed=include_closed,
    )

    # Fetch events from API
    async with PolymarketClient() as client:
        events = await client.fetch_all_events(include_closed=include_closed)

    logger.info("Fetched events from API", record_count=len(events))

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
            cursor=None,  # Offset pagination doesn't use cursors
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
) -> str:
    """Synchronous wrapper for ingest_events.

    This is a convenience function for CLI usage.

    Args:
        dt: Data partition date in YYYY-MM-DD format.
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).
        include_closed: Whether to include closed/resolved events.

    Returns:
        The run_id for this ingestion run.
    """
    return asyncio.run(
        ingest_events(
            dt,
            bucket=bucket,
            include_closed=include_closed,
        )
    )


def run_ingest_markets(
    dt: str,
    *,
    bucket: str | None = None,
    include_closed: bool = True,
) -> str:
    """Synchronous wrapper for ingest_markets.

    This is a convenience function for CLI usage.

    Args:
        dt: Data partition date in YYYY-MM-DD format.
        bucket: S3 bucket name (defaults to BRONZE_BUCKET from settings).
        include_closed: Whether to include closed/resolved markets.

    Returns:
        The run_id for this ingestion run.
    """
    return asyncio.run(
        ingest_markets(
            dt,
            bucket=bucket,
            include_closed=include_closed,
        )
    )
