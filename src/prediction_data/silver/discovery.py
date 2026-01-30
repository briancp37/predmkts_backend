"""Scan S3 for Bronze manifests to drive Silver processing.

Provides manifest discovery for the Silver processing pipeline. Scans the
Bronze layer S3 layout to find manifests matching platform, entity, and date
range filters, returning parsed and validated Manifest objects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from prediction_data.storage.manifest import Manifest

if TYPE_CHECKING:
    from prediction_data.storage.s3 import S3Client

logger = structlog.stdlib.get_logger(__name__)

# Regex to extract date from dt= partition keys
_DT_PATTERN = re.compile(r"/dt=(\d{4}-\d{2}-\d{2})/")


@dataclass(frozen=True)
class DiscoveredManifest:
    """A Bronze manifest discovered via S3 scanning.

    Attributes:
        manifest: Parsed and validated Manifest object.
        s3_key: The S3 key where the manifest was found.
    """

    manifest: Manifest
    s3_key: str

    @property
    def run_id(self) -> str:
        return self.manifest.run_id

    @property
    def dt(self) -> str:
        return self.manifest.dt

    @property
    def row_count(self) -> int:
        return self.manifest.row_count

    @property
    def platform(self) -> str:
        return self.manifest.platform

    @property
    def entity(self) -> str:
        return self.manifest.entity


async def discover_manifests(
    s3_client: S3Client,
    platform: str,
    entity: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[DiscoveredManifest]:
    """Scan S3 for Bronze manifests matching the given filters.

    Discovers manifests under the Bronze S3 layout:
    ``bronze/{platform}/{entity}/dt={date}/run_id={uuid}/_manifest.json``

    Args:
        s3_client: Initialised S3Client bound to the Bronze bucket.
        platform: Platform identifier (e.g. ``"polymarket"``).
        entity: Entity identifier (e.g. ``"trades"``, ``"markets"``).
        start_date: Optional inclusive start date (YYYY-MM-DD). If None, no lower bound.
        end_date: Optional inclusive end date (YYYY-MM-DD). If None, no upper bound.

    Returns:
        List of discovered manifests sorted by date ascending, then by
        ``generated_at`` ascending within each date.
    """
    prefix = f"bronze/{platform}/{entity}/"

    # List date partitions using delimiter trick
    date_prefixes = await s3_client.list_prefixes(prefix)

    if not date_prefixes:
        logger.info(
            "No date partitions found",
            platform=platform,
            entity=entity,
        )
        return []

    # Extract and filter dates
    dates: list[str] = []
    for dp in date_prefixes:
        m = _DT_PATTERN.search(dp)
        if m:
            dt_str = m.group(1)
            if start_date and dt_str < start_date:
                continue
            if end_date and dt_str > end_date:
                continue
            dates.append(dt_str)

    if not dates:
        logger.info(
            "No date partitions in range",
            platform=platform,
            entity=entity,
            start_date=start_date,
            end_date=end_date,
        )
        return []

    dates.sort()

    logger.info(
        "Found date partitions",
        platform=platform,
        entity=entity,
        count=len(dates),
        first=dates[0],
        last=dates[-1],
    )

    # Scan each date partition for manifest files
    results: list[DiscoveredManifest] = []
    errors = 0

    for dt_str in dates:
        date_prefix = f"bronze/{platform}/{entity}/dt={dt_str}/"
        keys = await s3_client.list_keys(date_prefix)
        manifest_keys = [k for k in keys if k.endswith("manifest.json")]

        for mk in manifest_keys:
            try:
                manifest = await s3_client.download_manifest(mk)
                results.append(DiscoveredManifest(manifest=manifest, s3_key=mk))
            except Exception:
                logger.warning(
                    "Failed to parse manifest",
                    s3_key=mk,
                    exc_info=True,
                )
                errors += 1

    # Sort by date, then by generated_at within date
    results.sort(key=lambda d: (d.dt, d.manifest.generated_at))

    logger.info(
        "Manifest discovery complete",
        platform=platform,
        entity=entity,
        manifests_found=len(results),
        parse_errors=errors,
        date_range=f"{dates[0]}..{dates[-1]}" if dates else "none",
    )

    return results
