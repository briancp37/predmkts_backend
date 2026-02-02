"""Silver layer CLI commands."""

from __future__ import annotations

import asyncio
import os
from typing import Annotated

import typer

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

    if dry_run:
        typer.echo("\nDry run — manifests that would be processed:")
        for m in manifests:
            typer.echo(f"  {m.platform}/{m.entity} dt={m.dt} run_id={m.run_id}")
        typer.echo(f"\n{len(manifests)} manifest(s) would be processed.")
        return

    catalog = get_catalog()

    processed = 0
    failures: list[tuple[str, str]] = []

    for i, m in enumerate(manifests, 1):
        label = f"[{i}/{len(manifests)}] {m.platform}/{m.entity} dt={m.dt}"
        typer.echo(f"\nProcessing {label} ...")

        try:
            result = await process_manifest(m, s3, catalog)
            processed += 1
            typer.echo(
                f"  OK: {result.rows_written} rows written, "
                f"snapshot_id={result.snapshot_id}, "
                f"{result.duplicates_dropped} dupes dropped, "
                f"{result.duration_seconds:.1f}s"
            )
            # Mark as processed in state log
            await state_store.mark_processed(
                run_id=m.run_id,
                platform=m.platform,
                entity=m.entity,
                dt=m.dt,
            )
        except ProcessingError as exc:
            failures.append((m.run_id, str(exc)))
            typer.echo(f"  FAILED: {exc}", err=True)

    # Summary
    typer.echo(f"\n--- Summary ---")
    typer.echo(f"Processed: {processed}/{len(manifests)}")
    if failures:
        typer.echo(f"Failures:  {len(failures)}")
        for run_id, err in failures:
            typer.echo(f"  {run_id}: {err}")
        raise typer.Exit(code=1)
    else:
        typer.echo("All manifests processed successfully.")
