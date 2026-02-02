"""Iceberg table maintenance operations for Silver layer.

Provides compaction to merge small data files into larger ones,
and snapshot expiration to control metadata size.
"""

from __future__ import annotations

import dataclasses
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pyarrow as pa  # type: ignore[import-untyped]

from prediction_data.core.logging import get_logger
from prediction_data.silver.tables import SILVER_TABLES

if TYPE_CHECKING:
    from pyiceberg.catalog import Catalog
    from pyiceberg.table import Table

logger = get_logger(__name__)

# Compaction thresholds
SMALL_FILE_THRESHOLD_BYTES = 64 * 1024 * 1024  # 64 MB
MIN_FILES_FOR_COMPACTION = 50
TARGET_FILE_SIZE_BYTES = 256 * 1024 * 1024  # 256 MB


class MaintenanceError(Exception):
    """Raised when a maintenance operation fails."""


@dataclasses.dataclass(slots=True)
class CompactionResult:
    """Metadata returned after a compaction operation."""

    namespace: str
    table_name: str
    partition: str | None
    files_before: int
    files_after: int
    bytes_before: int
    bytes_after: int
    duration_seconds: float
    skipped: bool = False


def _load_table(catalog: Catalog, namespace: str, table_name: str) -> Table:
    """Load an Iceberg table from the catalog."""
    try:
        return catalog.load_table((namespace, table_name))
    except Exception as exc:
        msg = f"Table {namespace}.{table_name} not found in catalog"
        raise MaintenanceError(msg) from exc


def _get_partition_file_stats(
    table: Table,
) -> dict[str, list[tuple[str, int]]]:
    """Get file paths and sizes grouped by partition value.

    Returns:
        Dict mapping partition value string to list of (file_path, file_size_bytes).
    """
    files_table = table.inspect.data_files()

    partitions: dict[str, list[tuple[str, int]]] = {}

    partition_col = "partition" if "partition" in files_table.column_names else None
    file_path_col = "file_path"
    file_size_col = "file_size_in_bytes"

    if file_path_col not in files_table.column_names:
        return partitions

    paths = files_table.column(file_path_col).to_pylist()
    sizes = files_table.column(file_size_col).to_pylist()

    if partition_col:
        partition_values = files_table.column(partition_col).to_pylist()
    else:
        partition_values = ["__unpartitioned__"] * len(paths)

    for part_val, path, size in zip(partition_values, paths, sizes, strict=True):
        key = str(part_val) if part_val is not None else "__null__"
        partitions.setdefault(key, []).append((path, size))

    return partitions


def _needs_compaction(files: list[tuple[str, int]]) -> bool:
    """Check if a partition needs compaction based on file count and sizes."""
    if len(files) < MIN_FILES_FOR_COMPACTION:
        return False
    small_files = [f for f in files if f[1] < SMALL_FILE_THRESHOLD_BYTES]
    return len(small_files) >= MIN_FILES_FOR_COMPACTION


def compact_table(
    catalog: Catalog,
    namespace: str,
    table_name: str,
    *,
    partition: str | None = None,
    dry_run: bool = False,
) -> list[CompactionResult]:
    """Compact small files in an Iceberg table.

    Identifies partitions with excessive small files and rewrites them
    into larger files using dynamic partition overwrite.

    Args:
        catalog: PyIceberg catalog instance.
        namespace: Iceberg namespace (e.g. ``"silver_polymarket"``).
        table_name: Iceberg table name (e.g. ``"trades"``).
        partition: Optional specific partition to compact. If None, scans all.
        dry_run: If True, report what would be compacted without writing.

    Returns:
        List of CompactionResult for each partition processed.
    """
    if (namespace, table_name) not in SILVER_TABLES:
        msg = f"Unknown table: {namespace}.{table_name}"
        raise MaintenanceError(msg)

    table = _load_table(catalog, namespace, table_name)
    full_name = f"{namespace}.{table_name}"

    logger.info("compaction_scan_start", table=full_name, partition_filter=partition)

    partition_stats = _get_partition_file_stats(table)

    if not partition_stats:
        logger.info("compaction_no_files", table=full_name)
        return [
            CompactionResult(
                namespace=namespace,
                table_name=table_name,
                partition=partition,
                files_before=0,
                files_after=0,
                bytes_before=0,
                bytes_after=0,
                duration_seconds=0.0,
                skipped=True,
            )
        ]

    # Filter to specific partition if requested
    if partition is not None:
        partition_stats = {
            k: v for k, v in partition_stats.items() if k == partition
        }
        if not partition_stats:
            logger.info(
                "compaction_partition_not_found",
                table=full_name,
                partition=partition,
            )
            return [
                CompactionResult(
                    namespace=namespace,
                    table_name=table_name,
                    partition=partition,
                    files_before=0,
                    files_after=0,
                    bytes_before=0,
                    bytes_after=0,
                    duration_seconds=0.0,
                    skipped=True,
                )
            ]

    results: list[CompactionResult] = []

    for part_key, files in sorted(partition_stats.items()):
        if not _needs_compaction(files):
            logger.info(
                "compaction_skip_partition",
                table=full_name,
                partition=part_key,
                file_count=len(files),
                reason="below threshold",
            )
            results.append(
                CompactionResult(
                    namespace=namespace,
                    table_name=table_name,
                    partition=part_key,
                    files_before=len(files),
                    files_after=len(files),
                    bytes_before=sum(s for _, s in files),
                    bytes_after=sum(s for _, s in files),
                    duration_seconds=0.0,
                    skipped=True,
                )
            )
            continue

        bytes_before = sum(s for _, s in files)
        files_before = len(files)

        logger.info(
            "compaction_partition_start",
            table=full_name,
            partition=part_key,
            files=files_before,
            bytes=bytes_before,
        )

        if dry_run:
            results.append(
                CompactionResult(
                    namespace=namespace,
                    table_name=table_name,
                    partition=part_key,
                    files_before=files_before,
                    files_after=0,
                    bytes_before=bytes_before,
                    bytes_after=0,
                    duration_seconds=0.0,
                    skipped=False,
                )
            )
            continue

        t0 = time.monotonic()

        try:
            # Scan partition data and rewrite via dynamic partition overwrite
            row_filter = (
                f"event_ts_day == '{part_key}'"
                if part_key not in ("__unpartitioned__", "__null__")
                else "true"
            )
            scan = table.scan(row_filter=row_filter)
            arrow_table: pa.Table = scan.to_arrow()

            if len(arrow_table) == 0:
                logger.warning(
                    "compaction_empty_scan",
                    table=full_name,
                    partition=part_key,
                )
                continue

            table.dynamic_partition_overwrite(arrow_table)

            # Refresh to get updated file stats
            table.refresh()
            new_stats = _get_partition_file_stats(table)
            new_files = new_stats.get(part_key, [])
            files_after = len(new_files)
            bytes_after = sum(s for _, s in new_files)

        except Exception as exc:
            msg = f"Compaction failed for {full_name} partition {part_key}: {exc}"
            raise MaintenanceError(msg) from exc

        duration = time.monotonic() - t0

        logger.info(
            "compaction_partition_done",
            table=full_name,
            partition=part_key,
            files_before=files_before,
            files_after=files_after,
            bytes_before=bytes_before,
            bytes_after=bytes_after,
            duration_s=round(duration, 2),
        )

        results.append(
            CompactionResult(
                namespace=namespace,
                table_name=table_name,
                partition=part_key,
                files_before=files_before,
                files_after=files_after,
                bytes_before=bytes_before,
                bytes_after=bytes_after,
                duration_seconds=duration,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Snapshot expiration
# ---------------------------------------------------------------------------

DEFAULT_RETENTION_DAYS = 7


@dataclasses.dataclass(slots=True)
class SnapshotExpirationResult:
    """Metadata returned after a snapshot expiration operation."""

    namespace: str
    table_name: str
    snapshots_before: int
    snapshots_after: int
    snapshots_expired: int
    older_than: datetime
    duration_seconds: float


def expire_snapshots(
    catalog: Catalog,
    namespace: str,
    table_name: str,
    *,
    older_than_days: int = DEFAULT_RETENTION_DAYS,
    dry_run: bool = False,
) -> SnapshotExpirationResult:
    """Expire old snapshots from an Iceberg table.

    Removes snapshots older than the specified retention period to reduce
    metadata size. Protected snapshots (branch/tag heads) are never expired.

    Args:
        catalog: PyIceberg catalog instance.
        namespace: Iceberg namespace (e.g. ``"silver_polymarket"``).
        table_name: Iceberg table name (e.g. ``"trades"``).
        older_than_days: Expire snapshots older than this many days (default 7).
        dry_run: If True, report what would be expired without committing.

    Returns:
        SnapshotExpirationResult with before/after counts.
    """
    if (namespace, table_name) not in SILVER_TABLES:
        msg = f"Unknown table: {namespace}.{table_name}"
        raise MaintenanceError(msg)

    table = _load_table(catalog, namespace, table_name)
    full_name = f"{namespace}.{table_name}"

    cutoff = datetime.now(tz=UTC) - timedelta(days=older_than_days)
    snapshots_before = len(table.metadata.snapshots)

    logger.info(
        "expire_snapshots_start",
        table=full_name,
        older_than=cutoff.isoformat(),
        snapshots_before=snapshots_before,
        dry_run=dry_run,
    )

    if dry_run:
        # Count how many would be expired without committing
        expire_builder = table.maintenance.expire_snapshots().older_than(cutoff)
        would_expire = len(expire_builder._snapshot_ids_to_expire)
        return SnapshotExpirationResult(
            namespace=namespace,
            table_name=table_name,
            snapshots_before=snapshots_before,
            snapshots_after=snapshots_before - would_expire,
            snapshots_expired=would_expire,
            older_than=cutoff,
            duration_seconds=0.0,
        )

    t0 = time.monotonic()

    try:
        table.maintenance.expire_snapshots().older_than(cutoff).commit()
        table.refresh()
    except Exception as exc:
        msg = f"Snapshot expiration failed for {full_name}: {exc}"
        raise MaintenanceError(msg) from exc

    duration = time.monotonic() - t0
    snapshots_after = len(table.metadata.snapshots)
    expired = snapshots_before - snapshots_after

    logger.info(
        "expire_snapshots_done",
        table=full_name,
        snapshots_before=snapshots_before,
        snapshots_after=snapshots_after,
        snapshots_expired=expired,
        duration_s=round(duration, 2),
    )

    return SnapshotExpirationResult(
        namespace=namespace,
        table_name=table_name,
        snapshots_before=snapshots_before,
        snapshots_after=snapshots_after,
        snapshots_expired=expired,
        older_than=cutoff,
        duration_seconds=duration,
    )
