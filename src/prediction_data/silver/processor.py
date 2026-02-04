"""End-to-end Silver processing orchestrator.

Orchestrates the full Bronze → Silver pipeline for a single manifest:
discover → read → dedup → normalize → quality checks → write.
"""

from __future__ import annotations

import dataclasses
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from prediction_data.core.logging import get_logger
from prediction_data.silver.dedup import dedup_batch
from prediction_data.silver.discovery import silver_entity_for
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
from prediction_data.silver.reader import ReadResult, read_manifest_data
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

    # --- Write (append, overwrite, or merge/upsert) ---
    namespace = _build_namespace(platform)
    try:
        if append_only:
            write_result: WriteResult = write_to_iceberg(
                normalized,
                catalog,
                namespace,
                entity,
            )
        elif overwrite:
            write_result = overwrite_to_iceberg(
                normalized,
                catalog,
                namespace,
                entity,
            )
        else:
            join_cols = normalizer.merge_keys()
            write_result = merge_to_iceberg(
                normalized,
                catalog,
                namespace,
                entity,
                join_cols=join_cols,
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
