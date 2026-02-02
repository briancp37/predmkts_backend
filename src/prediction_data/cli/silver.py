"""Silver layer CLI commands."""

from __future__ import annotations

import asyncio
import itertools
import os
from typing import TYPE_CHECKING, Annotated

import typer

if TYPE_CHECKING:
    from prediction_data.silver.maintenance import CompactionResult

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
) -> None:
    """Process Bronze manifests into Silver Iceberg tables.

    Specify either --dt for a single day, or --start-date/--end-date for a
    date range.
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
) -> None:
    """Discover and process Bronze manifests for the given scope."""
    from prediction_data.silver.catalog import get_catalog
    from prediction_data.silver.discovery import discover_manifests
    from prediction_data.silver.processor import ProcessingError, process_manifest
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
            typer.echo(f"  {dt}: {len(day_manifests)} manifest(s)")
            for m in day_manifests:
                typer.echo(f"    run_id={m.run_id}")
        return

    catalog = get_catalog()

    total_processed = 0
    total_manifests = len(manifests)
    day_failures: list[tuple[str, list[tuple[str, str]]]] = []

    for day_idx, (dt, day_manifests) in enumerate(days, 1):
        typer.echo(
            f"\n=== Day {day_idx}/{total_days}: {dt} "
            f"({len(day_manifests)} manifest(s)) ==="
        )

        day_errors: list[tuple[str, str]] = []

        for m in day_manifests:
            total_processed_so_far = total_processed + len(day_errors)
            progress = total_processed_so_far + 1
            label = f"[{progress}/{total_manifests}] {m.platform}/{m.entity} dt={m.dt}"
            typer.echo(f"  Processing {label} ...")

            try:
                result = await process_manifest(m, s3, catalog)
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
