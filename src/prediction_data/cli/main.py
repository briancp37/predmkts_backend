"""Main CLI application for prediction-data."""

from typing import Annotated

import typer

from prediction_data import __version__

app = typer.Typer(
    name="prediction-data",
    help="Data pipeline for prediction market data ingestion and processing.",
    no_args_is_help=True,
)

# Ingest command group placeholder
ingest_app = typer.Typer(
    help="Ingest data from prediction market platforms.",
    no_args_is_help=True,
)
app.add_typer(ingest_app, name="ingest")


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


@ingest_app.command()
def polymarket() -> None:
    """Ingest data from Polymarket."""
    typer.echo("Polymarket ingestion not yet implemented.")


@ingest_app.command()
def kalshi() -> None:
    """Ingest data from Kalshi."""
    typer.echo("Kalshi ingestion not yet implemented.")
