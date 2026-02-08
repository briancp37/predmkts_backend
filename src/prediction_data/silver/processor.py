"""End-to-end Silver processing orchestrator.

Orchestrates the full Bronze → Silver pipeline for a single manifest:
discover → read → dedup → normalize → quality checks → write.
"""

from __future__ import annotations

import dataclasses
import gc
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from prediction_data.core.logging import get_logger
from prediction_data.silver.dedup import dedup_batch
from prediction_data.silver.discovery import CATALOG_ENTITIES, silver_entity_for
from prediction_data.silver.normalize import (
    PolymarketTradesNormalizer,
    get_normalizer,
)
from prediction_data.silver.quality import (
    QualityCheckError,
    QualityCheckResult,
    checks_for_entity,
    run_quality_checks,
)
from prediction_data.silver.reader import ReadResult, read_manifest_data, read_single_file
from prediction_data.silver.writer import (
    IcebergWriteError,
    WriteResult,
    merge_to_iceberg,
    overwrite_to_iceberg,
    write_to_iceberg,
)

if TYPE_CHECKING:
    from pyiceberg.catalog import Catalog

    from prediction_data.silver.discovery import DiscoveredManifest
    from prediction_data.storage.s3 import S3Client

logger = get_logger(__name__)


class ProcessingError(Exception):
    """Raised when Silver processing fails for a manifest."""


@dataclasses.dataclass(slots=True)
class ProcessingResult:
    """Metadata from processing a single manifest."""

    platform: str
    entity: str
    dt: str
    run_id: str
    rows_read: int
    rows_after_dedup: int
    duplicates_dropped: int
    rows_normalized: int
    rows_written: int
    rows_inserted: int
    rows_updated: int
    snapshot_id: int
    quality_checks_passed: int
    duration_seconds: float


def _build_namespace(platform: str) -> str:
    """Map platform name to Iceberg namespace."""
    return f"silver_{platform}"


async def process_manifest(
    manifest: DiscoveredManifest,
    s3_client: S3Client,
    catalog: Catalog,
    *,
    skip_quality_checks: bool = False,
    markets_lookup: Any | None = None,
    append_only: bool = False,
    overwrite: bool = False,
    merge: bool = False,
) -> ProcessingResult:
    """Process a single Bronze manifest through the Silver pipeline.

    Steps:
        1. Read Bronze JSONL.gz data from S3.
        2. Dedup raw records using entity-specific dedup key.
        3. Normalize records to Silver schema.
        4. Run quality checks (abort on failure, unless skip_quality_checks=True).
        5. Write to Iceberg table.

    Args:
        manifest: Discovered Bronze manifest to process.
        s3_client: S3 client for reading Bronze data.
        catalog: PyIceberg catalog for writing Silver tables.
        skip_quality_checks: If True, skip quality checks during processing.
        markets_lookup: Pre-loaded MarketsReferenceLookup for trades processing.
            If provided, skips the per-manifest markets reference loading.

    Returns:
        A :class:`ProcessingResult` with pipeline metrics.

    Raises:
        ProcessingError: On read, normalization, or write failure.
    """
    platform = manifest.platform
    bronze_entity = manifest.entity
    entity = silver_entity_for(platform, bronze_entity)
    dt = manifest.dt
    run_id = manifest.run_id

    logger.info(
        "processing_start",
        platform=platform,
        entity=entity,
        dt=dt,
        run_id=run_id,
    )

    t0 = time.monotonic()

    # --- Read ---
    try:
        read_result: ReadResult = await read_manifest_data(s3_client, manifest)
    except Exception as exc:
        msg = f"Failed to read manifest {run_id}: {exc}"
        raise ProcessingError(msg) from exc

    records: list[dict[str, Any]] = read_result.records

    logger.info(
        "processing_read_done",
        platform=platform,
        entity=entity,
        run_id=run_id,
        records_read=read_result.records_read,
        files_read=read_result.files_read,
        errors=read_result.errors,
    )

    if not records:
        msg = f"No records read from manifest {run_id}"
        raise ProcessingError(msg)

    # --- Dedup ---
    normalizer = get_normalizer(platform, entity)
    deduped, dedup_stats = dedup_batch(records, normalizer)

    logger.info(
        "processing_dedup_done",
        platform=platform,
        entity=entity,
        run_id=run_id,
        records_in=dedup_stats.records_in,
        duplicates_dropped=dedup_stats.duplicates_dropped,
        records_out=dedup_stats.records_out,
    )

    # --- Load markets reference for trades normalization ---
    if isinstance(normalizer, PolymarketTradesNormalizer):
        if markets_lookup is not None:
            lookup = markets_lookup
        else:
            from prediction_data.silver.polymarket.markets_reference import (
                load_markets_reference,
            )

            logger.info(
                "loading_markets_reference",
                platform=platform,
                entity=entity,
                run_id=run_id,
            )
            try:
                lookup = await load_markets_reference(s3_client)
            except Exception as exc:
                msg = f"Failed to load markets reference for trades processing: {exc}"
                raise ProcessingError(msg) from exc

            if len(lookup) == 0:
                msg = (
                    "Markets reference lookup is empty — no Bronze markets data found. "
                    "Ingest and process markets before processing trades."
                )
                raise ProcessingError(msg)

            logger.info(
                "markets_reference_loaded",
                platform=platform,
                entity=entity,
                run_id=run_id,
                **lookup.coverage_stats,
            )

        normalizer.set_lookup(lookup)

    # --- Normalize ---
    silver_ingestion_ts = datetime.now(UTC)
    normalized = normalizer.normalize_batch(
        deduped,
        bronze_run_id=run_id,
        silver_ingestion_ts=silver_ingestion_ts,
    )

    if not normalized:
        msg = f"All records failed normalization for manifest {run_id}"
        raise ProcessingError(msg)

    logger.info(
        "processing_normalize_done",
        platform=platform,
        entity=entity,
        run_id=run_id,
        rows_normalized=len(normalized),
        rows_skipped=len(deduped) - len(normalized),
    )

    # --- Late-arrival detection ---
    now = datetime.now(UTC)
    late_threshold = now - timedelta(days=7)
    late_records = [
        r for r in normalized
        if isinstance(r.get("event_ts"), datetime) and r["event_ts"] < late_threshold
    ]
    if late_records:
        oldest_ts = min(r["event_ts"] for r in late_records)
        logger.warning(
            "late_arriving_data",
            platform=platform,
            entity=entity,
            dt=dt,
            run_id=run_id,
            late_record_count=len(late_records),
            total_records=len(normalized),
            oldest_event_ts=str(oldest_ts),
            days_old=(now - oldest_ts).days,
        )

    # --- Quality checks ---
    quality_results: list[QualityCheckResult] = []
    if skip_quality_checks:
        logger.info(
            "processing_quality_skipped",
            platform=platform,
            entity=entity,
            run_id=run_id,
        )
    else:
        expected_date = datetime.strptime(dt, "%Y-%m-%d").replace(tzinfo=UTC)
        quality_checks = checks_for_entity(platform, entity, expected_date=expected_date)

        try:
            quality_results = run_quality_checks(
                quality_checks, normalized
            )
        except QualityCheckError as exc:
            msg = f"Quality check failed for manifest {run_id}: {exc}"
            raise ProcessingError(msg) from exc

        logger.info(
            "processing_quality_done",
            platform=platform,
            entity=entity,
            run_id=run_id,
            checks_passed=len(quality_results),
        )

    # --- Write (overwrite, merge, or append) ---
    #
    # Default is append for ALL entities (fast, no table scan, low memory).
    # The Gold layer handles deduplication at read time by keeping the
    # latest record per primary key by updated_at timestamp.
    #
    # Write strategy precedence:
    #   1. --overwrite: Replace all data (for full snapshots)
    #   2. --merge: Upsert by primary key (legacy, memory-intensive)
    #   3. Default: Append (fast, Gold handles dedup)
    namespace = _build_namespace(platform)
    try:
        if overwrite:
            write_result: WriteResult = overwrite_to_iceberg(
                normalized,
                catalog,
                namespace,
                entity,
            )
        elif merge:
            join_cols = normalizer.merge_keys()
            write_result = merge_to_iceberg(
                normalized,
                catalog,
                namespace,
                entity,
                join_cols=join_cols,
            )
        else:
            # Default: append (fast, no table scan)
            write_result = write_to_iceberg(
                normalized,
                catalog,
                namespace,
                entity,
            )
    except (IcebergWriteError, KeyError) as exc:
        msg = f"Failed to write Silver for manifest {run_id}: {exc}"
        raise ProcessingError(msg) from exc

    duration = time.monotonic() - t0

    logger.info(
        "processing_done",
        platform=platform,
        entity=entity,
        dt=dt,
        run_id=run_id,
        rows_read=read_result.records_read,
        rows_written=write_result.rows_written,
        rows_inserted=write_result.rows_inserted,
        rows_updated=write_result.rows_updated,
        duplicates_dropped=dedup_stats.duplicates_dropped,
        snapshot_id=write_result.snapshot_id,
        quality_checks_passed=len(quality_results),
        duration_s=round(duration, 2),
    )

    return ProcessingResult(
        platform=platform,
        entity=entity,
        dt=dt,
        run_id=run_id,
        rows_read=read_result.records_read,
        rows_after_dedup=dedup_stats.records_out,
        duplicates_dropped=dedup_stats.duplicates_dropped,
        rows_normalized=len(normalized),
        rows_written=write_result.rows_written,
        rows_inserted=write_result.rows_inserted,
        rows_updated=write_result.rows_updated,
        snapshot_id=write_result.snapshot_id,
        quality_checks_passed=len(quality_results),
        duration_seconds=duration,
    )


async def process_manifest_chunked(
    manifest: DiscoveredManifest,
    s3_client: S3Client,
    catalog: Catalog,
    *,
    skip_quality_checks: bool = False,
    markets_lookup: Any | None = None,
    overwrite: bool = False,
    merge: bool = False,
) -> ProcessingResult:
    """Process a manifest file-by-file for bounded memory usage.

    Each Bronze part file is processed independently:
    read → dedup → normalize → write to Iceberg → free memory.

    Memory usage is bounded by the largest single part file, not the
    entire manifest.

    Args:
        manifest: Discovered Bronze manifest to process.
        s3_client: S3 client for reading Bronze data.
        catalog: PyIceberg catalog for writing Silver tables.
        skip_quality_checks: If True, skip quality checks.
        markets_lookup: Pre-loaded MarketsReferenceLookup for trades.
        overwrite: If True, first chunk overwrites table, rest append.
        merge: If True, upsert each chunk using entity merge keys.

    Returns:
        A :class:`ProcessingResult` with aggregated pipeline metrics.

    Raises:
        ProcessingError: On read, normalization, or write failure.
    """
    platform = manifest.platform
    bronze_entity = manifest.entity
    entity = silver_entity_for(platform, bronze_entity)
    dt = manifest.dt
    run_id = manifest.run_id

    files = manifest.manifest.files
    if not files:
        msg = f"Manifest {run_id} has no files"
        raise ProcessingError(msg)

    logger.info(
        "chunked_processing_start",
        platform=platform,
        entity=entity,
        dt=dt,
        run_id=run_id,
        file_count=len(files),
    )

    t0 = time.monotonic()

    # --- Set up normalizer (once) ---
    normalizer = get_normalizer(platform, entity)

    if isinstance(normalizer, PolymarketTradesNormalizer):
        if markets_lookup is not None:
            lookup = markets_lookup
        else:
            from prediction_data.silver.polymarket.markets_reference import (
                load_markets_reference,
            )

            logger.info("loading_markets_reference", platform=platform, entity=entity, run_id=run_id)
            try:
                lookup = await load_markets_reference(s3_client)
            except Exception as exc:
                msg = f"Failed to load markets reference for trades processing: {exc}"
                raise ProcessingError(msg) from exc

            if len(lookup) == 0:
                msg = (
                    "Markets reference lookup is empty — no Bronze markets data found. "
                    "Ingest and process markets before processing trades."
                )
                raise ProcessingError(msg)

            logger.info("markets_reference_loaded", platform=platform, entity=entity, run_id=run_id, **lookup.coverage_stats)

        normalizer.set_lookup(lookup)

    namespace = _build_namespace(platform)
    silver_ingestion_ts = datetime.now(UTC)

    # --- Aggregate metrics ---
    total_read = 0
    total_after_dedup = 0
    total_dupes_dropped = 0
    total_normalized = 0
    total_written = 0
    total_quality_passed = 0
    last_snapshot_id = -1
    files_processed = 0
    file_errors = 0
    first_write_done = False  # Track if we've done the first write (for overwrite mode)

    for file_idx, file_ref in enumerate(files):
        file_label = f"file {file_idx + 1}/{len(files)} ({file_ref.key})"
        try:
            records = read_single_file(s3_client, file_ref)
        except Exception as exc:
            logger.warning("chunked_file_read_failed", file=file_ref.key, run_id=run_id, error=str(exc))
            file_errors += 1
            continue

        if not records:
            logger.debug("chunked_file_empty", file=file_ref.key, run_id=run_id)
            continue

        file_read = len(records)
        total_read += file_read

        # --- Dedup ---
        deduped, dedup_stats = dedup_batch(records, normalizer)
        total_after_dedup += dedup_stats.records_out
        total_dupes_dropped += dedup_stats.duplicates_dropped
        del records

        # --- Normalize ---
        normalized = normalizer.normalize_batch(
            deduped,
            bronze_run_id=run_id,
            silver_ingestion_ts=silver_ingestion_ts,
        )
        del deduped

        if not normalized:
            logger.warning("chunked_file_all_normalization_failed", file=file_ref.key, run_id=run_id, records_in=file_read)
            continue

        total_normalized += len(normalized)

        # --- Quality checks ---
        if not skip_quality_checks:
            expected_date = datetime.strptime(dt, "%Y-%m-%d").replace(tzinfo=UTC)
            quality_checks = checks_for_entity(platform, entity, expected_date=expected_date)
            try:
                qr = run_quality_checks(quality_checks, normalized)
                total_quality_passed += len(qr)
            except QualityCheckError as exc:
                logger.warning("chunked_file_quality_failed", file=file_ref.key, run_id=run_id, error=str(exc))
                del normalized
                gc.collect()
                continue

        # --- Write (overwrite first chunk, merge, or append) ---
        try:
            if overwrite and not first_write_done:
                write_result = overwrite_to_iceberg(normalized, catalog, namespace, entity)
                first_write_done = True
            elif merge:
                join_cols = normalizer.merge_keys()
                write_result = merge_to_iceberg(normalized, catalog, namespace, entity, join_cols=join_cols)
            else:
                write_result = write_to_iceberg(normalized, catalog, namespace, entity)
            total_written += write_result.rows_written
            last_snapshot_id = write_result.snapshot_id
            files_processed += 1
        except (IcebergWriteError, KeyError) as exc:
            msg = f"Failed to write Silver for {file_label} in manifest {run_id}: {exc}"
            raise ProcessingError(msg) from exc
        finally:
            del normalized
            gc.collect()

        logger.info(
            "chunked_file_done",
            file=file_ref.key,
            run_id=run_id,
            rows_read=file_read,
            rows_written=write_result.rows_written,
        )

    duration = time.monotonic() - t0

    if total_written == 0 and total_read > 0:
        msg = f"No records written from manifest {run_id} ({total_read} read, {file_errors} file errors)"
        raise ProcessingError(msg)

    logger.info(
        "chunked_processing_done",
        platform=platform,
        entity=entity,
        dt=dt,
        run_id=run_id,
        files_processed=files_processed,
        file_errors=file_errors,
        rows_read=total_read,
        rows_written=total_written,
        duration_s=round(duration, 2),
    )

    return ProcessingResult(
        platform=platform,
        entity=entity,
        dt=dt,
        run_id=run_id,
        rows_read=total_read,
        rows_after_dedup=total_after_dedup,
        duplicates_dropped=total_dupes_dropped,
        rows_normalized=total_normalized,
        rows_written=total_written,
        rows_inserted=0,
        rows_updated=0,
        snapshot_id=last_snapshot_id,
        quality_checks_passed=total_quality_passed,
        duration_seconds=duration,
    )
