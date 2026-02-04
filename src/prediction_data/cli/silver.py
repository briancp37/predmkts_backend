"""Silver layer CLI commands."""

from __future__ import annotations

import asyncio
import gc
import itertools
import os
from datetime import date, timedelta
from typing import TYPE_CHECKING, Annotated

import typer

if TYPE_CHECKING:
    from prediction_data.silver.maintenance import (
        CompactionResult,
        MaintenanceRunResult,
        OrphanCleanupResult,
        SnapshotExpirationResult,
    )

app = typer.Typer(
    help="Silver layer processing and Iceberg table management.",
    no_args_is_help=True,
)

# Valid platform/entity combinations for Silver processing.
_VALID_TARGETS: list[tuple[str, str]] = [
    ("polymarket", "trades"),
    ("polymarket", "markets"),
    ("polymarket", "events"),
    ("kalshi", "trades"),
    ("kalshi", "markets"),
    ("kalshi", "events"),
]

_VALID_PLATFORMS = sorted({p for p, _ in _VALID_TARGETS})
_VALID_ENTITIES = sorted({e for _, e in _VALID_TARGETS})


def _validate_platform_entity(platform: str, entity: str) -> None:
    """Raise typer.BadParameter if the platform/entity combo is invalid."""
    if platform not in _VALID_PLATFORMS:
        raise typer.BadParameter(
            f"Unknown platform '{platform}'. Valid: {', '.join(_VALID_PLATFORMS)}"
        )
    if entity not in _VALID_ENTITIES:
        raise typer.BadParameter(
            f"Unknown entity '{entity}'. Valid: {', '.join(_VALID_ENTITIES)}"
        )
    if (platform, entity) not in _VALID_TARGETS:
        raise typer.BadParameter(
            f"No Silver table for {platform}/{entity}."
        )


@app.command(name="init-tables")
def init_tables(
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview table creation without creating tables.",
        ),
    ] = False,
) -> None:
    """Initialize all Silver Iceberg tables in the Glue Catalog."""
    from prediction_data.core.logging import configure_logging
    from prediction_data.silver.catalog import get_catalog
    from prediction_data.silver.tables import SILVER_TABLES, init_tables

    configure_logging()

    if dry_run:
        typer.echo("Dry run — no tables will be created.\n")

    typer.echo(f"Initializing {len(SILVER_TABLES)} Silver Iceberg tables...")

    try:
        catalog = get_catalog()
        created = init_tables(catalog, dry_run=dry_run)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    if dry_run:
        typer.echo(f"\n{len(created)} table(s) would be created.")
    else:
        typer.echo(f"\nDone. {len(created)} table(s) created.")


@app.command(name="process")
def process(
    platform: Annotated[
        str,
        typer.Option(
            "--platform",
            help=f"Platform to process ({', '.join(_VALID_PLATFORMS)}).",
        ),
    ],
    entity: Annotated[
        str,
        typer.Option(
            "--entity",
            help=f"Entity to process ({', '.join(_VALID_ENTITIES)}).",
        ),
    ],
    dt: Annotated[
        str | None,
        typer.Option(
            "--dt",
            help="Single date to process (YYYY-MM-DD).",
        ),
    ] = None,
    start_date: Annotated[
        str | None,
        typer.Option(
            "--start-date",
            help="Start date for range processing (YYYY-MM-DD, inclusive).",
        ),
    ] = None,
    end_date: Annotated[
        str | None,
        typer.Option(
            "--end-date",
            help="End date for range processing (YYYY-MM-DD, inclusive).",
        ),
    ] = None,
    bucket: Annotated[
        str | None,
        typer.Option(
            "--bucket",
            help="S3 bucket name (defaults to BRONZE_BUCKET env var).",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview manifests that would be processed without writing.",
        ),
    ] = False,
    force_reprocess: Annotated[
        bool,
        typer.Option(
            "--force-reprocess",
            help="Reprocess manifests even if already processed.",
        ),
    ] = False,
    skip_quality_checks: Annotated[
        bool,
        typer.Option(
            "--skip-quality-checks",
            help="Skip quality checks during processing.",
        ),
    ] = False,
    closed_days_only: Annotated[
        bool,
        typer.Option(
            "--closed-days-only",
            help=(
                "Only process completed days (before today). "
                "Use for end-of-day batch processing of stream entities."
            ),
        ),
    ] = False,
    append_only: Annotated[
        bool,
        typer.Option(
            "--append-only",
            help=(
                "Force append writes instead of merge/upsert. "
                "Stream entities (trades, order_filled) already default to "
                "append; this flag forces append for catalog entities too."
            ),
        ),
    ] = False,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            help=(
                "Replace all table data instead of merge/upsert. "
                "Use for catalog entities (markets, events) with full snapshots."
            ),
        ),
    ] = False,
) -> None:
    """Process Bronze manifests into Silver Iceberg tables.

    Specify either --dt for a single day, or --start-date/--end-date for a
    date range.  Use --closed-days-only to restrict processing to days before
    today (useful for end-of-day batch processing of stream entities like
    trades and order_filled).
    """
    from prediction_data.core.logging import configure_logging

    configure_logging()

    _validate_platform_entity(platform, entity)

    # Resolve dates
    if dt and (start_date or end_date):
        typer.echo("Error: Use --dt or --start-date/--end-date, not both.", err=True)
        raise typer.Exit(code=1)

    if not dt and not start_date:
        typer.echo("Error: Provide --dt or --start-date.", err=True)
        raise typer.Exit(code=1)

    resolved_start = dt or start_date
    resolved_end = dt or end_date or start_date

    assert resolved_start is not None
    assert resolved_end is not None

    if closed_days_only:
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        if resolved_start > yesterday:
            typer.echo(
                f"No closed days to process (start={resolved_start}, today={date.today().isoformat()})."
            )
            return
        if resolved_end > yesterday:
            typer.echo(
                f"Clamping end date from {resolved_end} to {yesterday} (--closed-days-only)."
            )
            resolved_end = yesterday

    resolved_bucket = bucket or os.environ.get("BRONZE_BUCKET", "")
    if not resolved_bucket:
        typer.echo("Error: --bucket or BRONZE_BUCKET env var required.", err=True)
        raise typer.Exit(code=1)

    asyncio.run(
        _run_process(
            platform=platform,
            entity=entity,
            start_date=resolved_start,
            end_date=resolved_end,
            bucket=resolved_bucket,
            dry_run=dry_run,
            force_reprocess=force_reprocess,
            skip_quality_checks=skip_quality_checks,
            append_only=append_only,
            overwrite=overwrite,
        )
    )


async def _run_process(
    *,
    platform: str,
    entity: str,
    start_date: str,
    end_date: str,
    bucket: str,
    dry_run: bool,
    force_reprocess: bool,
    skip_quality_checks: bool,
    append_only: bool = False,
    overwrite: bool = False,
) -> None:
    """Discover and process Bronze manifests for the given scope."""
    from prediction_data.silver.catalog import get_catalog
    from prediction_data.silver.discovery import (
        CATALOG_ENTITIES,
        discover_manifests,
        select_manifests_for_day,
    )
    from prediction_data.silver.processor import (
        ProcessingError,
        process_manifest,
        process_manifest_chunked,
    )
    from prediction_data.storage import S3Client

    s3 = S3Client(bucket=bucket)

    typer.echo(
        f"Discovering manifests for {platform}/{entity} "
        f"({start_date} to {end_date})..."
    )

    manifests = await discover_manifests(
        s3, platform, entity, start_date=start_date, end_date=end_date
    )

    if not manifests:
        typer.echo("No manifests found.")
        raise typer.Exit(code=0)

    typer.echo(f"Found {len(manifests)} manifest(s).")

    # Load state tracker for idempotency
    from prediction_data.silver.state import SilverStateStore

    state_store = SilverStateStore(s3, platform, entity)
    await state_store.load()

    # Filter out already-processed manifests unless --force-reprocess
    if not force_reprocess:
        before = len(manifests)
        manifests = [m for m in manifests if not state_store.is_processed(m.run_id)]
        skipped = before - len(manifests)
        if skipped:
            typer.echo(f"Skipping {skipped} already-processed manifest(s).")

    if not manifests:
        typer.echo("No unprocessed manifests remaining.")
        return

    # Group manifests by day for day-level progress and error resilience.
    days = [
        (dt, list(group))
        for dt, group in itertools.groupby(manifests, key=lambda m: m.dt)
    ]
    total_days = len(days)

    if dry_run:
        typer.echo(f"\nDry run — {len(manifests)} manifest(s) across {total_days} day(s):")
        for dt, day_manifests in days:
            selected = select_manifests_for_day(day_manifests, entity)
            skipped = len(day_manifests) - len(selected)
            suffix = f" ({skipped} superseded by snapshot)" if skipped else ""
            typer.echo(f"  {dt}: {len(selected)} manifest(s){suffix}")
            for m in selected:
                typer.echo(f"    run_id={m.run_id} [{m.snapshot_type}]")
        return

    catalog = get_catalog()

    # Pre-load markets reference for trades processing (avoid per-manifest reload)
    markets_lookup = None
    if entity == "trades":
        from prediction_data.silver.polymarket.markets_reference import (
            load_markets_reference,
        )

        typer.echo("Pre-loading markets reference for trades processing...")
        try:
            markets_lookup = await load_markets_reference(s3)
        except Exception as e:
            typer.echo(f"Error loading markets reference: {e}", err=True)
            raise typer.Exit(code=1)

        if len(markets_lookup) == 0:
            typer.echo(
                "Error: Markets reference is empty — no Bronze markets data found. "
                "Ingest markets before processing trades.",
                err=True,
            )
            raise typer.Exit(code=1)

        typer.echo(
            f"Markets reference loaded: {markets_lookup.coverage_stats}"
        )

    total_processed = 0
    total_manifests = len(manifests)
    day_failures: list[tuple[str, list[tuple[str, str]]]] = []

    for day_idx, (dt, day_manifests) in enumerate(days, 1):
        # Apply entity-aware manifest selection per day.
        before_selection = len(day_manifests)
        day_manifests = select_manifests_for_day(day_manifests, entity)
        skipped_by_snapshot = before_selection - len(day_manifests)
        if skipped_by_snapshot:
            typer.echo(
                f"  Skipped {skipped_by_snapshot} manifest(s) superseded by snapshot "
                f"for {dt}."
            )

        typer.echo(
            f"\n=== Day {day_idx}/{total_days}: {dt} "
            f"({len(day_manifests)} manifest(s)) ==="
        )

        day_errors: list[tuple[str, str]] = []

        is_stream = entity not in CATALOG_ENTITIES

        for m in day_manifests:
            total_processed_so_far = total_processed + len(day_errors)
            progress = total_processed_so_far + 1
            label = f"[{progress}/{total_manifests}] {m.platform}/{m.entity} dt={m.dt}"
            typer.echo(f"  Processing {label} ...")

            try:
                if is_stream:
                    result = await process_manifest_chunked(
                        m, s3, catalog,
                        skip_quality_checks=skip_quality_checks,
                        markets_lookup=markets_lookup,
                    )
                else:
                    result = await process_manifest(
                        m, s3, catalog,
                        skip_quality_checks=skip_quality_checks,
                        markets_lookup=markets_lookup,
                        append_only=append_only,
                        overwrite=overwrite,
                    )
                total_processed += 1
                typer.echo(
                    f"    OK: {result.rows_written} rows written, "
                    f"snapshot_id={result.snapshot_id}, "
                    f"{result.duplicates_dropped} dupes dropped, "
                    f"{result.duration_seconds:.1f}s"
                )
                await state_store.mark_processed(
                    run_id=m.run_id,
                    platform=m.platform,
                    entity=m.entity,
                    dt=m.dt,
                )
            except ProcessingError as exc:
                day_errors.append((m.run_id, str(exc)))
                typer.echo(f"    FAILED: {exc}", err=True)
            finally:
                gc.collect()

        if day_errors:
            day_failures.append((dt, day_errors))
            typer.echo(f"  Day {dt}: {len(day_errors)} failure(s), continuing...")

    # Summary
    all_errors = [err for _, errs in day_failures for err in errs]
    typer.echo(f"\n--- Summary ---")
    typer.echo(f"Days:      {total_days}")
    typer.echo(f"Processed: {total_processed}/{total_manifests}")
    if day_failures:
        typer.echo(f"Failed days: {len(day_failures)}")
        for dt, errs in day_failures:
            typer.echo(f"  {dt}:")
            for run_id, err in errs:
                typer.echo(f"    {run_id}: {err}")
        raise typer.Exit(code=1)
    else:
        typer.echo("All manifests processed successfully.")


@app.command(name="catchup")
def catchup(
    platform: Annotated[
        str,
        typer.Option(
            "--platform",
            help=f"Platform to catch up ({', '.join(_VALID_PLATFORMS)}).",
        ),
    ],
    entity: Annotated[
        str,
        typer.Option(
            "--entity",
            help=f"Entity to catch up ({', '.join(_VALID_ENTITIES)}).",
        ),
    ],
    from_date: Annotated[
        str | None,
        typer.Option(
            "--from-date",
            help="Override start date instead of auto-detecting (YYYY-MM-DD).",
        ),
    ] = None,
    bucket: Annotated[
        str | None,
        typer.Option(
            "--bucket",
            help="S3 bucket name (defaults to BRONZE_BUCKET env var).",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview manifests that would be processed without writing.",
        ),
    ] = False,
    force_reprocess: Annotated[
        bool,
        typer.Option(
            "--force-reprocess",
            help="Reprocess manifests even if already processed.",
        ),
    ] = False,
    skip_quality_checks: Annotated[
        bool,
        typer.Option(
            "--skip-quality-checks",
            help="Skip quality checks during processing.",
        ),
    ] = False,
) -> None:
    """Catch up Silver processing to present.

    Auto-detects the latest processed date from the state store and
    discovers only new Bronze manifests from that date forward. Uses
    memory-efficient file-by-file processing for stream entities.

    \b
    Examples:
      prediction-data silver catchup --platform polymarket --entity trades
      prediction-data silver catchup --platform polymarket --entity trades --dry-run
      prediction-data silver catchup --platform polymarket --entity trades --from-date 2025-01-15
    """
    from prediction_data.core.logging import configure_logging

    configure_logging()

    _validate_platform_entity(platform, entity)

    resolved_bucket = bucket or os.environ.get("BRONZE_BUCKET", "")
    if not resolved_bucket:
        typer.echo("Error: --bucket or BRONZE_BUCKET env var required.", err=True)
        raise typer.Exit(code=1)

    asyncio.run(
        _run_catchup(
            platform=platform,
            entity=entity,
            from_date=from_date,
            bucket=resolved_bucket,
            dry_run=dry_run,
            force_reprocess=force_reprocess,
            skip_quality_checks=skip_quality_checks,
        )
    )


async def _run_catchup(
    *,
    platform: str,
    entity: str,
    from_date: str | None,
    bucket: str,
    dry_run: bool,
    force_reprocess: bool,
    skip_quality_checks: bool,
) -> None:
    """Auto-detect latest processed date and catch up to present."""
    from prediction_data.silver.catalog import get_catalog
    from prediction_data.silver.discovery import (
        CATALOG_ENTITIES,
        discover_manifests,
        select_manifests_for_day,
    )
    from prediction_data.silver.processor import (
        ProcessingError,
        process_manifest,
        process_manifest_chunked,
    )
    from prediction_data.silver.state import SilverStateStore
    from prediction_data.storage import S3Client

    s3 = S3Client(bucket=bucket)

    # Load state store to find latest processed date
    state_store = SilverStateStore(s3, platform, entity)
    await state_store.load()

    if from_date:
        start_date = from_date
        typer.echo(f"Using override start date: {start_date}")
    else:
        latest = state_store.latest_processed_date()
        if latest:
            start_date = latest
            typer.echo(f"Latest processed date: {latest}")
        else:
            start_date = "2022-01-01"
            typer.echo("No prior processing found — starting from 2022-01-01")

    end_date = date.today().isoformat()

    typer.echo(
        f"Discovering manifests for {platform}/{entity} "
        f"({start_date} to {end_date})..."
    )

    manifests = await discover_manifests(
        s3, platform, entity, start_date=start_date, end_date=end_date
    )

    if not manifests:
        typer.echo("No manifests found.")
        return

    typer.echo(f"Found {len(manifests)} manifest(s).")

    # Filter out already-processed manifests unless --force-reprocess
    if not force_reprocess:
        before = len(manifests)
        manifests = [m for m in manifests if not state_store.is_processed(m.run_id)]
        skipped = before - len(manifests)
        if skipped:
            typer.echo(f"Skipping {skipped} already-processed manifest(s).")

    if not manifests:
        typer.echo("All manifests already processed. Silver is up to date.")
        return

    # Group manifests by day
    days = [
        (dt_val, list(group))
        for dt_val, group in itertools.groupby(manifests, key=lambda m: m.dt)
    ]
    total_days = len(days)

    if dry_run:
        total_unprocessed = sum(
            len(select_manifests_for_day(dm, entity)) for _, dm in days
        )
        typer.echo(
            f"\nDry run — {total_unprocessed} manifest(s) to process "
            f"across {total_days} day(s):"
        )
        for dt_val, day_manifests in days:
            selected = select_manifests_for_day(day_manifests, entity)
            typer.echo(f"  {dt_val}: {len(selected)} manifest(s)")
            for m in selected:
                typer.echo(f"    run_id={m.run_id} rows={m.row_count}")
        return

    catalog = get_catalog()
    is_stream = entity not in CATALOG_ENTITIES

    # Pre-load markets reference for trades processing
    markets_lookup = None
    if entity == "trades":
        from prediction_data.silver.polymarket.markets_reference import (
            load_markets_reference,
        )

        typer.echo("Pre-loading markets reference for trades processing...")
        try:
            markets_lookup = await load_markets_reference(s3)
        except Exception as e:
            typer.echo(f"Error loading markets reference: {e}", err=True)
            raise typer.Exit(code=1) from e

        if len(markets_lookup) == 0:
            typer.echo(
                "Error: Markets reference is empty — no Bronze markets data found. "
                "Ingest markets before processing trades.",
                err=True,
            )
            raise typer.Exit(code=1)

        typer.echo(f"Markets reference loaded: {markets_lookup.coverage_stats}")

    total_processed = 0
    total_manifests = sum(
        len(select_manifests_for_day(dm, entity)) for _, dm in days
    )
    day_failures: list[tuple[str, list[tuple[str, str]]]] = []

    for day_idx, (dt_val, day_manifests) in enumerate(days, 1):
        day_manifests = select_manifests_for_day(day_manifests, entity)
        if not day_manifests:
            continue

        typer.echo(
            f"\n=== Day {day_idx}/{total_days}: {dt_val} "
            f"({len(day_manifests)} manifest(s)) ==="
        )

        day_errors: list[tuple[str, str]] = []

        for m in day_manifests:
            progress = total_processed + len(day_errors) + 1
            label = f"[{progress}/{total_manifests}]"
            typer.echo(f"  {label} Processing dt={m.dt} run_id={m.run_id} ...")

            try:
                if is_stream:
                    result = await process_manifest_chunked(
                        m, s3, catalog,
                        skip_quality_checks=skip_quality_checks,
                        markets_lookup=markets_lookup,
                    )
                else:
                    result = await process_manifest(
                        m, s3, catalog,
                        skip_quality_checks=skip_quality_checks,
                        markets_lookup=markets_lookup,
                    )
                total_processed += 1
                typer.echo(
                    f"    OK: {result.rows_written} rows, "
                    f"{result.duplicates_dropped} dupes, "
                    f"{result.duration_seconds:.1f}s"
                )
                await state_store.mark_processed(
                    run_id=m.run_id,
                    platform=m.platform,
                    entity=m.entity,
                    dt=m.dt,
                )
            except ProcessingError as exc:
                day_errors.append((m.run_id, str(exc)))
                typer.echo(f"    FAILED: {exc}", err=True)
            finally:
                gc.collect()

        if day_errors:
            day_failures.append((dt_val, day_errors))

    # Summary
    typer.echo("\n--- Summary ---")
    typer.echo(f"Days:      {total_days}")
    typer.echo(f"Processed: {total_processed}/{total_manifests}")
    if day_failures:
        typer.echo(f"Failed days: {len(day_failures)}")
        for dt_val, errs in day_failures:
            typer.echo(f"  {dt_val}:")
            for run_id, err in errs:
                typer.echo(f"    {run_id}: {err}")
        raise typer.Exit(code=1)
    else:
        typer.echo("All manifests processed successfully.")


def _resolve_namespace(platform: str) -> str:
    """Map platform name to Iceberg namespace."""
    return f"silver_{platform}"


@app.command(name="compact")
def compact(
    table: Annotated[
        str,
        typer.Option(
            "--table",
            help="Table to compact as 'platform/entity' (e.g. polymarket/trades).",
        ),
    ],
    partition: Annotated[
        str | None,
        typer.Option(
            "--partition",
            help="Specific partition to compact (e.g. '2024-06-15').",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview compaction targets without rewriting files.",
        ),
    ] = False,
) -> None:
    """Compact small files in a Silver Iceberg table.

    Identifies partitions with excessive small files (>50 files, <64MB each)
    and rewrites them to target 256MB files.
    """
    from prediction_data.core.logging import configure_logging
    from prediction_data.silver.catalog import get_catalog
    from prediction_data.silver.maintenance import compact_table

    configure_logging()

    # Parse table argument
    parts = table.split("/")
    if len(parts) != 2:
        typer.echo(
            "Error: --table must be 'platform/entity' (e.g. polymarket/trades).",
            err=True,
        )
        raise typer.Exit(code=1)

    platform, entity = parts
    _validate_platform_entity(platform, entity)

    namespace = _resolve_namespace(platform)

    if dry_run:
        typer.echo("Dry run — no files will be rewritten.\n")

    typer.echo(f"Scanning {namespace}.{entity} for compaction targets...")

    try:
        catalog = get_catalog()
        results = compact_table(
            catalog,
            namespace,
            entity,
            partition=partition,
            dry_run=dry_run,
        )
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e

    _print_compaction_results(results, dry_run=dry_run)


def _print_compaction_results(
    results: list[CompactionResult],
    *,
    dry_run: bool,
) -> None:
    """Print compaction results summary."""

    compacted = [r for r in results if not r.skipped]
    skipped = [r for r in results if r.skipped]

    if not compacted and not skipped:
        typer.echo("No partitions found.")
        return

    if skipped:
        typer.echo(f"\nSkipped {len(skipped)} partition(s) (below threshold).")

    if not compacted:
        typer.echo("No partitions need compaction.")
        return

    typer.echo(f"\n{'Would compact' if dry_run else 'Compacted'} {len(compacted)} partition(s):")
    total_bytes_saved = 0
    for r in compacted:
        saved = r.bytes_before - r.bytes_after
        total_bytes_saved += saved
        if dry_run:
            typer.echo(
                f"  {r.partition}: {r.files_before} files, "
                f"{r.bytes_before / 1024 / 1024:.1f} MB"
            )
        else:
            typer.echo(
                f"  {r.partition}: {r.files_before} -> {r.files_after} files, "
                f"saved {saved / 1024 / 1024:.1f} MB, "
                f"{r.duration_seconds:.1f}s"
            )

    if not dry_run and total_bytes_saved > 0:
        typer.echo(f"\nTotal space saved: {total_bytes_saved / 1024 / 1024:.1f} MB")


@app.command(name="expire-snapshots")
def expire_snapshots_cmd(
    table: Annotated[
        str,
        typer.Option(
            "--table",
            help="Table as 'platform/entity' (e.g. polymarket/trades).",
        ),
    ],
    older_than_days: Annotated[
        int,
        typer.Option(
            "--older-than-days",
            help="Expire snapshots older than this many days (default 7).",
        ),
    ] = 7,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview which snapshots would be expired without committing.",
        ),
    ] = False,
) -> None:
    """Expire old snapshots from a Silver Iceberg table.

    Removes snapshots older than the retention period to control metadata size.
    Protected snapshots (branch/tag heads) are never expired.
    """
    from prediction_data.core.logging import configure_logging
    from prediction_data.silver.catalog import get_catalog
    from prediction_data.silver.maintenance import expire_snapshots

    configure_logging()

    parts = table.split("/")
    if len(parts) != 2:
        typer.echo(
            "Error: --table must be 'platform/entity' (e.g. polymarket/trades).",
            err=True,
        )
        raise typer.Exit(code=1)

    platform, entity = parts
    _validate_platform_entity(platform, entity)

    namespace = _resolve_namespace(platform)

    if dry_run:
        typer.echo("Dry run — no snapshots will be expired.\n")

    typer.echo(
        f"Expiring snapshots older than {older_than_days} day(s) "
        f"from {namespace}.{entity}..."
    )

    try:
        catalog = get_catalog()
        result = expire_snapshots(
            catalog,
            namespace,
            entity,
            older_than_days=older_than_days,
            dry_run=dry_run,
        )
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e

    _print_expiration_result(result, dry_run=dry_run)


def _print_expiration_result(
    result: SnapshotExpirationResult,
    *,
    dry_run: bool,
) -> None:
    """Print snapshot expiration results."""
    action = "Would expire" if dry_run else "Expired"
    typer.echo(
        f"\n{action} {result.snapshots_expired} snapshot(s) "
        f"(cutoff: {result.older_than.strftime('%Y-%m-%d %H:%M:%S UTC')})."
    )
    typer.echo(f"Snapshots before: {result.snapshots_before}")
    typer.echo(f"Snapshots after:  {result.snapshots_after}")
    if not dry_run and result.duration_seconds > 0:
        typer.echo(f"Duration: {result.duration_seconds:.1f}s")


@app.command(name="remove-orphans")
def remove_orphans_cmd(
    table: Annotated[
        str,
        typer.Option(
            "--table",
            help="Table as 'platform/entity' (e.g. polymarket/trades).",
        ),
    ],
    older_than_days: Annotated[
        int,
        typer.Option(
            "--older-than-days",
            help="Only delete orphans older than this many days (default 7).",
        ),
    ] = 7,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Report orphan files without deleting them.",
        ),
    ] = False,
) -> None:
    """Detect and remove orphaned data files from a Silver Iceberg table.

    Orphan files are Parquet files in the table's data directory that are
    not referenced by any snapshot. Only files older than the safety
    threshold are deleted.
    """
    from prediction_data.core.logging import configure_logging
    from prediction_data.silver.catalog import get_catalog
    from prediction_data.silver.maintenance import remove_orphans

    configure_logging()

    parts = table.split("/")
    if len(parts) != 2:
        typer.echo(
            "Error: --table must be 'platform/entity' (e.g. polymarket/trades).",
            err=True,
        )
        raise typer.Exit(code=1)

    platform, entity = parts
    _validate_platform_entity(platform, entity)

    namespace = _resolve_namespace(platform)

    if dry_run:
        typer.echo("Dry run — no files will be deleted.\n")

    typer.echo(
        f"Scanning {namespace}.{entity} for orphaned data files "
        f"(older than {older_than_days} day(s))..."
    )

    try:
        catalog = get_catalog()
        result = remove_orphans(
            catalog,
            namespace,
            entity,
            older_than_days=older_than_days,
            dry_run=dry_run,
        )
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e

    _print_orphan_result(result, dry_run=dry_run)


def _print_orphan_result(
    result: OrphanCleanupResult,
    *,
    dry_run: bool,
) -> None:
    """Print orphan cleanup results."""
    if result.orphan_files_found == 0:
        typer.echo("\nNo orphan files found.")
        return

    action = "Found" if dry_run else "Deleted"
    count = result.orphan_files_found if dry_run else result.orphan_files_deleted
    mb = result.orphan_bytes / 1024 / 1024

    typer.echo(f"\n{action} {count} orphan file(s) ({mb:.1f} MB).")

    if not dry_run and result.duration_seconds > 0:
        typer.echo(f"Duration: {result.duration_seconds:.1f}s")


_VALID_OPERATIONS = {"compact", "expire", "orphans"}


@app.command(name="maintain")
def maintain(
    operations: Annotated[
        list[str] | None,
        typer.Option(
            "--op",
            help=(
                "Operations to run (compact, expire, orphans). "
                "Repeatable. Defaults to all."
            ),
        ),
    ] = None,
    expire_older_than_days: Annotated[
        int,
        typer.Option(
            "--expire-older-than-days",
            help="Retention period for snapshot expiration (default 7).",
        ),
    ] = 7,
    orphan_older_than_days: Annotated[
        int,
        typer.Option(
            "--orphan-older-than-days",
            help="Min age for orphan file deletion (default 7).",
        ),
    ] = 7,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview all operations without making changes.",
        ),
    ] = False,
) -> None:
    """Run maintenance across all Silver Iceberg tables.

    Runs compaction, snapshot expiration, and orphan cleanup for every
    registered Silver table. Designed to be invoked by cron or
    EventBridge Scheduler.

    \b
    Recommended schedules:
      - Daily:  prediction-data silver maintain --op compact
      - Weekly: prediction-data silver maintain --op expire --op orphans
      - All:    prediction-data silver maintain
    """
    from prediction_data.core.logging import configure_logging
    from prediction_data.silver.catalog import get_catalog
    from prediction_data.silver.maintenance import run_all_maintenance

    configure_logging()

    # Resolve operations
    ops = frozenset(operations) if operations else frozenset(_VALID_OPERATIONS)
    invalid = ops - _VALID_OPERATIONS
    if invalid:
        typer.echo(
            f"Error: Unknown operation(s): {', '.join(sorted(invalid))}. "
            f"Valid: {', '.join(sorted(_VALID_OPERATIONS))}",
            err=True,
        )
        raise typer.Exit(code=1)

    if dry_run:
        typer.echo("Dry run — no changes will be made.\n")

    typer.echo(f"Running maintenance: {', '.join(sorted(ops))}")
    typer.echo(f"Tables: {len(_VALID_TARGETS)}\n")

    try:
        catalog = get_catalog()
        result = run_all_maintenance(
            catalog,
            operations=ops,
            expire_older_than_days=expire_older_than_days,
            orphan_older_than_days=orphan_older_than_days,
            dry_run=dry_run,
        )
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e

    _print_maintenance_summary(result, dry_run=dry_run)

    if result.errors:
        raise typer.Exit(code=1)


def _print_maintenance_summary(
    result: MaintenanceRunResult,
    *,
    dry_run: bool,
) -> None:
    """Print full maintenance run summary."""
    typer.echo("\n--- Maintenance Summary ---")
    typer.echo(f"Tables processed: {result.tables_processed}")
    typer.echo(f"Duration: {result.duration_seconds:.1f}s")

    # Compaction summary
    compacted = [r for r in result.compaction_results if not r.skipped]
    if compacted:
        total_saved = sum(r.bytes_before - r.bytes_after for r in compacted)
        action = "Would compact" if dry_run else "Compacted"
        typer.echo(
            f"\n{action} {len(compacted)} partition(s), "
            f"saved {total_saved / 1024 / 1024:.1f} MB"
        )

    # Expiration summary
    total_expired = sum(r.snapshots_expired for r in result.expiration_results)
    if total_expired:
        action = "Would expire" if dry_run else "Expired"
        typer.echo(f"{action} {total_expired} snapshot(s)")

    # Orphan summary
    total_orphans = sum(r.orphan_files_found for r in result.orphan_results)
    if total_orphans:
        total_bytes = sum(r.orphan_bytes for r in result.orphan_results)
        action = "Found" if dry_run else "Deleted"
        typer.echo(f"{action} {total_orphans} orphan file(s) ({total_bytes / 1024 / 1024:.1f} MB)")

    # Errors
    if result.errors:
        typer.echo(f"\nErrors ({len(result.errors)}):")
        for table, msg in result.errors:
            typer.echo(f"  {table}: {msg}")
    else:
        typer.echo("\nAll operations completed successfully.")
