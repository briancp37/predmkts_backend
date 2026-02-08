"""Iceberg table maintenance operations for Silver layer.

Provides compaction to merge small data files into larger ones,
snapshot expiration to control metadata size, and orphan file cleanup.
Also provides a unified runner for scheduling all operations across tables.
"""

from __future__ import annotations

import dataclasses
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pyarrow as pa

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


@dataclasses.dataclass(slots=True)
class DedupCompactionResult:
    """Metadata returned after a dedup compaction operation."""

    namespace: str
    table_name: str
    partition: str | None
    rows_before: int
    rows_after: int
    duplicates_removed: int
    duration_seconds: float
    skipped: bool = False


# Primary key and timestamp columns for deduplication by entity type
DEDUP_KEYS: dict[str, tuple[str, str]] = {
    "markets": ("platform_market_id", "updated_at"),
    "events": ("platform_event_id", "updated_at"),
    "trades": ("platform_trade_id", "event_ts"),
}


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


def compact_with_dedup(
    catalog: Catalog,
    namespace: str,
    table_name: str,
    *,
    partition: str | None = None,
    dry_run: bool = False,
) -> list[DedupCompactionResult]:
    """Compact a table with row-level deduplication.

    For catalog entities (markets, events), this removes duplicate records
    by primary key, keeping the record with the latest updated_at timestamp.
    This is used to clean up duplicates from append-only ingestion.

    Args:
        catalog: PyIceberg catalog instance.
        namespace: Iceberg namespace (e.g. ``"silver_polymarket"``).
        table_name: Iceberg table name (e.g. ``"markets"``).
        partition: Optional specific partition to compact. If None, processes
            all partitions.
        dry_run: If True, report what would be deduplicated without writing.

    Returns:
        List of DedupCompactionResult for each partition processed.
    """
    if (namespace, table_name) not in SILVER_TABLES:
        msg = f"Unknown table: {namespace}.{table_name}"
        raise MaintenanceError(msg)

    # Get dedup configuration for this entity
    if table_name not in DEDUP_KEYS:
        msg = f"No dedup key configured for entity: {table_name}"
        raise MaintenanceError(msg)

    primary_key, timestamp_col = DEDUP_KEYS[table_name]

    table = _load_table(catalog, namespace, table_name)
    full_name = f"{namespace}.{table_name}"

    logger.info(
        "dedup_compaction_start",
        table=full_name,
        partition_filter=partition,
        primary_key=primary_key,
        timestamp_col=timestamp_col,
    )

    # Get list of partitions
    partition_stats = _get_partition_file_stats(table)

    if not partition_stats:
        logger.info("dedup_compaction_no_files", table=full_name)
        return [
            DedupCompactionResult(
                namespace=namespace,
                table_name=table_name,
                partition=partition,
                rows_before=0,
                rows_after=0,
                duplicates_removed=0,
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
                "dedup_compaction_partition_not_found",
                table=full_name,
                partition=partition,
            )
            return [
                DedupCompactionResult(
                    namespace=namespace,
                    table_name=table_name,
                    partition=partition,
                    rows_before=0,
                    rows_after=0,
                    duplicates_removed=0,
                    duration_seconds=0.0,
                    skipped=True,
                )
            ]

    results: list[DedupCompactionResult] = []

    for part_key, _files in sorted(partition_stats.items()):
        logger.info(
            "dedup_compaction_partition_start",
            table=full_name,
            partition=part_key,
        )

        t0 = time.monotonic()

        try:
            # Scan partition data
            row_filter = (
                f"event_ts_day == '{part_key}'"
                if part_key not in ("__unpartitioned__", "__null__")
                else "true"
            )
            scan = table.scan(row_filter=row_filter)
            arrow_table: pa.Table = scan.to_arrow()

            rows_before = len(arrow_table)

            if rows_before == 0:
                logger.info(
                    "dedup_compaction_empty_partition",
                    table=full_name,
                    partition=part_key,
                )
                results.append(
                    DedupCompactionResult(
                        namespace=namespace,
                        table_name=table_name,
                        partition=part_key,
                        rows_before=0,
                        rows_after=0,
                        duplicates_removed=0,
                        duration_seconds=0.0,
                        skipped=True,
                    )
                )
                continue

            # Deduplicate: keep row with latest timestamp per primary key
            records = arrow_table.to_pylist()
            latest_by_key: dict[str, dict] = {}

            for rec in records:
                key = rec.get(primary_key, "")
                ts = rec.get(timestamp_col)
                existing = latest_by_key.get(key)
                if existing is None or (ts and ts > existing.get(timestamp_col)):
                    latest_by_key[key] = rec

            deduped = list(latest_by_key.values())
            rows_after = len(deduped)
            duplicates_removed = rows_before - rows_after

            if duplicates_removed == 0:
                logger.info(
                    "dedup_compaction_no_duplicates",
                    table=full_name,
                    partition=part_key,
                    rows=rows_before,
                )
                results.append(
                    DedupCompactionResult(
                        namespace=namespace,
                        table_name=table_name,
                        partition=part_key,
                        rows_before=rows_before,
                        rows_after=rows_after,
                        duplicates_removed=0,
                        duration_seconds=time.monotonic() - t0,
                        skipped=True,
                    )
                )
                continue

            if dry_run:
                results.append(
                    DedupCompactionResult(
                        namespace=namespace,
                        table_name=table_name,
                        partition=part_key,
                        rows_before=rows_before,
                        rows_after=rows_after,
                        duplicates_removed=duplicates_removed,
                        duration_seconds=0.0,
                        skipped=False,
                    )
                )
                continue

            # Overwrite partition with deduplicated data
            deduped_table = pa.Table.from_pylist(deduped, schema=arrow_table.schema)
            table.dynamic_partition_overwrite(deduped_table)
            table.refresh()

        except Exception as exc:
            msg = f"Dedup compaction failed for {full_name} partition {part_key}: {exc}"
            raise MaintenanceError(msg) from exc

        duration = time.monotonic() - t0

        logger.info(
            "dedup_compaction_partition_done",
            table=full_name,
            partition=part_key,
            rows_before=rows_before,
            rows_after=rows_after,
            duplicates_removed=duplicates_removed,
            duration_s=round(duration, 2),
        )

        results.append(
            DedupCompactionResult(
                namespace=namespace,
                table_name=table_name,
                partition=part_key,
                rows_before=rows_before,
                rows_after=rows_after,
                duplicates_removed=duplicates_removed,
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


# ---------------------------------------------------------------------------
# Orphan file cleanup
# ---------------------------------------------------------------------------

ORPHAN_MIN_AGE_DAYS = 7


@dataclasses.dataclass(slots=True)
class OrphanCleanupResult:
    """Metadata returned after an orphan file cleanup operation."""

    namespace: str
    table_name: str
    orphan_files_found: int
    orphan_files_deleted: int
    orphan_bytes: int
    duration_seconds: float


def _parse_s3_url(url: str) -> tuple[str, str]:
    """Parse ``s3://bucket/key`` into (bucket, key)."""
    if not url.startswith("s3://"):
        msg = f"Not an S3 URL: {url}"
        raise MaintenanceError(msg)
    without_scheme = url[5:]
    bucket, _, key = without_scheme.partition("/")
    return bucket, key


def _list_s3_data_files(
    bucket: str,
    prefix: str,
) -> list[tuple[str, int, datetime]]:
    """List all .parquet files under an S3 prefix.

    Returns list of (s3_url, size_bytes, last_modified).
    """
    import boto3

    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")

    files: list[tuple[str, int, datetime]] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key: str = obj["Key"]
            if key.endswith(".parquet"):
                s3_url = f"s3://{bucket}/{key}"
                files.append((s3_url, obj["Size"], obj["LastModified"]))

    return files


def remove_orphans(
    catalog: Catalog,
    namespace: str,
    table_name: str,
    *,
    older_than_days: int = ORPHAN_MIN_AGE_DAYS,
    dry_run: bool = False,
) -> OrphanCleanupResult:
    """Detect and remove orphaned data files from an Iceberg table.

    Orphan files are Parquet files in the table's data directory that are
    not referenced by any snapshot in the table metadata. Only files older
    than ``older_than_days`` are eligible for deletion as a safety measure.

    Args:
        catalog: PyIceberg catalog instance.
        namespace: Iceberg namespace (e.g. ``"silver_polymarket"``).
        table_name: Iceberg table name (e.g. ``"trades"``).
        older_than_days: Only delete orphans older than this many days (default 7).
        dry_run: If True, report orphans without deleting them.

    Returns:
        OrphanCleanupResult with counts of files found and deleted.
    """
    import boto3

    if (namespace, table_name) not in SILVER_TABLES:
        msg = f"Unknown table: {namespace}.{table_name}"
        raise MaintenanceError(msg)

    table = _load_table(catalog, namespace, table_name)
    full_name = f"{namespace}.{table_name}"

    logger.info("orphan_cleanup_start", table=full_name, dry_run=dry_run)

    t0 = time.monotonic()

    # Collect all data file paths tracked across all snapshots
    tracked_files: set[str] = set()
    files_table = table.inspect.data_files()
    if "file_path" in files_table.column_names:
        tracked_files = set(files_table.column("file_path").to_pylist())

    # List all parquet files on S3 under the table location
    table_location = table.location()
    bucket, prefix = _parse_s3_url(table_location)
    # Ensure prefix ends with /data/ to only scan data directory
    data_prefix = prefix.rstrip("/") + "/data/"

    all_s3_files = _list_s3_data_files(bucket, data_prefix)

    # Identify orphans: on S3 but not in metadata, older than safety threshold
    cutoff = datetime.now(tz=UTC) - timedelta(days=older_than_days)
    orphans: list[tuple[str, int]] = []  # (s3_url, size)

    for s3_url, size, last_modified in all_s3_files:
        if s3_url not in tracked_files and last_modified.replace(tzinfo=UTC) < cutoff:
            orphans.append((s3_url, size))

    orphan_bytes = sum(s for _, s in orphans)

    logger.info(
        "orphan_cleanup_scan_done",
        table=full_name,
        tracked_files=len(tracked_files),
        s3_files=len(all_s3_files),
        orphans_found=len(orphans),
        orphan_bytes=orphan_bytes,
    )

    if not orphans or dry_run:
        duration = time.monotonic() - t0
        return OrphanCleanupResult(
            namespace=namespace,
            table_name=table_name,
            orphan_files_found=len(orphans),
            orphan_files_deleted=0,
            orphan_bytes=orphan_bytes,
            duration_seconds=duration,
        )

    # Delete orphan files
    s3 = boto3.client("s3")
    deleted = 0
    for s3_url, _size in orphans:
        _, key = _parse_s3_url(s3_url)
        try:
            s3.delete_object(Bucket=bucket, Key=key)
            deleted += 1
        except Exception:
            logger.warning("orphan_delete_failed", file=s3_url)

    duration = time.monotonic() - t0

    logger.info(
        "orphan_cleanup_done",
        table=full_name,
        orphans_deleted=deleted,
        orphan_bytes=orphan_bytes,
        duration_s=round(duration, 2),
    )

    return OrphanCleanupResult(
        namespace=namespace,
        table_name=table_name,
        orphan_files_found=len(orphans),
        orphan_files_deleted=deleted,
        orphan_bytes=orphan_bytes,
        duration_seconds=duration,
    )


# ---------------------------------------------------------------------------
# Maintenance runner — runs all operations across all tables
# ---------------------------------------------------------------------------


@dataclasses.dataclass(slots=True)
class MaintenanceRunResult:
    """Summary of a full maintenance run across all tables."""

    tables_processed: int
    compaction_results: list[CompactionResult]
    dedup_results: list[DedupCompactionResult]
    expiration_results: list[SnapshotExpirationResult]
    orphan_results: list[OrphanCleanupResult]
    errors: list[tuple[str, str]]  # (table_name, error_message)
    duration_seconds: float


def run_all_maintenance(
    catalog: Catalog,
    *,
    operations: frozenset[str] = frozenset({"compact", "expire", "orphans"}),
    expire_older_than_days: int = DEFAULT_RETENTION_DAYS,
    orphan_older_than_days: int = ORPHAN_MIN_AGE_DAYS,
    dry_run: bool = False,
) -> MaintenanceRunResult:
    """Run maintenance operations across all Silver Iceberg tables.

    Designed to be called from a scheduler (cron, EventBridge, etc.).
    Operations are run sequentially per table: compact, dedup, expire
    snapshots, then remove orphans.

    Args:
        catalog: PyIceberg catalog instance.
        operations: Set of operations to run. Valid values:
            ``"compact"``, ``"dedup"``, ``"expire"``, ``"orphans"``.
        expire_older_than_days: Retention period for snapshot expiration.
        orphan_older_than_days: Min age for orphan file deletion.
        dry_run: If True, preview without making changes.

    Returns:
        MaintenanceRunResult with per-table results and errors.
    """
    t0 = time.monotonic()

    compaction_results: list[CompactionResult] = []
    dedup_results: list[DedupCompactionResult] = []
    expiration_results: list[SnapshotExpirationResult] = []
    orphan_results: list[OrphanCleanupResult] = []
    errors: list[tuple[str, str]] = []
    tables_processed = 0

    for namespace, table_name in sorted(SILVER_TABLES):
        full_name = f"{namespace}.{table_name}"
        logger.info("maintenance_run_table_start", table=full_name, dry_run=dry_run)

        if "compact" in operations:
            try:
                results = compact_table(
                    catalog, namespace, table_name, dry_run=dry_run,
                )
                compaction_results.extend(results)
            except MaintenanceError as exc:
                logger.warning("maintenance_compact_error", table=full_name, error=str(exc))
                errors.append((full_name, f"compact: {exc}"))

        if "dedup" in operations:
            try:
                dedup_res = compact_with_dedup(
                    catalog, namespace, table_name, dry_run=dry_run,
                )
                dedup_results.extend(dedup_res)
            except MaintenanceError as exc:
                logger.warning("maintenance_dedup_error", table=full_name, error=str(exc))
                errors.append((full_name, f"dedup: {exc}"))

        if "expire" in operations:
            try:
                exp_result = expire_snapshots(
                    catalog,
                    namespace,
                    table_name,
                    older_than_days=expire_older_than_days,
                    dry_run=dry_run,
                )
                expiration_results.append(exp_result)
            except MaintenanceError as exc:
                logger.warning("maintenance_expire_error", table=full_name, error=str(exc))
                errors.append((full_name, f"expire: {exc}"))

        if "orphans" in operations:
            try:
                orph_result = remove_orphans(
                    catalog,
                    namespace,
                    table_name,
                    older_than_days=orphan_older_than_days,
                    dry_run=dry_run,
                )
                orphan_results.append(orph_result)
            except MaintenanceError as exc:
                logger.warning("maintenance_orphan_error", table=full_name, error=str(exc))
                errors.append((full_name, f"orphans: {exc}"))

        tables_processed += 1

    duration = time.monotonic() - t0
    logger.info(
        "maintenance_run_done",
        tables=tables_processed,
        errors=len(errors),
        duration_s=round(duration, 2),
    )

    return MaintenanceRunResult(
        tables_processed=tables_processed,
        compaction_results=compaction_results,
        dedup_results=dedup_results,
        expiration_results=expiration_results,
        orphan_results=orphan_results,
        errors=errors,
        duration_seconds=duration,
    )
