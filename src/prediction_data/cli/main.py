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
        raise typer.Exit(code=0)
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
        raise typer.Exit(code=0)
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
        raise typer.Exit(code=0)
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
        raise typer.Exit(code=0)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
