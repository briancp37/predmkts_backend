"""ClickHouse query utilities for the API layer.

Provides async-friendly wrappers around clickhouse_connect with connection pooling,
query builders for common patterns, and Pydantic model conversion helpers.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import lru_cache
from typing import TYPE_CHECKING, Any, TypeVar

import clickhouse_connect
from clickhouse_connect.driver.client import Client
from pydantic import BaseModel

from prediction_data.core.config import get_settings

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence

# Default query timeout in seconds
DEFAULT_QUERY_TIMEOUT = 10

# Thread pool for running sync ClickHouse operations
_executor = ThreadPoolExecutor(max_workers=4)

T = TypeVar("T", bound=BaseModel)


@lru_cache(maxsize=1)
def _get_client() -> Client:
    """Get a cached ClickHouse client (singleton pattern).

    The client is thread-safe and can be reused across requests.

    Returns:
        A connected clickhouse_connect Client.
    """
    settings = get_settings()
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
    )


def get_clickhouse_client() -> Client:
    """Get the ClickHouse client for dependency injection.

    This is the recommended way to get a client in FastAPI endpoints.

    Returns:
        A connected clickhouse_connect Client.
    """
    return _get_client()


@contextmanager
def query_timeout(seconds: int = DEFAULT_QUERY_TIMEOUT) -> Generator[None, None, None]:
    """Context manager to set query timeout.

    Note: This is a placeholder for future timeout implementation.
    ClickHouse query timeout should be set via query settings.

    Args:
        seconds: Timeout in seconds.

    Yields:
        None
    """
    # For now, just yield - timeout is handled at query level
    yield


async def execute_query(
    query: str,
    parameters: dict[str, Any] | None = None,
    *,
    client: Client | None = None,
    timeout: int = DEFAULT_QUERY_TIMEOUT,
) -> list[dict[str, Any]]:
    """Execute a ClickHouse query asynchronously and return results as dicts.

    Runs the query in a thread pool to avoid blocking the event loop.

    Args:
        query: SQL query string.
        parameters: Query parameters for parameterized queries.
        client: Optional ClickHouse client. Uses default if None.
        timeout: Query timeout in seconds.

    Returns:
        List of result rows as dictionaries.
    """
    ch = client or get_clickhouse_client()

    def _run_query() -> list[dict[str, Any]]:
        settings = {"max_execution_time": timeout}
        result = ch.query(query, parameters=parameters, settings=settings)
        # Convert to list of dicts with column names as keys
        columns = result.column_names
        rows = []
        for row in result.result_rows:
            rows.append(dict(zip(columns, row)))
        return rows

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _run_query)


async def execute_query_count(
    query: str,
    parameters: dict[str, Any] | None = None,
    *,
    client: Client | None = None,
    timeout: int = DEFAULT_QUERY_TIMEOUT,
) -> int:
    """Execute a COUNT query and return the count value.

    Args:
        query: SQL query that returns a single count value.
        parameters: Query parameters.
        client: Optional ClickHouse client.
        timeout: Query timeout in seconds.

    Returns:
        The count value from the query.
    """
    ch = client or get_clickhouse_client()

    def _run_query() -> int:
        settings = {"max_execution_time": timeout}
        result = ch.query(query, parameters=parameters, settings=settings)
        if result.result_rows:
            return int(result.first_row[0])
        return 0

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _run_query)


def build_where_clause(
    filters: dict[str, Any],
    *,
    ilike_fields: Sequence[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build a WHERE clause from filter parameters.

    Handles None values (skip filter), exact matches, and ILIKE for search fields.

    Args:
        filters: Dict of field names to filter values.
        ilike_fields: Field names that should use ILIKE (case-insensitive search).

    Returns:
        Tuple of (WHERE clause string without 'WHERE', parameters dict).
        Returns empty string if no filters are active.

    Example:
        >>> clause, params = build_where_clause(
        ...     {"category": "sports", "search": "election"},
        ...     ilike_fields=["question", "description"],
        ... )
        >>> clause
        "category = {category:String} AND (question ILIKE {search:String} OR description ILIKE {search:String})"
    """
    conditions: list[str] = []
    params: dict[str, Any] = {}
    ilike_fields = ilike_fields or []

    for field, value in filters.items():
        if value is None:
            continue

        if field == "search" and ilike_fields:
            # Build ILIKE conditions for search across multiple fields
            search_conditions = [
                f"{f} ILIKE {{search:String}}" for f in ilike_fields
            ]
            if search_conditions:
                conditions.append(f"({' OR '.join(search_conditions)})")
                params["search"] = f"%{value}%"
        elif isinstance(value, bool):
            # Boolean fields
            conditions.append(f"{field} = {{{field}:Bool}}")
            params[field] = value
        elif isinstance(value, int):
            # Integer fields
            conditions.append(f"{field} = {{{field}:Int64}}")
            params[field] = value
        elif isinstance(value, float):
            # Float fields
            conditions.append(f"{field} = {{{field}:Float64}}")
            params[field] = value
        else:
            # String fields (exact match)
            conditions.append(f"{field} = {{{field}:String}}")
            params[field] = str(value)

    return " AND ".join(conditions), params


def build_pagination(
    *,
    limit: int = 50,
    offset: int = 0,
    max_limit: int = 500,
) -> tuple[str, dict[str, Any]]:
    """Build pagination clause (LIMIT/OFFSET).

    Args:
        limit: Maximum rows to return.
        offset: Number of rows to skip.
        max_limit: Maximum allowed limit value.

    Returns:
        Tuple of (LIMIT/OFFSET clause, parameters dict).
    """
    # Clamp limit to max
    actual_limit = min(limit, max_limit)
    actual_offset = max(offset, 0)

    return (
        "LIMIT {limit:UInt64} OFFSET {offset:UInt64}",
        {"limit": actual_limit, "offset": actual_offset},
    )


def build_order_by(
    field: str,
    *,
    direction: str = "DESC",
    allowed_fields: Sequence[str] | None = None,
    default_field: str = "totalVolume",
) -> str:
    """Build ORDER BY clause with validation.

    Args:
        field: Field name to order by.
        direction: Sort direction ('ASC' or 'DESC').
        allowed_fields: List of valid field names. If None, any field is allowed.
        default_field: Default field if provided field is not allowed.

    Returns:
        ORDER BY clause string.
    """
    # Validate direction
    direction = direction.upper()
    if direction not in ("ASC", "DESC"):
        direction = "DESC"

    # Validate field
    if allowed_fields is not None and field not in allowed_fields:
        field = default_field

    return f"ORDER BY {field} {direction}"


def rows_to_models(rows: list[dict[str, Any]], model_class: type[T]) -> list[T]:
    """Convert query result rows to Pydantic models.

    Args:
        rows: List of dicts from query results.
        model_class: Pydantic model class to instantiate.

    Returns:
        List of Pydantic model instances.

    Example:
        >>> from prediction_data.api.markets.schemas import MarketResponse
        >>> markets = rows_to_models(rows, MarketResponse)
    """
    return [model_class.model_validate(row) for row in rows]


async def ping(client: Client | None = None) -> bool:
    """Health-check the ClickHouse connection asynchronously.

    Args:
        client: Optional ClickHouse client.

    Returns:
        True if the server responds to SELECT 1.
    """
    ch = client or get_clickhouse_client()

    def _ping() -> bool:
        try:
            result = ch.query("SELECT 1")
            return bool(result.first_row[0] == 1)
        except Exception:
            return False

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _ping)
