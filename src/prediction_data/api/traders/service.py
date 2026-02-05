"""Traders service layer for ClickHouse queries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from clickhouse_connect.driver.client import Client


async def get_traders(
    client: Client,
    *,
    search: str | None = None,
    sort_by: str = "totalPnl",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch traders from ClickHouse with filtering.

    Args:
        client: ClickHouse client.
        search: Search query for wallet address or username (ILIKE).
        sort_by: Field to sort by.
        sort_order: Sort direction ('asc' or 'desc').
        limit: Maximum number of results.
        offset: Offset for pagination.

    Returns:
        Tuple of (list of trader dicts, total count).
    """
    # TODO: Implement ClickHouse query in GET /traders endpoint feature
    return [], 0
