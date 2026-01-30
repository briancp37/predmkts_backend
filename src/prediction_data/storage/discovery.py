"""S3 data discovery utilities for finding latest timestamps and dates."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from prediction_data.storage.s3 import S3Client

logger = structlog.stdlib.get_logger(__name__)

# Regex to extract date from dt= partition keys
_DT_PATTERN = re.compile(r"/dt=(\d{4}-\d{2}-\d{2})/")


async def find_latest_timestamp(
    s3_client: S3Client,
    platform: str,
    entity: str,
) -> int | None:
    """Find the latest record timestamp for a given platform/entity in S3.

    Scans S3 prefixes to find the most recent date partition, then reads the
    manifest from the latest run. If the manifest has a ``latest_timestamp``
    field in its source metadata, that value is returned. Otherwise, the latest
    data file is downloaded and scanned for the maximum ``timestamp`` field.

    Args:
        s3_client: Initialised S3Client.
        platform: Platform identifier (e.g. ``"polymarket"``).
        entity: Entity identifier (e.g. ``"order_filled"``).

    Returns:
        The maximum Unix-epoch-seconds timestamp found, or ``None`` if no data exists.
    """
    prefix = f"bronze/{platform}/{entity}/"
    all_keys = await s3_client.list_keys(prefix)

    if not all_keys:
        logger.info("No data found", platform=platform, entity=entity)
        return None

    # Extract unique dates from keys
    dates: set[str] = set()
    for key in all_keys:
        m = _DT_PATTERN.search(key)
        if m:
            dates.add(m.group(1))

    if not dates:
        logger.info("No date partitions found", platform=platform, entity=entity)
        return None

    latest_date = max(dates)
    logger.info("Found latest date partition", platform=platform, entity=entity, latest_date=latest_date)

    # Find all manifests for the latest date
    date_prefix = f"bronze/{platform}/{entity}/dt={latest_date}/"
    date_keys = [k for k in all_keys if k.startswith(date_prefix)]
    manifest_keys = [k for k in date_keys if k.endswith("manifest.json")]

    if not manifest_keys:
        logger.warning("No manifests in latest date partition", latest_date=latest_date)
        return None

    # Find the manifest with the latest generated_at (latest run)
    latest_manifest = None
    latest_manifest_key = None
    for mk in manifest_keys:
        manifest = await s3_client.download_manifest(mk)
        if latest_manifest is None or manifest.generated_at > latest_manifest.generated_at:
            latest_manifest = manifest
            latest_manifest_key = mk

    assert latest_manifest is not None
    assert latest_manifest_key is not None

    # Check if source metadata has latest_timestamp
    source_dict = latest_manifest.source.model_dump()
    if "latest_timestamp" in source_dict and source_dict["latest_timestamp"] is not None:
        ts = int(source_dict["latest_timestamp"])
        logger.info("Found latest_timestamp in manifest", timestamp=ts)
        return ts

    # Fallback: download data file and scan for max timestamp
    data_keys = [k for k in date_keys if k.endswith(".jsonl.gz") and not k.endswith("manifest.json")]
    if not data_keys:
        logger.warning("No data files in latest run", manifest_key=latest_manifest_key)
        return None

    # Scan only files from the latest run
    run_prefix = latest_manifest_key.rsplit("manifest.json", 1)[0]
    run_data_keys = [k for k in data_keys if k.startswith(run_prefix)]
    if not run_data_keys:
        run_data_keys = data_keys  # fallback to all data files in the date

    max_ts: int | None = None
    for dk in run_data_keys:
        records = await s3_client.download_jsonl(dk)
        for record in records:
            ts_val = record.get("timestamp")
            if ts_val is not None:
                ts_int = int(ts_val)
                if max_ts is None or ts_int > max_ts:
                    max_ts = ts_int

    if max_ts is not None:
        logger.info("Found latest timestamp via data scan", timestamp=max_ts)
    else:
        logger.warning("No timestamp field found in data files")

    return max_ts


async def find_latest_date(
    s3_client: S3Client,
    platform: str,
    entity: str,
) -> str | None:
    """Find the latest date partition for a given platform/entity in S3.

    Args:
        s3_client: Initialised S3Client.
        platform: Platform identifier.
        entity: Entity identifier.

    Returns:
        The latest date string (YYYY-MM-DD), or ``None`` if no data exists.
    """
    prefix = f"bronze/{platform}/{entity}/"
    all_keys = await s3_client.list_keys(prefix)

    if not all_keys:
        return None

    dates: set[str] = set()
    for key in all_keys:
        m = _DT_PATTERN.search(key)
        if m:
            dates.add(m.group(1))

    return max(dates) if dates else None
