"""Gold layer CLI commands."""

from __future__ import annotations

from typing import Optional

import typer

from prediction_data.core.config import get_settings

app = typer.Typer(
    help="Gold layer aggregation and ClickHouse serving.",
    no_args_is_help=True,
)

LOADABLE_DIMS = ("dim_platform", "dim_market", "dim_outcome", "dim_wallet")


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
