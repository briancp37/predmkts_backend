"""Status command group for monitoring and auditing Bronze layer data."""

from __future__ import annotations

import asyncio
import os
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
