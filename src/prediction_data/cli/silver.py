"""Silver layer CLI commands."""

from typing import Annotated

import typer

app = typer.Typer(
    help="Silver layer Iceberg table management.",
    no_args_is_help=True,
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
