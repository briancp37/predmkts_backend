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
