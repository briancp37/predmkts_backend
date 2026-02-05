"""Markets service layer for ClickHouse queries."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clickhouse_connect.driver.client import Client


async def get_markets(
    client: Client,
    *,
    category: str | None = None,
    search: str | None = None,
    resolved: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Fetch markets from ClickHouse with filtering.

    Args:
        client: ClickHouse client.
        category: Filter by category (exact match).
        search: Search query for question/description (ILIKE).
        resolved: Filter by resolved status.
        limit: Maximum number of results.
        offset: Offset for pagination.

    Returns:
        Tuple of (list of market dicts, total count).
    """
    # TODO: Implement ClickHouse query in GET /markets endpoint feature
    return [], 0
