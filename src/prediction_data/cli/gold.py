"""Gold layer CLI commands."""

from __future__ import annotations

import typer

app = typer.Typer(
    help="Gold layer aggregation and ClickHouse serving.",
    no_args_is_help=True,
)


@app.command(name="status")
def status() -> None:
    """Show Gold layer status and table info."""
    typer.echo("Gold layer status: not yet configured.")
    typer.echo("Run 'prediction-data gold init-tables' after ClickHouse setup.")
