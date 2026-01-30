"""Status command group for monitoring and auditing Bronze layer data."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Annotated, Any

import typer

app = typer.Typer(
    help="Monitor and audit Bronze layer data in S3.",
    no_args_is_help=True,
)


class Platform(str, Enum):
    """Supported prediction market platforms."""

    polymarket = "polymarket"
    kalshi = "kalshi"


class Entity(str, Enum):
    """Supported entity types."""

    trades = "trades"
    markets = "markets"
    events = "events"
    order_filled = "order_filled"


# Common CLI option types for reuse across subcommands
PlatformOption = Annotated[
    Platform | None,
    typer.Option("--platform", "-p", help="Filter by platform."),
]

EntityOption = Annotated[
    Entity | None,
    typer.Option("--entity", "-e", help="Filter by entity type."),
]

# All platform/entity combinations
ALL_PLATFORMS = [p.value for p in Platform]
ALL_ENTITIES = [e.value for e in Entity]

def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Format data as an aligned text table.

    Args:
        headers: Column header strings.
        rows: List of row data (each row is a list of column values).

    Returns:
        Formatted table string with aligned columns.
    """
    if not rows:
        return " | ".join(headers) + "\n(no data)"

    # Compute column widths from headers and data
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(val))

    def _fmt_row(values: list[str]) -> str:
        return " | ".join(v.ljust(col_widths[i]) for i, v in enumerate(values))

    separator = "-+-".join("-" * w for w in col_widths)
    lines = [_fmt_row(headers), separator]
    lines.extend(_fmt_row(row) for row in rows)
    return "\n".join(lines)


def _date_range(start: date, end: date) -> list[date]:
    """Generate list of dates from start to end inclusive."""
    dates: list[date] = []
    current = start
    while current <= end:
        dates.append(current)
        current += timedelta(days=1)
    return dates


def _resolve_filters(
    platform: Platform | None, entity: Entity | None
) -> list[tuple[str, str]]:
    """Resolve platform/entity filters to list of (platform, entity) pairs."""
    platforms = [platform.value] if platform else ALL_PLATFORMS
    entities = [entity.value] if entity else ALL_ENTITIES
    return [(p, e) for p in platforms for e in entities]


async def _get_coverage_data(
    s3_client: Any,
    platform: str,
    entity: str,
    dates: list[date],
) -> list[dict[str, Any]]:
    """Get coverage data for a platform/entity over a date range.

    For each date, checks if data exists and reads manifest metadata.

    Returns list of dicts with keys: date, platform, entity, runs, total_rows, latest_run_time.
    """
    results: list[dict[str, Any]] = []
    for d in dates:
        dt_str = d.isoformat()
        prefix = f"bronze/{platform}/{entity}/dt={dt_str}/"
        keys = await s3_client.list_keys(prefix)
        manifest_keys = [k for k in keys if k.endswith("manifest.json")]

        if not manifest_keys:
            results.append({
                "date": dt_str,
                "platform": platform,
                "entity": entity,
                "runs": 0,
                "total_rows": 0,
                "latest_run_time": None,
            })
            continue

        total_rows = 0
        latest_time = None
        for mk in manifest_keys:
            manifest = await s3_client.download_manifest(mk)
            total_rows += manifest.row_count
            if latest_time is None or manifest.generated_at > latest_time:
                latest_time = manifest.generated_at

        results.append({
            "date": dt_str,
            "platform": platform,
            "entity": entity,
            "runs": len(manifest_keys),
            "total_rows": total_rows,
            "latest_run_time": latest_time.isoformat() if latest_time else "",
        })

    return results


@app.command(name="coverage")
def coverage(
    start_date: Annotated[
        str,
        typer.Option("--start-date", help="Start date (YYYY-MM-DD, inclusive)."),
    ],
    end_date: Annotated[
        str,
        typer.Option("--end-date", help="End date (YYYY-MM-DD, inclusive)."),
    ],
    platform: PlatformOption = None,
    entity: EntityOption = None,
    bucket: Annotated[
        str | None,
        typer.Option("--bucket", help="S3 bucket (defaults to BRONZE_BUCKET env var)."),
    ] = None,
) -> None:
    """Show which dates have data, which are missing, and row counts."""
    from prediction_data.storage.s3 import S3Client

    bucket = bucket or os.environ.get("BRONZE_BUCKET", "")
    if not bucket:
        typer.echo("Error: --bucket or BRONZE_BUCKET env var required.", err=True)
        raise typer.Exit(code=1)

    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError as exc:
        typer.echo(f"Error: Invalid date format: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if start > end:
        typer.echo("Error: --start-date must be <= --end-date.", err=True)
        raise typer.Exit(code=1)

    dates = _date_range(start, end)
    combos = _resolve_filters(platform, entity)

    all_rows: list[list[str]] = []
    total_dates = 0
    dates_with_data = 0
    missing_dates = 0
    grand_total_rows = 0

    async def _run() -> None:
        nonlocal total_dates, dates_with_data, missing_dates, grand_total_rows
        async with S3Client(bucket=bucket) as client:
            for plat, ent in combos:
                results = await _get_coverage_data(client, plat, ent, dates)
                for r in results:
                    total_dates += 1
                    if r["runs"] > 0:
                        dates_with_data += 1
                    else:
                        missing_dates += 1
                    grand_total_rows += r["total_rows"]

                    status = "OK" if r["runs"] > 0 else "MISSING"
                    all_rows.append([
                        r["date"],
                        r["platform"],
                        r["entity"],
                        str(r["runs"]),
                        str(r["total_rows"]),
                        r["latest_run_time"] or "-",
                        status,
                    ])

    asyncio.run(_run())

    headers = ["date", "platform", "entity", "runs", "total_rows", "latest_run_time", "status"]
    typer.echo(format_table(headers, all_rows))
    typer.echo(
        f"\nSummary: {total_dates} date(s), {dates_with_data} with data, "
        f"{missing_dates} missing, {grand_total_rows} total rows"
    )


async def _get_runs_data(
    s3_client: Any,
    combos: list[tuple[str, str]],
    dt_filter: str | None,
    last: int,
) -> list[dict[str, Any]]:
    """Fetch run metadata from manifests across platform/entity combos.

    Returns list of dicts sorted by generated_at descending.
    """
    runs: list[dict[str, Any]] = []
    for plat, ent in combos:
        if dt_filter:
            prefix = f"bronze/{plat}/{ent}/dt={dt_filter}/"
            keys = await s3_client.list_keys(prefix)
        else:
            prefix = f"bronze/{plat}/{ent}/"
            keys = await s3_client.list_keys(prefix)

        manifest_keys = [k for k in keys if k.endswith("manifest.json")]
        for mk in manifest_keys:
            manifest = await s3_client.download_manifest(mk)
            runs.append({
                "run_id": manifest.run_id,
                "platform": manifest.platform,
                "entity": manifest.entity,
                "dt": manifest.dt,
                "row_count": manifest.row_count,
                "generated_at": manifest.generated_at,
            })

    # Sort by generated_at descending
    runs.sort(key=lambda r: r["generated_at"], reverse=True)

    # Apply limit only when no dt filter
    if not dt_filter:
        runs = runs[:last]

    return runs


@app.command(name="runs")
def runs(
    platform: PlatformOption = None,
    entity: EntityOption = None,
    dt: Annotated[
        str | None,
        typer.Option("--dt", help="Filter to a specific date (YYYY-MM-DD). Shows all runs for that date."),
    ] = None,
    last: Annotated[
        int,
        typer.Option("--last", help="Number of recent runs to show (default 20, ignored with --dt)."),
    ] = 20,
    bucket: Annotated[
        str | None,
        typer.Option("--bucket", help="S3 bucket (defaults to BRONZE_BUCKET env var)."),
    ] = None,
) -> None:
    """List recent ingestion runs with metadata from manifests."""
    from prediction_data.storage.s3 import S3Client

    bucket = bucket or os.environ.get("BRONZE_BUCKET", "")
    if not bucket:
        typer.echo("Error: --bucket or BRONZE_BUCKET env var required.", err=True)
        raise typer.Exit(code=1)

    if dt:
        try:
            date.fromisoformat(dt)
        except ValueError as exc:
            typer.echo(f"Error: Invalid date format: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    combos = _resolve_filters(platform, entity)

    run_list: list[dict[str, Any]] = []

    async def _run() -> None:
        nonlocal run_list
        async with S3Client(bucket=bucket) as client:
            run_list = await _get_runs_data(client, combos, dt, last)

    asyncio.run(_run())

    rows = [
        [
            r["run_id"],
            r["platform"],
            r["entity"],
            r["dt"],
            str(r["row_count"]),
            r["generated_at"].isoformat(),
        ]
        for r in run_list
    ]

    headers = ["run_id", "platform", "entity", "dt", "row_count", "generated_at"]
    typer.echo(format_table(headers, rows))


async def _find_manifest_by_run_id(
    s3_client: Any,
    run_id: str,
    combos: list[tuple[str, str]],
) -> tuple[str, Any] | None:
    """Search S3 for a manifest matching the given run_id (supports prefix matching).

    Returns (manifest_key, Manifest) or None if not found.
    """
    for plat, ent in combos:
        prefix = f"bronze/{plat}/{ent}/"
        keys = await s3_client.list_keys(prefix)
        manifest_keys = [k for k in keys if k.endswith("manifest.json")]
        for mk in manifest_keys:
            if run_id in mk:
                manifest = await s3_client.download_manifest(mk)
                return mk, manifest
    return None


@app.command(name="show-run")
def show_run(
    run_id: Annotated[
        str,
        typer.Argument(help="Run ID to look up (supports partial prefix matching)."),
    ],
    platform: PlatformOption = None,
    entity: EntityOption = None,
    bucket: Annotated[
        str | None,
        typer.Option("--bucket", help="S3 bucket (defaults to BRONZE_BUCKET env var)."),
    ] = None,
) -> None:
    """Display full details of a specific ingestion run."""
    from prediction_data.storage.s3 import S3Client

    bucket = bucket or os.environ.get("BRONZE_BUCKET", "")
    if not bucket:
        typer.echo("Error: --bucket or BRONZE_BUCKET env var required.", err=True)
        raise typer.Exit(code=1)

    combos = _resolve_filters(platform, entity)
    result: tuple[str, Any] | None = None

    async def _run() -> None:
        nonlocal result
        async with S3Client(bucket=bucket) as client:
            result = await _find_manifest_by_run_id(client, run_id, combos)

    asyncio.run(_run())

    if result is None:
        typer.echo(f"Error: No run found matching '{run_id}'.", err=True)
        typer.echo("Hint: Use 'prediction-data status runs' to list available runs.", err=True)
        raise typer.Exit(code=1)

    manifest_key, manifest = result

    # Display manifest details
    typer.echo("Run Details")
    typer.echo("=" * 40)
    typer.echo(f"  run_id:       {manifest.run_id}")
    typer.echo(f"  platform:     {manifest.platform}")
    typer.echo(f"  entity:       {manifest.entity}")
    typer.echo(f"  dt:           {manifest.dt}")
    typer.echo(f"  generated_at: {manifest.generated_at.isoformat()}")
    typer.echo(f"  row_count:    {manifest.row_count}")

    # Source metadata
    typer.echo("")
    typer.echo("Source")
    typer.echo("-" * 40)
    typer.echo(f"  api_base_url: {manifest.source.api_base_url}")
    typer.echo(f"  pagination:   {manifest.source.pagination}")
    typer.echo(f"  cursor:       {manifest.source.cursor or '(none)'}")

    # Part files
    typer.echo("")
    typer.echo(f"Files ({len(manifest.files)})")
    typer.echo("-" * 40)
    for f in manifest.files:
        typer.echo(f"  s3://{f.bucket}/{f.key}")


@dataclass
class ValidationResult:
    """Accumulates validation findings across all checked prefixes."""

    valid_runs: int = 0
    invalid_manifests: int = 0
    missing_parts: int = 0
    orphaned_files: int = 0
    empty_runs: int = 0
    errors: list[str] = field(default_factory=list)


async def _validate_data(
    s3_client: Any,
    combos: list[tuple[str, str]],
    dates: list[date],
) -> ValidationResult:
    """Validate manifest integrity and detect orphaned/incomplete data.

    For each date/platform/entity combo:
    - Checks every run directory has a parseable manifest with required fields
    - Verifies every part file listed in the manifest exists in S3
    - Detects orphaned data files (in directories without a manifest)
    - Flags manifests with row_count=0 as empty runs
    """
    from pydantic import ValidationError

    result = ValidationResult()

    for plat, ent in combos:
        for d in dates:
            dt_str = d.isoformat()
            prefix = f"bronze/{plat}/{ent}/dt={dt_str}/"
            all_keys = await s3_client.list_keys(prefix)

            if not all_keys:
                continue

            # Group keys by run directory
            run_dirs: dict[str, list[str]] = {}
            for key in all_keys:
                # Extract run_id dir: everything up to and including run_id=xxx/
                parts = key[len(prefix):]
                run_dir = parts.split("/")[0] if "/" in parts else ""
                if run_dir:
                    run_dirs.setdefault(run_dir, []).append(key)

            for _run_dir, keys in run_dirs.items():
                manifest_keys = [k for k in keys if k.endswith("manifest.json")]
                data_keys = [k for k in keys if not k.endswith("manifest.json")]

                if not manifest_keys:
                    # Orphaned files — no manifest in this run directory
                    result.orphaned_files += len(data_keys)
                    for dk in data_keys:
                        result.errors.append(f"Orphaned file (no manifest): {dk}")
                    continue

                # Try to parse manifest
                mk = manifest_keys[0]
                try:
                    manifest = await s3_client.download_manifest(mk)
                except (ValidationError, Exception) as exc:
                    result.invalid_manifests += 1
                    result.errors.append(f"Invalid manifest {mk}: {exc}")
                    continue

                # Check empty runs
                if manifest.row_count == 0:
                    result.empty_runs += 1
                    result.errors.append(f"Empty run (row_count=0): {mk}")

                # Verify all part files listed in manifest exist in S3
                existing_keys_set = set(all_keys)
                for file_ref in manifest.files:
                    if file_ref.key not in existing_keys_set:
                        result.missing_parts += 1
                        result.errors.append(f"Missing part file: {file_ref.key} (referenced in {mk})")

                result.valid_runs += 1

    return result


@app.command(name="validate")
def validate(
    start_date: Annotated[
        str,
        typer.Option("--start-date", help="Start date (YYYY-MM-DD, inclusive)."),
    ],
    end_date: Annotated[
        str,
        typer.Option("--end-date", help="End date (YYYY-MM-DD, inclusive)."),
    ],
    platform: PlatformOption = None,
    entity: EntityOption = None,
    bucket: Annotated[
        str | None,
        typer.Option("--bucket", help="S3 bucket (defaults to BRONZE_BUCKET env var)."),
    ] = None,
) -> None:
    """Check manifest integrity and detect orphaned or incomplete data."""
    from prediction_data.storage.s3 import S3Client

    bucket = bucket or os.environ.get("BRONZE_BUCKET", "")
    if not bucket:
        typer.echo("Error: --bucket or BRONZE_BUCKET env var required.", err=True)
        raise typer.Exit(code=1)

    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError as exc:
        typer.echo(f"Error: Invalid date format: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if start > end:
        typer.echo("Error: --start-date must be <= --end-date.", err=True)
        raise typer.Exit(code=1)

    dates = _date_range(start, end)
    combos = _resolve_filters(platform, entity)
    vr = ValidationResult()

    async def _run() -> None:
        nonlocal vr
        async with S3Client(bucket=bucket) as client:
            vr = await _validate_data(client, combos, dates)

    asyncio.run(_run())

    # Display results
    typer.echo("Validation Results")
    typer.echo("=" * 40)
    typer.echo(f"  Valid runs:         {vr.valid_runs}")
    typer.echo(f"  Invalid manifests:  {vr.invalid_manifests}")
    typer.echo(f"  Missing part files: {vr.missing_parts}")
    typer.echo(f"  Orphaned files:     {vr.orphaned_files}")
    typer.echo(f"  Empty runs:         {vr.empty_runs}")

    if vr.errors:
        typer.echo("")
        typer.echo("Errors")
        typer.echo("-" * 40)
        for err in vr.errors:
            typer.echo(f"  - {err}")

    has_errors = vr.invalid_manifests > 0 or vr.missing_parts > 0 or vr.orphaned_files > 0
    if has_errors:
        raise typer.Exit(code=1)
