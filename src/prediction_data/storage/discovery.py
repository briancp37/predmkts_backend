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


async def _find_latest_date_partition(
    s3_client: S3Client,
    platform: str,
    entity: str,
) -> str | None:
    """Return the latest ``dt=YYYY-MM-DD`` date string using delimiter listing.

    Uses ``list_prefixes`` (S3 delimiter trick) so only partition names are
    returned — no enumeration of individual keys.
    """
    prefix = f"bronze/{platform}/{entity}/"
    prefixes = await s3_client.list_prefixes(prefix)

    if not prefixes:
        logger.info("No date partitions found", platform=platform, entity=entity)
        return None

    dates: list[str] = []
    for p in prefixes:
        m = _DT_PATTERN.search(p)
        if m:
            dates.append(m.group(1))

    if not dates:
        return None

    latest = max(dates)
    logger.info("Found latest date partition", platform=platform, entity=entity, latest_date=latest)
    return latest


async def find_latest_timestamp(
    s3_client: S3Client,
    platform: str,
    entity: str,
) -> int | None:
    """Find the latest record timestamp for a given platform/entity in S3.

    Uses ``list_prefixes`` to quickly locate the latest date partition, then
    only lists keys within that single partition to read manifests/data.

    Args:
        s3_client: Initialised S3Client.
        platform: Platform identifier (e.g. ``"polymarket"``).
        entity: Entity identifier (e.g. ``"order_filled"``).

    Returns:
        The maximum Unix-epoch-seconds timestamp found, or ``None`` if no data exists.
    """
    latest_date = await _find_latest_date_partition(s3_client, platform, entity)
    if latest_date is None:
        return None

    # List keys only within the latest date partition
    date_prefix = f"bronze/{platform}/{entity}/dt={latest_date}/"
    date_keys = await s3_client.list_keys(date_prefix)
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
    return await _find_latest_date_partition(s3_client, platform, entity)
