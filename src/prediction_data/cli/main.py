"""Main CLI application for prediction-data."""

import asyncio
import calendar
from datetime import date, datetime, timedelta
from typing import Annotated

from dotenv import load_dotenv

load_dotenv()

import typer

from prediction_data import __version__
from prediction_data.cli.gold import app as gold_app
from prediction_data.cli.silver import app as silver_app
from prediction_data.cli.status import app as status_app

app = typer.Typer(
    name="prediction-data",
    help="Data pipeline for prediction market data ingestion and processing.",
    no_args_is_help=True,
)

# Status command group
app.add_typer(status_app, name="status")

# Silver command group
app.add_typer(silver_app, name="silver")

# Gold command group
app.add_typer(gold_app, name="gold")

# Ingest command group placeholder
ingest_app = typer.Typer(
    help="Ingest data from prediction market platforms.",
    no_args_is_help=True,
)
app.add_typer(ingest_app, name="ingest")

# Backfill command group
backfill_app = typer.Typer(
    help="Backfill historical data over date ranges.",
    no_args_is_help=True,
)
app.add_typer(backfill_app, name="backfill")


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(f"prediction-data {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-v",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """Prediction Data CLI - Data pipeline for prediction market data."""


@ingest_app.command(name="polymarket-trades")
def polymarket_trades(
    dt: Annotated[
        str,
        typer.Option(
            "--dt",
            help="Data partition date in YYYY-MM-DD format.",
        ),
    ],
    bucket: Annotated[
        str | None,
        typer.Option(
            "--bucket",
            help="S3 bucket name (defaults to BRONZE_BUCKET env var).",
        ),
    ] = None,
    market: Annotated[
        str | None,
        typer.Option(
            "--market",
            help="Comma-separated condition IDs to filter by.",
        ),
    ] = None,
    event_id: Annotated[
        str | None,
        typer.Option(
            "--event-id",
            help="Comma-separated event IDs to filter by.",
        ),
    ] = None,
    taker_only: Annotated[
        bool,
        typer.Option(
            "--taker-only/--all-trades",
            help="Whether to only include taker trades.",
        ),
    ] = True,
) -> None:
    """Ingest Polymarket trades for a given date."""
    from prediction_data.bronze.polymarket.ingest import run_ingest_trades
    from prediction_data.core.logging import configure_logging

    configure_logging()

    try:
        run_id = run_ingest_trades(
            dt,
            bucket=bucket,
            market=market,
            event_id=event_id,
            taker_only=taker_only,
        )
        typer.echo(run_id)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@ingest_app.command(name="polymarket-markets")
def polymarket_markets(
    dt: Annotated[
        str,
        typer.Option(
            "--dt",
            help="Data partition date in YYYY-MM-DD format.",
        ),
    ],
    bucket: Annotated[
        str | None,
        typer.Option(
            "--bucket",
            help="S3 bucket name (defaults to BRONZE_BUCKET env var).",
        ),
    ] = None,
    include_closed: Annotated[
        bool,
        typer.Option(
            "--include-closed/--active-only",
            help="Whether to include closed/resolved markets.",
        ),
    ] = True,
) -> None:
    """Ingest Polymarket markets snapshot for a given date."""
    from prediction_data.bronze.polymarket.ingest import run_ingest_markets
    from prediction_data.core.logging import configure_logging

    configure_logging()

    try:
        run_id = run_ingest_markets(
            dt,
            bucket=bucket,
            include_closed=include_closed,
        )
        typer.echo(run_id)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@ingest_app.command(name="polymarket-events")
def polymarket_events(
    dt: Annotated[
        str,
        typer.Option(
            "--dt",
            help="Data partition date in YYYY-MM-DD format.",
        ),
    ],
    bucket: Annotated[
        str | None,
        typer.Option(
            "--bucket",
            help="S3 bucket name (defaults to BRONZE_BUCKET env var).",
        ),
    ] = None,
    include_closed: Annotated[
        bool,
        typer.Option(
            "--include-closed/--active-only",
            help="Whether to include closed/resolved events.",
        ),
    ] = True,
) -> None:
    """Ingest Polymarket events snapshot for a given date."""
    from prediction_data.bronze.polymarket.ingest import run_ingest_events
    from prediction_data.core.logging import configure_logging

    configure_logging()

    try:
        run_id = run_ingest_events(
            dt,
            bucket=bucket,
            include_closed=include_closed,
        )
        typer.echo(run_id)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@ingest_app.command(name="polymarket-order-filled")
def polymarket_order_filled(
    dt: Annotated[
        str,
        typer.Option(
            "--dt",
            help="Data partition date in YYYY-MM-DD format.",
        ),
    ],
    bucket: Annotated[
        str | None,
        typer.Option(
            "--bucket",
            help="S3 bucket name (defaults to BRONZE_BUCKET env var).",
        ),
    ] = None,
) -> None:
    """Ingest Polymarket order filled events for a given date."""
    from prediction_data.bronze.polymarket.ingest import run_ingest_order_filled
    from prediction_data.core.logging import configure_logging

    configure_logging()

    try:
        run_id = run_ingest_order_filled(dt, bucket=bucket)
        typer.echo(run_id)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@ingest_app.command(name="kalshi-trades")
def kalshi_trades(
    dt: Annotated[
        str,
        typer.Option(
            "--dt",
            help="Data partition date in YYYY-MM-DD format.",
        ),
    ],
    bucket: Annotated[
        str | None,
        typer.Option(
            "--bucket",
            help="S3 bucket name (defaults to BRONZE_BUCKET env var).",
        ),
    ] = None,
    ticker: Annotated[
        str | None,
        typer.Option(
            "--ticker",
            help="Market ticker to filter by.",
        ),
    ] = None,
    min_ts: Annotated[
        int | None,
        typer.Option(
            "--min-ts",
            help="Minimum Unix timestamp to filter trades.",
        ),
    ] = None,
    max_ts: Annotated[
        int | None,
        typer.Option(
            "--max-ts",
            help="Maximum Unix timestamp to filter trades.",
        ),
    ] = None,
) -> None:
    """Ingest Kalshi trades for a given date."""
    from prediction_data.bronze.kalshi.ingest import run_ingest_trades
    from prediction_data.core.logging import configure_logging

    configure_logging()

    try:
        run_id = run_ingest_trades(
            dt,
            bucket=bucket,
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
        )
        typer.echo(run_id)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@ingest_app.command(name="kalshi-markets")
def kalshi_markets(
    dt: Annotated[
        str,
        typer.Option(
            "--dt",
            help="Data partition date in YYYY-MM-DD format.",
        ),
    ],
    bucket: Annotated[
        str | None,
        typer.Option(
            "--bucket",
            help="S3 bucket name (defaults to BRONZE_BUCKET env var).",
        ),
    ] = None,
    event_ticker: Annotated[
        str | None,
        typer.Option(
            "--event-ticker",
            help="Event ticker to filter by.",
        ),
    ] = None,
    series_ticker: Annotated[
        str | None,
        typer.Option(
            "--series-ticker",
            help="Series ticker to filter by.",
        ),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option(
            "--status",
            help="Market status to filter by (unopened, open, paused, closed, settled).",
        ),
    ] = None,
) -> None:
    """Ingest Kalshi markets snapshot for a given date."""
    from prediction_data.bronze.kalshi.ingest import run_ingest_markets
    from prediction_data.core.logging import configure_logging

    configure_logging()

    try:
        run_id = run_ingest_markets(
            dt,
            bucket=bucket,
            event_ticker=event_ticker,
            series_ticker=series_ticker,
            status=status,
        )
        typer.echo(run_id)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@ingest_app.command(name="kalshi-events")
def kalshi_events(
    dt: Annotated[
        str,
        typer.Option(
            "--dt",
            help="Data partition date in YYYY-MM-DD format.",
        ),
    ],
    bucket: Annotated[
        str | None,
        typer.Option(
            "--bucket",
            help="S3 bucket name (defaults to BRONZE_BUCKET env var).",
        ),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option(
            "--status",
            help="Event status to filter by (open, closed, settled).",
        ),
    ] = None,
) -> None:
    """Ingest Kalshi events snapshot for a given date."""
    from prediction_data.bronze.kalshi.ingest import run_ingest_events
    from prediction_data.core.logging import configure_logging

    configure_logging()

    try:
        run_id = run_ingest_events(
            dt,
            bucket=bucket,
            status=status,
        )
        typer.echo(run_id)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


def _date_range(start: date, end: date) -> list[date]:
    """Generate list of dates from start to end inclusive."""
    dates: list[date] = []
    current = start
    while current <= end:
        dates.append(current)
        current += timedelta(days=1)
    return dates


def _day_boundaries_ts(dt: date) -> tuple[int, int]:
    """Return (start_of_day, end_of_day) as Unix timestamps for a date."""
    start_ts = calendar.timegm(datetime(dt.year, dt.month, dt.day, 0, 0, 0).timetuple())
    end_ts = calendar.timegm(datetime(dt.year, dt.month, dt.day, 23, 59, 59).timetuple())
    return start_ts, end_ts


def _is_date_scoped_entity(entity: str) -> bool:
    """Return True if the entity uses per-day backfill (e.g. trades).

    Markets and events are full catalog fetches, not date-scoped.
    """
    return entity in {"trades", "order_filled"}


async def _run_backfill(
    *,
    platform: str,
    entity: str,
    start_date: date,
    end_date: date,
    bucket: str | None,
    dry_run: bool,
) -> list[tuple[str, str]]:
    """Run backfill for a single platform/entity combination.

    For date-scoped entities (trades), iterates over each day in the range.
    For catalog entities (markets, events), runs a single full fetch using
    today's date as the partition key.

    Returns list of (label, error_msg) for failures.
    """
    from prediction_data.core.logging import get_logger

    logger = get_logger(__name__)
    failed_days: list[tuple[str, str]] = []

    if _is_date_scoped_entity(entity):
        dates = _date_range(start_date, end_date)
        total_days = len(dates)
        for idx, d in enumerate(dates, 1):
            dt_str = d.isoformat()
            label = f"{platform}/{entity} dt={dt_str}"

            if dry_run:
                typer.echo(f"[dry-run] Would ingest {label}")
                continue

            typer.echo(f"[{idx}/{total_days}] Ingesting {label}...")
            logger.info("Backfill starting", platform=platform, entity=entity, dt=dt_str)

            try:
                run_id = await _ingest_one(
                    platform=platform, entity=entity, dt_str=dt_str, dt_date=d, bucket=bucket
                )
                typer.echo(f"OK {label} run_id={run_id}")
            except Exception as exc:
                failed_days.append((dt_str, str(exc)))
                logger.error(
                    "Backfill day failed",
                    platform=platform,
                    entity=entity,
                    dt=dt_str,
                    error=str(exc),
                )
                typer.echo(f"FAIL {label}: {exc}", err=True)
    else:
        # Catalog entities: single full fetch, partition by today's date
        dt_str = date.today().isoformat()
        label = f"{platform}/{entity} (full catalog, dt={dt_str})"

        if dry_run:
            typer.echo(f"[dry-run] Would ingest {label}")
            return failed_days

        logger.info(
            "Catalog fetch starting", platform=platform, entity=entity, dt=dt_str
        )

        try:
            run_id = await _ingest_one(
                platform=platform,
                entity=entity,
                dt_str=dt_str,
                dt_date=date.today(),
                bucket=bucket,
            )
            typer.echo(f"OK {label} run_id={run_id}")
        except Exception as exc:
            failed_days.append((entity, str(exc)))
            logger.error(
                "Catalog fetch failed",
                platform=platform,
                entity=entity,
                error=str(exc),
            )
            typer.echo(f"FAIL {label}: {exc}", err=True)

    return failed_days


async def _ingest_one(
    *,
    platform: str,
    entity: str,
    dt_str: str,
    dt_date: date,
    bucket: str | None,
) -> str:
    """Run a single ingestion for a platform/entity/date."""
    if platform == "polymarket":
        from prediction_data.bronze.polymarket import ingest as pm_ingest

        if entity == "trades":
            return await pm_ingest.ingest_trades_clob(dt_str, bucket=bucket)
        elif entity == "markets":
            return await pm_ingest.ingest_markets(dt_str, bucket=bucket)
        elif entity == "order_filled":
            return await pm_ingest.ingest_order_filled(dt_str, bucket=bucket)
        else:
            return await pm_ingest.ingest_events(dt_str, bucket=bucket)
    else:  # kalshi
        from prediction_data.bronze.kalshi import ingest as ka_ingest

        if entity == "order_filled":
            msg = "order_filled entity is only supported for polymarket"
            raise ValueError(msg)
        if entity == "trades":
            min_ts, max_ts = _day_boundaries_ts(dt_date)
            return await ka_ingest.ingest_trades(
                dt_str, bucket=bucket, min_ts=min_ts, max_ts=max_ts
            )
        elif entity == "markets":
            return await ka_ingest.ingest_markets(dt_str, bucket=bucket)
        else:
            return await ka_ingest.ingest_events(dt_str, bucket=bucket)


def _resolve_platforms(platform: str) -> list[str]:
    """Resolve platform option to list of platform names."""
    if platform == "all":
        return ["polymarket", "kalshi"]
    return [platform]


def _resolve_entities(entity: str) -> list[str]:
    """Resolve entity option to list of entity names."""
    if entity == "all":
        return ["trades", "markets", "events", "order_filled"]
    return [entity]


@backfill_app.command(name="run")
def backfill_run(
    start_date: Annotated[
        str,
        typer.Option(
            "--start-date",
            help="Start date in YYYY-MM-DD format (inclusive).",
        ),
    ],
    end_date: Annotated[
        str,
        typer.Option(
            "--end-date",
            help="End date in YYYY-MM-DD format (inclusive).",
        ),
    ],
    platform: Annotated[
        str,
        typer.Option(
            "--platform",
            help="Platform to backfill (polymarket, kalshi, or all).",
        ),
    ] = "all",
    entity: Annotated[
        str,
        typer.Option(
            "--entity",
            help="Entity type to backfill (trades, markets, events, order_filled, or all).",
        ),
    ] = "all",
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
            help="Preview planned ingestion runs without executing.",
        ),
    ] = False,
) -> None:
    """Backfill historical data over a date range for one or more platforms and entities."""
    from prediction_data.core.logging import configure_logging

    configure_logging()

    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError as exc:
        typer.echo(f"Error: Invalid date format: {exc}", err=True)
        raise typer.Exit(code=1)

    if start > end:
        typer.echo("Error: --start-date must be <= --end-date.", err=True)
        raise typer.Exit(code=1)

    valid_platforms = {"polymarket", "kalshi", "all"}
    valid_entities = {"trades", "markets", "events", "order_filled", "all"}

    if platform not in valid_platforms:
        typer.echo(f"Error: --platform must be one of {valid_platforms}", err=True)
        raise typer.Exit(code=1)
    if entity not in valid_entities:
        typer.echo(f"Error: --entity must be one of {valid_entities}", err=True)
        raise typer.Exit(code=1)

    platforms = _resolve_platforms(platform)
    entities = _resolve_entities(entity)
    total_days = (end - start).days + 1

    date_scoped = [e for e in entities if _is_date_scoped_entity(e)]
    catalog = [e for e in entities if not _is_date_scoped_entity(e)]
    parts = []
    if date_scoped:
        parts.append(f"{', '.join(date_scoped)} x {total_days} day(s)")
    if catalog:
        parts.append(f"{', '.join(catalog)} (full catalog, once)")
    typer.echo(
        f"Backfill: {len(platforms)} platform(s) — {'; '.join(parts)}"
    )

    all_failures: list[tuple[str, str]] = []

    async def _run_all() -> None:
        for p in platforms:
            for e in entities:
                failures = await _run_backfill(
                    platform=p,
                    entity=e,
                    start_date=start,
                    end_date=end,
                    bucket=bucket,
                    dry_run=dry_run,
                )
                all_failures.extend(failures)

    try:
        asyncio.run(_run_all())
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    if all_failures:
        typer.echo(f"\nBackfill completed with {len(all_failures)} failure(s).", err=True)
        raise typer.Exit(code=1)
    elif not dry_run:
        typer.echo("Backfill completed successfully.")


@backfill_app.command(name="catchup")
def backfill_catchup(
    platform: Annotated[
        str,
        typer.Option(
            "--platform",
            help="Platform to catch up (polymarket, kalshi, or all).",
        ),
    ] = "all",
    entity: Annotated[
        str,
        typer.Option(
            "--entity",
            help="Entity type to catch up (trades, markets, events, order_filled, or all).",
        ),
    ] = "all",
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
            help="Preview what would be fetched without executing.",
        ),
    ] = False,
    full: Annotated[
        bool,
        typer.Option(
            "--full",
            help="Force full snapshot for catalog entities (markets, events) instead of incremental.",
        ),
    ] = False,
    skip_if_concurrent: Annotated[
        bool,
        typer.Option(
            "--skip-if-concurrent",
            help="Check ECS for concurrent tasks and skip if one is already running.",
        ),
    ] = False,
) -> None:
    """Auto-detect latest data and catch up to present."""
    from prediction_data.core.logging import configure_logging

    configure_logging()

    valid_platforms = {"polymarket", "kalshi", "all"}
    valid_entities = {"trades", "markets", "events", "order_filled", "all"}

    if platform not in valid_platforms:
        typer.echo(f"Error: --platform must be one of {valid_platforms}", err=True)
        raise typer.Exit(code=1)
    if entity not in valid_entities:
        typer.echo(f"Error: --entity must be one of {valid_entities}", err=True)
        raise typer.Exit(code=1)

    platforms = _resolve_platforms(platform)
    entities = _resolve_entities(entity)
    all_failures: list[tuple[str, str]] = []

    async def _run_all() -> None:
        import os

        from prediction_data.storage import S3Client
        from prediction_data.storage.discovery import (
            find_latest_date,
            find_latest_manifest_source,
        )

        resolved_bucket = bucket or os.environ.get("BRONZE_BUCKET", "")
        if not resolved_bucket:
            typer.echo("Error: --bucket or BRONZE_BUCKET env var required.", err=True)
            raise typer.Exit(code=1)

        s3 = S3Client(bucket=resolved_bucket)

        if skip_if_concurrent:
            from prediction_data.core.ecs_guard import should_skip_concurrent

            for e in entities:
                if await should_skip_concurrent(e):
                    typer.echo(
                        f"SKIP: concurrent task detected for {e}, exiting"
                    )
                    return

        today = date.today()

        for p in platforms:
            for e in entities:
                label = f"{p}/{e}"

                # order_filled is only for polymarket
                if e == "order_filled" and p != "polymarket":
                    continue

                try:
                    if e == "order_filled":
                        # order_filled: timestamp-incremental via Goldsky
                        today_str = today.isoformat()
                        latest_date, latest_ts = await find_latest_manifest_source(
                            s3, p, e
                        )

                        if latest_date is None:
                            typer.echo(
                                f"SKIP {label}: no existing data found "
                                "(run initial backfill first)"
                            )
                            continue

                        if dry_run:
                            if latest_ts is not None:
                                typer.echo(
                                    f"[dry-run] Would incrementally ingest {label} "
                                    f"since_timestamp={latest_ts}"
                                )
                            else:
                                typer.echo(
                                    f"[dry-run] Would ingest {label} "
                                    f"(full day for {today_str}, "
                                    f"no timestamp in latest manifest)"
                                )
                            continue

                        from prediction_data.bronze.polymarket import (
                            ingest as pm_ingest,
                        )

                        run_id = await pm_ingest.ingest_order_filled(
                            today_str,
                            bucket=bucket,
                            since_timestamp=latest_ts,
                        )
                        typer.echo(f"OK {label} dt={today_str} run_id={run_id}")

                    elif _is_date_scoped_entity(e):
                        # Date-scoped: find latest date, backfill missing days
                        latest = await find_latest_date(s3, p, e)
                        if latest is None:
                            typer.echo(
                                f"SKIP {label}: no existing data found "
                                "(run initial backfill first)"
                            )
                            continue

                        latest_dt = date.fromisoformat(latest)
                        start_dt = latest_dt + timedelta(days=1)

                        if start_dt > today:
                            typer.echo(f"SKIP {label}: already up to date (latest={latest})")
                            continue

                        if dry_run:
                            days = (today - start_dt).days + 1
                            typer.echo(
                                f"[dry-run] Would backfill {label} "
                                f"from {start_dt.isoformat()} to {today.isoformat()} "
                                f"({days} day(s))"
                            )
                            continue

                        failures = await _run_backfill(
                            platform=p,
                            entity=e,
                            start_date=start_dt,
                            end_date=today,
                            bucket=bucket,
                            dry_run=False,
                        )
                        all_failures.extend(failures)

                    else:
                        # Catalog: use incremental mode by default, --full for snapshot
                        today_str = today.isoformat()

                        if full:
                            # Full snapshot mode
                            latest = await find_latest_date(s3, p, e)
                            if latest == today_str:
                                typer.echo(f"SKIP {label}: already up to date (latest={latest})")
                                continue
                            if latest is None:
                                typer.echo(
                                    f"SKIP {label}: no existing data found "
                                    "(run initial backfill first)"
                                )
                                continue
                            if dry_run:
                                typer.echo(
                                    f"[dry-run] Would ingest {label} "
                                    f"(full catalog snapshot for {today_str})"
                                )
                                continue
                            failures = await _run_backfill(
                                platform=p,
                                entity=e,
                                start_date=today,
                                end_date=today,
                                bucket=bucket,
                                dry_run=False,
                            )
                            all_failures.extend(failures)
                        else:
                            # Incremental mode (default)
                            latest_date, latest_ts = await find_latest_manifest_source(
                                s3, p, e
                            )

                            if latest_date is None:
                                # No previous data — fall back to full snapshot
                                if dry_run:
                                    typer.echo(
                                        f"[dry-run] Would ingest {label} "
                                        f"(full catalog snapshot for {today_str}, first run)"
                                    )
                                    continue
                                failures = await _run_backfill(
                                    platform=p,
                                    entity=e,
                                    start_date=today,
                                    end_date=today,
                                    bucket=bucket,
                                    dry_run=False,
                                )
                                all_failures.extend(failures)
                                continue

                            if latest_ts is None:
                                # Previous data exists but no timestamp — full snapshot
                                if dry_run:
                                    typer.echo(
                                        f"[dry-run] Would ingest {label} "
                                        f"(full catalog snapshot for {today_str}, "
                                        f"no cursor in latest manifest)"
                                    )
                                    continue
                                failures = await _run_backfill(
                                    platform=p,
                                    entity=e,
                                    start_date=today,
                                    end_date=today,
                                    bucket=bucket,
                                    dry_run=False,
                                )
                                all_failures.extend(failures)
                                continue

                            # Have a cursor — run incremental
                            from prediction_data.bronze.polymarket.ingest import (
                                _epoch_to_iso,
                            )

                            since_updated_at = _epoch_to_iso(latest_ts)

                            if dry_run:
                                typer.echo(
                                    f"[dry-run] Would incrementally ingest {label} "
                                    f"since_updated_at={since_updated_at} "
                                    f"(epoch={latest_ts})"
                                )
                                continue

                            if p == "polymarket":
                                from prediction_data.bronze.polymarket import (
                                    ingest as pm_ingest,
                                )

                                if e == "markets":
                                    run_id = await pm_ingest.ingest_markets(
                                        today_str,
                                        bucket=bucket,
                                        since_updated_at=since_updated_at,
                                    )
                                else:
                                    run_id = await pm_ingest.ingest_events(
                                        today_str,
                                        bucket=bucket,
                                        since_updated_at=since_updated_at,
                                    )
                                typer.echo(f"OK {label} run_id={run_id}")
                            else:
                                # Kalshi doesn't support incremental catalog yet — full snapshot
                                failures = await _run_backfill(
                                    platform=p,
                                    entity=e,
                                    start_date=today,
                                    end_date=today,
                                    bucket=bucket,
                                    dry_run=False,
                                )
                                all_failures.extend(failures)

                except Exception as exc:
                    all_failures.append((label, str(exc)))
                    typer.echo(f"FAIL {label}: {exc}", err=True)

    try:
        asyncio.run(_run_all())
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    if all_failures:
        typer.echo(f"\nCatchup completed with {len(all_failures)} failure(s).", err=True)
        raise typer.Exit(code=1)
    elif not dry_run:
        typer.echo("Catchup completed successfully.")
