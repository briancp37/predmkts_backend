"""Gold layer CLI commands."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

import typer

from prediction_data.core.config import get_settings

app = typer.Typer(
    help="Gold layer aggregation and ClickHouse serving.",
    no_args_is_help=True,
)

LOADABLE_DIMS = ("dim_platform", "dim_market", "dim_outcome", "dim_wallet", "dim_event", "dim_category")


@app.command(name="status")
def status() -> None:
    """Show Gold layer status and table info."""
    typer.echo("Gold layer status: not yet configured.")
    typer.echo("Run 'prediction-data gold init-tables' after ClickHouse setup.")


@app.command(name="load-dims")
def load_dims(
    table: Optional[str] = typer.Option(  # noqa: UP007
        None,
        help=f"Specific dimension table to load. Options: {', '.join(LOADABLE_DIMS)}.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing."),
) -> None:
    """Load Gold dimension tables into S3 and ClickHouse."""
    from prediction_data.gold.dimensions import (
        load_dim_category,
        load_dim_event,
        load_dim_market,
        load_dim_outcome,
        load_dim_platform,
        load_dim_wallet,
    )

    settings = get_settings()
    tables_to_load = [table] if table else list(LOADABLE_DIMS)

    for tbl in tables_to_load:
        if tbl not in LOADABLE_DIMS:
            typer.echo(f"Unknown dimension table: {tbl}", err=True)
            raise typer.Exit(code=1)

    for tbl in tables_to_load:
        if tbl == "dim_platform":
            rows = load_dim_platform(
                gold_bucket=settings.gold_bucket or None,
                dry_run=dry_run,
            )
            typer.echo(f"dim_platform: {rows} rows loaded.")
        elif tbl == "dim_market":
            rows = load_dim_market(
                gold_bucket=settings.gold_bucket or None,
                dry_run=dry_run,
            )
            typer.echo(f"dim_market: {rows} rows loaded.")
        elif tbl == "dim_outcome":
            rows = load_dim_outcome(
                gold_bucket=settings.gold_bucket or None,
                dry_run=dry_run,
            )
            typer.echo(f"dim_outcome: {rows} rows loaded.")
        elif tbl == "dim_wallet":
            rows = load_dim_wallet(
                gold_bucket=settings.gold_bucket or None,
                dry_run=dry_run,
            )
            typer.echo(f"dim_wallet: {rows} rows loaded.")
        elif tbl == "dim_event":
            rows = load_dim_event(
                gold_bucket=settings.gold_bucket or None,
                dry_run=dry_run,
            )
            typer.echo(f"dim_event: {rows} rows loaded.")
        elif tbl == "dim_category":
            rows = load_dim_category(
                gold_bucket=settings.gold_bucket or None,
                dry_run=dry_run,
            )
            typer.echo(f"dim_category: {rows} rows loaded.")


# ---------------------------------------------------------------------------
# Watchlist sub-commands
# ---------------------------------------------------------------------------

watchlist_app = typer.Typer(
    help="Manage the Gold watchlist for selective wallet computation.",
    no_args_is_help=True,
)
app.add_typer(watchlist_app, name="watchlist")


@app.command(name="compute-marks")
def compute_marks(
    dt: Optional[str] = typer.Option(  # noqa: UP007
        None,
        help="Single date to compute (YYYY-MM-DD).",
    ),
    start_date: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--start-date",
        help="Start of date range (YYYY-MM-DD). Requires --end-date.",
    ),
    end_date: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--end-date",
        help="End of date range inclusive (YYYY-MM-DD). Requires --start-date.",
    ),
    platform: str = typer.Option("polymarket", help="Platform to compute marks for."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing."),
) -> None:
    """Compute market_mark_daily from Silver trades."""
    from datetime import date as date_cls, timedelta

    from prediction_data.gold.market_marks import compute_market_marks

    settings = get_settings()

    # Resolve dates.
    if dt and (start_date or end_date):
        typer.echo("Error: --dt cannot be combined with --start-date/--end-date.", err=True)
        raise typer.Exit(code=1)

    if dt:
        dates = [date_cls.fromisoformat(dt)]
    elif start_date and end_date:
        s = date_cls.fromisoformat(start_date)
        e = date_cls.fromisoformat(end_date)
        if s > e:
            typer.echo("Error: --start-date must be <= --end-date.", err=True)
            raise typer.Exit(code=1)
        dates = []
        cur = s
        while cur <= e:
            dates.append(cur)
            cur += timedelta(days=1)
    else:
        typer.echo("Error: provide --dt or both --start-date and --end-date.", err=True)
        raise typer.Exit(code=1)

    total_rows = 0
    failures: list[str] = []
    for d in dates:
        try:
            rows = compute_market_marks(
                platform=platform,
                dt=d,
                gold_bucket=settings.gold_bucket or None,
                dry_run=dry_run,
            )
            total_rows += rows
            typer.echo(f"{d}: {rows} rows{'  [dry-run]' if dry_run else ''}")
        except Exception as exc:
            failures.append(f"{d}: {exc}")
            typer.echo(f"{d}: FAILED ({exc})", err=True)

    typer.echo(f"Total: {total_rows} rows across {len(dates)} day(s).")
    if failures:
        typer.echo(f"{len(failures)} day(s) failed:", err=True)
        for f in failures:
            typer.echo(f"  {f}", err=True)
        raise typer.Exit(code=1)


@app.command(name="load-marks-ch")
def load_marks_ch(
    lookback_days: int = typer.Option(
        90, "--lookback-days", help="Number of days to load from S3 into ClickHouse."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing."),
) -> None:
    """Load market_mark_daily from S3 Gold Parquet into ClickHouse."""
    from prediction_data.gold.market_marks import load_marks_to_clickhouse_from_s3

    settings = get_settings()
    gold_bucket = settings.gold_bucket or None
    if not gold_bucket:
        typer.echo("Error: GOLD_BUCKET not configured.", err=True)
        raise typer.Exit(code=1)

    if dry_run:
        typer.echo(f"[dry-run] Would load up to {lookback_days} days into ClickHouse.")
        return

    rows = load_marks_to_clickhouse_from_s3(
        gold_bucket=gold_bucket,
        lookback_days=lookback_days,
    )
    typer.echo(f"Loaded {rows} rows into ClickHouse (lookback={lookback_days} days).")


@app.command(name="ch-load")
def ch_load(
    table: Optional[str] = typer.Option(  # noqa: UP007
        None,
        help=(
            "Gold table to load. Options: market_mark_daily, wallet_pnl_daily, "
            "wallet_mtm_daily, wallet_position_snapshot_daily."
        ),
    ),
    all_tables: bool = typer.Option(
        False, "--all", help="Load all Gold tables into ClickHouse."
    ),
    lookback_days: int = typer.Option(
        90, "--lookback-days", help="Number of days to load from S3 (default: 90)."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing."),
) -> None:
    """Load Gold tables from S3 Parquet into ClickHouse.

    Reads day-partitioned Parquet files from S3 Gold and inserts them
    into the corresponding ClickHouse tables within the lookback window.
    ClickHouse TTL expressions handle expiry of older data automatically.

    Specify --table TABLE for a single table or --all for all tables.
    """
    from prediction_data.gold.ch_loader import ALL_GOLD_TABLES, load_gold_table_to_clickhouse

    settings = get_settings()
    gold_bucket = settings.gold_bucket or None
    if not gold_bucket:
        typer.echo("Error: GOLD_BUCKET not configured.", err=True)
        raise typer.Exit(code=1)

    if not table and not all_tables:
        typer.echo("Error: specify --table TABLE or --all.", err=True)
        raise typer.Exit(code=1)

    if table and all_tables:
        typer.echo("Error: --table and --all are mutually exclusive.", err=True)
        raise typer.Exit(code=1)

    # table is guaranteed non-None here (checked above).
    tables_to_load: list[str] = ALL_GOLD_TABLES if all_tables else [table]  # type: ignore[list-item]

    # Validate table names.
    for tbl in tables_to_load:
        if tbl not in ALL_GOLD_TABLES:
            typer.echo(
                f"Error: unknown table '{tbl}'. "
                f"Options: {', '.join(ALL_GOLD_TABLES)}",
                err=True,
            )
            raise typer.Exit(code=1)

    if dry_run:
        for tbl in tables_to_load:
            typer.echo(
                f"[dry-run] Would load {tbl} (lookback={lookback_days} days) into ClickHouse."
            )
        return

    total_rows = 0
    failures: list[str] = []
    for tbl in tables_to_load:
        try:
            rows = load_gold_table_to_clickhouse(
                table_name=tbl,
                gold_bucket=gold_bucket,
                lookback_days=lookback_days,
            )
            total_rows += rows
            typer.echo(f"{tbl}: {rows} rows loaded (lookback={lookback_days} days).")
        except Exception as exc:
            failures.append(f"{tbl}: {exc}")
            typer.echo(f"{tbl}: FAILED ({exc})", err=True)

    typer.echo(f"Total: {total_rows} rows across {len(tables_to_load)} table(s).")
    if failures:
        typer.echo(f"{len(failures)} table(s) failed:", err=True)
        for f in failures:
            typer.echo(f"  {f}", err=True)
        raise typer.Exit(code=1)


@app.command(name="compute-pnl")
def compute_pnl(
    dt: Optional[str] = typer.Option(  # noqa: UP007
        None,
        help="Single date to compute (YYYY-MM-DD).",
    ),
    start_date: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--start-date",
        help="Start of date range (YYYY-MM-DD). Requires --end-date.",
    ),
    end_date: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--end-date",
        help="End of date range inclusive (YYYY-MM-DD). Requires --start-date.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing."),
) -> None:
    """Compute wallet_pnl_daily from wallet_position_ledger."""
    from datetime import date as date_cls, timedelta

    from prediction_data.gold.wallet_pnl import compute_wallet_pnl

    settings = get_settings()

    if dt and (start_date or end_date):
        typer.echo("Error: --dt cannot be combined with --start-date/--end-date.", err=True)
        raise typer.Exit(code=1)

    if dt:
        dates = [date_cls.fromisoformat(dt)]
    elif start_date and end_date:
        s = date_cls.fromisoformat(start_date)
        e = date_cls.fromisoformat(end_date)
        if s > e:
            typer.echo("Error: --start-date must be <= --end-date.", err=True)
            raise typer.Exit(code=1)
        dates = []
        cur = s
        while cur <= e:
            dates.append(cur)
            cur += timedelta(days=1)
    else:
        typer.echo("Error: provide --dt or both --start-date and --end-date.", err=True)
        raise typer.Exit(code=1)

    total_rows = 0
    failures: list[str] = []
    for d in dates:
        try:
            rows = compute_wallet_pnl(
                dt=d,
                gold_bucket=settings.gold_bucket or None,
                dry_run=dry_run,
            )
            total_rows += rows
            typer.echo(f"{d}: {rows} rows{'  [dry-run]' if dry_run else ''}")
        except Exception as exc:
            failures.append(f"{d}: {exc}")
            typer.echo(f"{d}: FAILED ({exc})", err=True)

    typer.echo(f"Total: {total_rows} rows across {len(dates)} day(s).")
    if failures:
        typer.echo(f"{len(failures)} day(s) failed:", err=True)
        for f in failures:
            typer.echo(f"  {f}", err=True)
        raise typer.Exit(code=1)


@app.command(name="compute-mtm")
def compute_mtm(
    dt: Optional[str] = typer.Option(  # noqa: UP007
        None,
        help="Single date to compute (YYYY-MM-DD).",
    ),
    start_date: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--start-date",
        help="Start of date range (YYYY-MM-DD). Requires --end-date.",
    ),
    end_date: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--end-date",
        help="End of date range inclusive (YYYY-MM-DD). Requires --start-date.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing."),
) -> None:
    """Compute wallet_mtm_daily for watchlist wallets."""
    from datetime import date as date_cls, timedelta

    from prediction_data.gold.wallet_mtm import compute_wallet_mtm

    settings = get_settings()

    if dt and (start_date or end_date):
        typer.echo("Error: --dt cannot be combined with --start-date/--end-date.", err=True)
        raise typer.Exit(code=1)

    if dt:
        dates = [date_cls.fromisoformat(dt)]
    elif start_date and end_date:
        s = date_cls.fromisoformat(start_date)
        e = date_cls.fromisoformat(end_date)
        if s > e:
            typer.echo("Error: --start-date must be <= --end-date.", err=True)
            raise typer.Exit(code=1)
        dates = []
        cur = s
        while cur <= e:
            dates.append(cur)
            cur += timedelta(days=1)
    else:
        typer.echo("Error: provide --dt or both --start-date and --end-date.", err=True)
        raise typer.Exit(code=1)

    total_rows = 0
    failures: list[str] = []
    for d in dates:
        try:
            rows = compute_wallet_mtm(
                dt=d,
                gold_bucket=settings.gold_bucket or None,
                dry_run=dry_run,
            )
            total_rows += rows
            typer.echo(f"{d}: {rows} rows{'  [dry-run]' if dry_run else ''}")
        except Exception as exc:
            failures.append(f"{d}: {exc}")
            typer.echo(f"{d}: FAILED ({exc})", err=True)

    typer.echo(f"Total: {total_rows} rows across {len(dates)} day(s).")
    if failures:
        typer.echo(f"{len(failures)} day(s) failed:", err=True)
        for f in failures:
            typer.echo(f"  {f}", err=True)
        raise typer.Exit(code=1)


@app.command(name="compute-position-snapshot")
def compute_position_snapshot(
    dt: Optional[str] = typer.Option(  # noqa: UP007
        None,
        help="Single date to compute (YYYY-MM-DD).",
    ),
    start_date: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--start-date",
        help="Start of date range (YYYY-MM-DD). Requires --end-date.",
    ),
    end_date: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--end-date",
        help="End of date range inclusive (YYYY-MM-DD). Requires --start-date.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing."),
) -> None:
    """Compute wallet_position_snapshot_daily for watchlist wallets."""
    from datetime import date as date_cls, timedelta

    from prediction_data.gold.wallet_position_snapshot import compute_wallet_position_snapshot

    settings = get_settings()

    if dt and (start_date or end_date):
        typer.echo("Error: --dt cannot be combined with --start-date/--end-date.", err=True)
        raise typer.Exit(code=1)

    if dt:
        dates = [date_cls.fromisoformat(dt)]
    elif start_date and end_date:
        s = date_cls.fromisoformat(start_date)
        e = date_cls.fromisoformat(end_date)
        if s > e:
            typer.echo("Error: --start-date must be <= --end-date.", err=True)
            raise typer.Exit(code=1)
        dates = []
        cur = s
        while cur <= e:
            dates.append(cur)
            cur += timedelta(days=1)
    else:
        typer.echo("Error: provide --dt or both --start-date and --end-date.", err=True)
        raise typer.Exit(code=1)

    total_rows = 0
    failures: list[str] = []
    for d in dates:
        try:
            rows = compute_wallet_position_snapshot(
                dt=d,
                gold_bucket=settings.gold_bucket or None,
                dry_run=dry_run,
            )
            total_rows += rows
            typer.echo(f"{d}: {rows} rows{'  [dry-run]' if dry_run else ''}")
        except Exception as exc:
            failures.append(f"{d}: {exc}")
            typer.echo(f"{d}: FAILED ({exc})", err=True)

    typer.echo(f"Total: {total_rows} rows across {len(dates)} day(s).")
    if failures:
        typer.echo(f"{len(failures)} day(s) failed:", err=True)
        for f in failures:
            typer.echo(f"  {f}", err=True)
        raise typer.Exit(code=1)


@app.command(name="compute-wallet-metrics")
def compute_wallet_metrics(
    dt: Optional[str] = typer.Option(  # noqa: UP007
        None,
        help="Single date to compute (YYYY-MM-DD).",
    ),
    start_date: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--start-date",
        help="Start of date range (YYYY-MM-DD). Requires --end-date.",
    ),
    end_date: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--end-date",
        help="End of date range inclusive (YYYY-MM-DD). Requires --start-date.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing."),
) -> None:
    """Compute all wallet metrics: pnl (all wallets), mtm + snapshots (watchlist only)."""
    from datetime import date as date_cls, timedelta

    from prediction_data.gold.wallet_mtm import compute_wallet_mtm
    from prediction_data.gold.wallet_pnl import compute_wallet_pnl
    from prediction_data.gold.wallet_position_snapshot import compute_wallet_position_snapshot

    settings = get_settings()

    if dt and (start_date or end_date):
        typer.echo("Error: --dt cannot be combined with --start-date/--end-date.", err=True)
        raise typer.Exit(code=1)

    if dt:
        dates = [date_cls.fromisoformat(dt)]
    elif start_date and end_date:
        s = date_cls.fromisoformat(start_date)
        e = date_cls.fromisoformat(end_date)
        if s > e:
            typer.echo("Error: --start-date must be <= --end-date.", err=True)
            raise typer.Exit(code=1)
        dates = []
        cur = s
        while cur <= e:
            dates.append(cur)
            cur += timedelta(days=1)
    else:
        typer.echo("Error: provide --dt or both --start-date and --end-date.", err=True)
        raise typer.Exit(code=1)

    gold_bucket = settings.gold_bucket or None
    failures: list[str] = []

    # 1. wallet_pnl_daily (all wallets)
    typer.echo("--- wallet_pnl_daily (all wallets) ---")
    pnl_total = 0
    for d in dates:
        try:
            rows = compute_wallet_pnl(dt=d, gold_bucket=gold_bucket, dry_run=dry_run)
            pnl_total += rows
            typer.echo(f"  {d}: {rows} rows{'  [dry-run]' if dry_run else ''}")
        except Exception as exc:
            failures.append(f"pnl {d}: {exc}")
            typer.echo(f"  {d}: FAILED ({exc})", err=True)

    # 2. wallet_mtm_daily (watchlist only)
    typer.echo("--- wallet_mtm_daily (watchlist) ---")
    mtm_total = 0
    for d in dates:
        try:
            rows = compute_wallet_mtm(dt=d, gold_bucket=gold_bucket, dry_run=dry_run)
            mtm_total += rows
            typer.echo(f"  {d}: {rows} rows{'  [dry-run]' if dry_run else ''}")
        except Exception as exc:
            failures.append(f"mtm {d}: {exc}")
            typer.echo(f"  {d}: FAILED ({exc})", err=True)

    # 3. wallet_position_snapshot_daily (watchlist only)
    typer.echo("--- wallet_position_snapshot_daily (watchlist) ---")
    snap_total = 0
    for d in dates:
        try:
            rows = compute_wallet_position_snapshot(
                dt=d, gold_bucket=gold_bucket, dry_run=dry_run
            )
            snap_total += rows
            typer.echo(f"  {d}: {rows} rows{'  [dry-run]' if dry_run else ''}")
        except Exception as exc:
            failures.append(f"snapshot {d}: {exc}")
            typer.echo(f"  {d}: FAILED ({exc})", err=True)

    typer.echo(
        f"Total: pnl={pnl_total}, mtm={mtm_total}, snapshots={snap_total} "
        f"across {len(dates)} day(s)."
    )
    if failures:
        typer.echo(f"{len(failures)} step(s) failed:", err=True)
        for f in failures:
            typer.echo(f"  {f}", err=True)
        raise typer.Exit(code=1)


@app.command(name="process-trades")
def process_trades(
    dt: Optional[str] = typer.Option(  # noqa: UP007
        None,
        help="Single date to process (YYYY-MM-DD).",
    ),
    start_date: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--start-date",
        help="Start of date range (YYYY-MM-DD). Requires --end-date.",
    ),
    end_date: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--end-date",
        help="End of date range inclusive (YYYY-MM-DD). Requires --start-date.",
    ),
    force_reprocess: bool = typer.Option(
        False, "--force-reprocess", help="Reprocess already-processed dates."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing."),
) -> None:
    """Process Silver trades through the position accounting pipeline.

    Reads Silver polymarket.trades, splits into fills, runs through the
    average-cost accounting engine, and writes the position ledger (S3 Gold +
    ClickHouse) and updates position state in ClickHouse.

    Dates are processed sequentially (order matters for cumulative position
    state). Already-processed dates are skipped unless --force-reprocess.
    """
    from datetime import date as date_cls

    from prediction_data.gold.trade_processor import process_date_range, process_day

    settings = get_settings()

    if dt and (start_date or end_date):
        typer.echo("Error: --dt cannot be combined with --start-date/--end-date.", err=True)
        raise typer.Exit(code=1)

    gold_bucket = settings.gold_bucket or None

    if dt:
        target = date_cls.fromisoformat(dt)
        typer.echo(
            f"Processing trades for {target}"
            f"{'  [force-reprocess]' if force_reprocess else ''}"
            f"{'  [dry-run]' if dry_run else ''}"
        )
        rows = process_day(
            dt=target,
            gold_bucket=gold_bucket,
            dry_run=dry_run,
            force_reprocess=force_reprocess,
        )
        typer.echo(f"{target}: {rows} fills processed{'  [dry-run]' if dry_run else ''}")
        typer.echo(f"Total: {rows} fills across 1 day(s).")
    elif start_date and end_date:
        s = date_cls.fromisoformat(start_date)
        e = date_cls.fromisoformat(end_date)
        if s > e:
            typer.echo("Error: --start-date must be <= --end-date.", err=True)
            raise typer.Exit(code=1)
        typer.echo(
            f"Processing trades from {s} to {e}"
            f"{'  [force-reprocess]' if force_reprocess else ''}"
            f"{'  [dry-run]' if dry_run else ''}"
        )
        results = process_date_range(
            start_date=s,
            end_date=e,
            gold_bucket=gold_bucket,
            dry_run=dry_run,
            force_reprocess=force_reprocess,
        )
        for day_str, fills in sorted(results.items()):
            typer.echo(f"  {day_str}: {fills} fills{'  [dry-run]' if dry_run else ''}")
        total = sum(results.values())
        typer.echo(f"Total: {total} fills across {len(results)} day(s).")
    else:
        typer.echo("Error: provide --dt or both --start-date and --end-date.", err=True)
        raise typer.Exit(code=1)


@app.command(name="daily-run")
def daily_run(
    dt: Optional[str] = typer.Option(  # noqa: UP007
        None,
        help="Date to process (YYYY-MM-DD). Defaults to yesterday UTC.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing."),
    stop_on_error: bool = typer.Option(
        False, "--stop-on-error", help="Halt on first step failure instead of continuing."
    ),
) -> None:
    """Run all daily Gold processing steps in order.

    Executes: 1) load-dims, 2) process-trades, 3) compute-marks, 4) compute-wallet-metrics.

    By default, failures are logged and execution continues to the next step
    (fail-forward). Use --stop-on-error to halt on first failure.
    """
    from datetime import UTC, date as date_cls, datetime, timedelta

    import structlog

    log = structlog.stdlib.get_logger("gold.daily_run")

    settings = get_settings()
    gold_bucket = settings.gold_bucket or None

    # Default to yesterday UTC.
    target_date = (
        date_cls.fromisoformat(dt) if dt else datetime.now(UTC).date() - timedelta(days=1)
    )

    typer.echo(f"Gold daily-run for {target_date}{'  [dry-run]' if dry_run else ''}")

    # Define steps in execution order.
    steps: list[tuple[str, str]] = [
        ("load-dims", "Loading dimension tables"),
        ("process-trades", "Processing trades into position ledger"),
        ("compute-marks", "Computing market marks"),
        ("compute-wallet-metrics", "Computing wallet metrics (pnl, mtm, snapshots)"),
    ]

    results: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    total_rows = 0

    for step_name, step_desc in steps:
        typer.echo(f"\n--- Step: {step_name} ({step_desc}) ---")
        log.info("step.start", step=step_name, dt=str(target_date))

        try:
            rows = _run_daily_step(
                step_name, target_date, gold_bucket=gold_bucket, dry_run=dry_run
            )
            total_rows += rows
            results.append({"step": step_name, "status": "success", "rows": rows})
            typer.echo(f"  {step_name}: {rows} rows{'  [dry-run]' if dry_run else ''}")
            log.info("step.success", step=step_name, rows=rows)
        except Exception as exc:
            entry: dict[str, Any] = {"step": step_name, "status": "failed", "error": str(exc)}
            results.append(entry)
            failed.append(entry)
            typer.echo(f"  {step_name}: FAILED ({exc})", err=True)
            log.error("step.failed", step=step_name, error=str(exc))
            if stop_on_error:
                typer.echo("Halting due to --stop-on-error.", err=True)
                break

    # Summary.
    succeeded = [r for r in results if r["status"] == "success"]
    typer.echo(f"\n{'=' * 60}")
    typer.echo(f"Daily-run summary for {target_date}:")
    typer.echo(f"  Steps succeeded: {len(succeeded)}/{len(results)}")
    typer.echo(f"  Total rows: {total_rows}")
    if failed:
        typer.echo("  Failed steps:", err=True)
        for r in failed:
            typer.echo(f"    {r['step']}: {r['error']}", err=True)

    # Emit pipeline_runs metadata if ClickHouse is available.
    _emit_daily_run_metadata(
        log, total_rows=total_rows, has_failures=bool(failed)
    )

    if failed:
        raise typer.Exit(code=1)


def _emit_daily_run_metadata(
    log: object,  # structlog logger
    *,
    total_rows: int,
    has_failures: bool,
) -> None:
    """Best-effort pipeline_runs record for the daily-run."""
    try:
        from prediction_data.gold.clickhouse import get_client
        from prediction_data.gold.ops_metadata import end_run, start_run

        ch = get_client()
        run_id = start_run(ch, "gold.daily_run")
        from datetime import UTC, datetime

        started_at = datetime.now(UTC)
        end_run(
            ch,
            run_id,
            "gold.daily_run",
            started_at,
            status="failed" if has_failures else "success",
            rows_written=total_rows,
            error="one or more steps failed" if has_failures else None,
        )
    except Exception:
        if hasattr(log, "debug"):
            log.debug("clickhouse_unavailable_for_tracking", exc_info=True)


def _run_daily_step(
    step_name: str,
    dt: date,
    *,
    gold_bucket: str | None = None,
    dry_run: bool = False,
) -> int:
    """Execute a single daily-run step and return the number of rows produced."""
    if step_name == "load-dims":
        from prediction_data.gold.dimensions import (
            load_dim_category,
            load_dim_event,
            load_dim_market,
            load_dim_outcome,
            load_dim_platform,
            load_dim_wallet,
        )

        total = 0
        total += load_dim_platform(gold_bucket=gold_bucket, dry_run=dry_run)
        total += load_dim_market(gold_bucket=gold_bucket, dry_run=dry_run)
        total += load_dim_outcome(gold_bucket=gold_bucket, dry_run=dry_run)
        total += load_dim_wallet(gold_bucket=gold_bucket, dry_run=dry_run)
        total += load_dim_event(gold_bucket=gold_bucket, dry_run=dry_run)
        total += load_dim_category(gold_bucket=gold_bucket, dry_run=dry_run)
        return total

    elif step_name == "process-trades":
        # Position accounting engine (sprint 03). Call if available,
        # otherwise raise NotImplementedError so fail-forward kicks in.
        try:
            from prediction_data.gold.trade_processor import process_day

            result: int = process_day(dt=dt, gold_bucket=gold_bucket, dry_run=dry_run)
            return result
        except ImportError:
            raise NotImplementedError(
                "process-trades requires the position accounting engine "
                "(gold.trade_processor) which is not yet implemented."
            ) from None

    elif step_name == "compute-marks":
        from prediction_data.gold.market_marks import compute_market_marks

        return compute_market_marks(
            platform="polymarket",
            dt=dt,
            gold_bucket=gold_bucket,
            dry_run=dry_run,
        )

    elif step_name == "compute-wallet-metrics":
        from prediction_data.gold.wallet_mtm import compute_wallet_mtm
        from prediction_data.gold.wallet_pnl import compute_wallet_pnl
        from prediction_data.gold.wallet_position_snapshot import (
            compute_wallet_position_snapshot,
        )

        total = 0
        total += compute_wallet_pnl(dt=dt, gold_bucket=gold_bucket, dry_run=dry_run)
        total += compute_wallet_mtm(dt=dt, gold_bucket=gold_bucket, dry_run=dry_run)
        total += compute_wallet_position_snapshot(
            dt=dt, gold_bucket=gold_bucket, dry_run=dry_run
        )
        return total

    else:
        raise ValueError(f"Unknown step: {step_name}")


# ---------------------------------------------------------------------------
# Rebuild tables
# ---------------------------------------------------------------------------

# Tables that can be rebuilt independently per day (no cross-day state).
_INDEPENDENT_TABLES = {"market_mark_daily"}

# Tables that depend on cumulative position state and should be rebuilt
# sequentially from earliest date.
_CUMULATIVE_TABLES = {
    "wallet_pnl_daily",
    "wallet_mtm_daily",
    "wallet_position_snapshot_daily",
}

REBUILDABLE_TABLES = sorted(_INDEPENDENT_TABLES | _CUMULATIVE_TABLES)


def _gold_partition_exists(
    s3_client: Any,
    bucket: str,
    table_name: str,
    day: str,
) -> bool:
    """Check whether a Gold partition already exists in S3."""
    key = f"gold/{table_name}/day={day}/part-000.parquet"
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def _rebuild_day(
    table_name: str,
    dt: date,
    *,
    gold_bucket: str | None = None,
    dry_run: bool = False,
) -> int:
    """Rebuild a single Gold table for one day. Returns row count."""
    if table_name == "market_mark_daily":
        from prediction_data.gold.market_marks import compute_market_marks

        return compute_market_marks(
            platform="polymarket",
            dt=dt,
            gold_bucket=gold_bucket,
            dry_run=dry_run,
        )
    elif table_name == "wallet_pnl_daily":
        from prediction_data.gold.wallet_pnl import compute_wallet_pnl

        return compute_wallet_pnl(
            dt=dt,
            gold_bucket=gold_bucket,
            dry_run=dry_run,
        )
    elif table_name == "wallet_mtm_daily":
        from prediction_data.gold.wallet_mtm import compute_wallet_mtm

        return compute_wallet_mtm(
            dt=dt,
            gold_bucket=gold_bucket,
            dry_run=dry_run,
        )
    elif table_name == "wallet_position_snapshot_daily":
        from prediction_data.gold.wallet_position_snapshot import compute_wallet_position_snapshot

        return compute_wallet_position_snapshot(
            dt=dt,
            gold_bucket=gold_bucket,
            dry_run=dry_run,
        )
    else:
        raise ValueError(f"Unknown rebuild table: {table_name}")


@app.command(name="rebuild")
def rebuild(
    table: str = typer.Option(
        ...,
        help=f"Gold table to rebuild. Options: {', '.join(REBUILDABLE_TABLES)}.",
    ),
    start_date: str = typer.Option(
        ..., "--start-date", help="Start of date range (YYYY-MM-DD)."
    ),
    end_date: str = typer.Option(
        ..., "--end-date", help="End of date range inclusive (YYYY-MM-DD)."
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing S3 Gold partitions."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing."),
) -> None:
    """Rebuild Gold tables from Silver for a date range.

    Reprocesses the specified Gold table for each day in the date range.
    Without --force, days that already have data in S3 are skipped.

    For cumulative tables (wallet_pnl_daily, wallet_mtm_daily,
    wallet_position_snapshot_daily), dates are always processed sequentially
    from earliest to latest because position state is cumulative.

    For market_mark_daily, each day can be rebuilt independently.
    """
    from datetime import date as date_cls, timedelta

    import structlog

    log = structlog.stdlib.get_logger("gold.rebuild")

    if table not in REBUILDABLE_TABLES:
        typer.echo(
            f"Error: unknown table '{table}'. "
            f"Options: {', '.join(REBUILDABLE_TABLES)}",
            err=True,
        )
        raise typer.Exit(code=1)

    s = date_cls.fromisoformat(start_date)
    e = date_cls.fromisoformat(end_date)
    if s > e:
        typer.echo("Error: --start-date must be <= --end-date.", err=True)
        raise typer.Exit(code=1)

    settings = get_settings()
    gold_bucket = settings.gold_bucket or None

    # Build date list (always earliest-first for cumulative tables).
    dates: list[date] = []
    cur = s
    while cur <= e:
        dates.append(cur)
        cur += timedelta(days=1)

    is_cumulative = table in _CUMULATIVE_TABLES

    typer.echo(
        f"Rebuild {table}: {len(dates)} day(s) from {s} to {e}"
        f"{'  [cumulative — sequential]' if is_cumulative else ''}"
        f"{'  [force]' if force else ''}"
        f"{'  [dry-run]' if dry_run else ''}"
    )

    # Warn about dependencies for wallet metrics tables.
    if table in ("wallet_mtm_daily", "wallet_position_snapshot_daily"):
        typer.echo(
            "Note: this table depends on market marks and position state. "
            "Ensure market_mark_daily and wallet_position_ledger are up-to-date."
        )
    elif table == "wallet_pnl_daily":
        typer.echo(
            "Note: this table depends on wallet_position_ledger. "
            "Ensure the position ledger is up-to-date."
        )

    total_rows = 0
    skipped = 0
    failures: list[str] = []

    # Prepare S3 client for existence checks (only when not forcing).
    s3_client: Any = None
    if not force and not dry_run and gold_bucket:
        import boto3

        s3_client = boto3.client("s3")

    for i, d in enumerate(dates, 1):
        # Skip existing partitions unless --force.
        if not force and not dry_run and gold_bucket and s3_client is not None:
            if _gold_partition_exists(s3_client, gold_bucket, table, str(d)):
                skipped += 1
                log.info("partition_exists_skipping", table=table, day=str(d))
                typer.echo(f"  [{i}/{len(dates)}] {d}: skipped (exists)")
                continue

        try:
            rows = _rebuild_day(
                table, d, gold_bucket=gold_bucket, dry_run=dry_run
            )
            total_rows += rows
            typer.echo(
                f"  [{i}/{len(dates)}] {d}: {rows} rows"
                f"{'  [dry-run]' if dry_run else ''}"
            )
            log.info("rebuild_day_done", table=table, day=str(d), rows=rows)
        except Exception as exc:
            failures.append(f"{d}: {exc}")
            typer.echo(f"  [{i}/{len(dates)}] {d}: FAILED ({exc})", err=True)
            log.error("rebuild_day_failed", table=table, day=str(d), error=str(exc))

    # Summary.
    typer.echo(f"\nRebuild summary for {table}:")
    typer.echo(f"  Days processed: {len(dates) - skipped - len(failures)}/{len(dates)}")
    typer.echo(f"  Total rows: {total_rows}")
    if skipped:
        typer.echo(f"  Skipped (already exist): {skipped}")
    if failures:
        typer.echo(f"  Failed: {len(failures)}", err=True)
        for f in failures:
            typer.echo(f"    {f}", err=True)
        raise typer.Exit(code=1)


@app.command(name="compute-snapshot")
def compute_snapshot(
    wallet: str = typer.Option(..., "--wallet", help="Wallet address to compute snapshots for."),
    start_date: str = typer.Option(
        ..., "--start-date", help="Start of date range (YYYY-MM-DD)."
    ),
    end_date: str = typer.Option(
        ..., "--end-date", help="End of date range inclusive (YYYY-MM-DD)."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing."),
    skip_ch: bool = typer.Option(
        False, "--skip-ch", help="Write to S3 only, skip ClickHouse loading."
    ),
    chunk_days: int = typer.Option(
        30, "--chunk-days", help="Max days per batch (default 30)."
    ),
) -> None:
    """On-demand snapshot reconstruction for a single wallet."""
    from datetime import date as date_cls, timedelta

    from prediction_data.gold.on_demand import compute_wallet_snapshots

    settings = get_settings()

    s = date_cls.fromisoformat(start_date)
    e = date_cls.fromisoformat(end_date)
    if s > e:
        typer.echo("Error: --start-date must be <= --end-date.", err=True)
        raise typer.Exit(code=1)

    total_days = (e - s).days + 1
    gold_bucket = settings.gold_bucket or None

    total_rows = 0
    days_done = 0
    chunk_start = s
    while chunk_start <= e:
        chunk_end = min(chunk_start + timedelta(days=chunk_days - 1), e)
        chunk_size = (chunk_end - chunk_start).days + 1
        typer.echo(
            f"Computing snapshots for wallet {wallet[:10]}... "
            f"day {days_done + 1}-{days_done + chunk_size}/{total_days}"
        )
        result = compute_wallet_snapshots(
            wallet=wallet,
            start_date=chunk_start,
            end_date=chunk_end,
            gold_bucket=gold_bucket,
            dry_run=dry_run,
            skip_ch=skip_ch,
        )
        rows = len(result)
        total_rows += rows
        days_done += chunk_size
        typer.echo(
            f"  {chunk_start} → {chunk_end}: {rows} rows"
            f"{'  [dry-run]' if dry_run else ''}"
        )
        chunk_start = chunk_end + timedelta(days=1)

    typer.echo(f"Done: {total_rows} rows across {total_days} day(s) for {wallet}.")


@app.command(name="freshness")
def freshness() -> None:
    """Display current freshness status of all Gold datasets."""
    from prediction_data.gold.clickhouse import get_client
    from prediction_data.gold.ops_metadata import check_freshness

    ch = get_client()
    rows = check_freshness(ch)

    if not rows:
        typer.echo("No freshness data recorded yet.")
        return

    # Header
    typer.echo(f"{'Dataset':<40} {'State':<8} {'Lag (s)':<10} {'SLA (s)':<10} {'Last Success'}")
    typer.echo("-" * 100)
    for r in rows:
        last_ts = str(r["last_success_at"])[:19] if r["last_success_at"] else "—"
        typer.echo(
            f"{r['dataset']:<40} {r['state']:<8} "
            f"{r['actual_lag_seconds']:<10} {r['expected_lag_seconds']:<10} {last_ts}"
        )


@watchlist_app.command(name="add")
def watchlist_add(
    address: str = typer.Argument(..., help="Wallet address to add."),
    notes: str = typer.Option("", help="Optional notes for this wallet."),
) -> None:
    """Add a wallet address to the watchlist."""
    from prediction_data.gold.watchlist import add_wallet

    add_wallet(address, notes=notes)
    typer.echo(f"Added {address} to watchlist.")


@watchlist_app.command(name="remove")
def watchlist_remove(
    address: str = typer.Argument(..., help="Wallet address to deactivate."),
) -> None:
    """Remove (deactivate) a wallet from the watchlist."""
    from prediction_data.gold.watchlist import remove_wallet

    remove_wallet(address)
    typer.echo(f"Removed {address} from watchlist.")


@watchlist_app.command(name="list")
def watchlist_list(
    all_: bool = typer.Option(False, "--all", help="Include inactive wallets."),
) -> None:
    """List wallets on the watchlist."""
    from prediction_data.gold.watchlist import list_wallets

    wallets = list_wallets(active_only=not all_)
    if not wallets:
        typer.echo("No wallets on watchlist.")
        return
    for w in wallets:
        status = "active" if w["active"] else "inactive"
        notes_part = f"  ({w['notes']})" if w["notes"] else ""
        typer.echo(f"{w['wallet_address']}  [{status}]{notes_part}")
