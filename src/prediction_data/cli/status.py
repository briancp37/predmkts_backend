"""Status command group for monitoring and auditing Bronze layer data."""

from enum import Enum
from typing import Annotated

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
