"""Goldsky GraphQL client for querying OrderFilledEvent data from Polymarket orderbook subgraph."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import structlog

from prediction_data.core.http import HttpClient, RetryConfig, TimeoutConfig
from prediction_data.core.logging import get_logger

GOLDSKY_API_BASE_URL = (
    "https://api.goldsky.com/api/public/"
    "project_cl6mb8i9h0003e201j6li0diw/subgraphs/orderbook-subgraph/prod/gn"
)

# Standard subgraph page size
DEFAULT_PAGE_SIZE = 1000

# GraphQL query for OrderFilledEvent with timestamp cursor pagination.
# Orders by timestamp for chronological progress. Uses timestamp_gt for pagination
# which is fast and well-indexed on Goldsky.
ORDER_FILLED_QUERY = """\
query OrderFilledEvents($first: Int!, $timestamp_gt: BigInt!, $timestamp_lte: BigInt!) {
  orderFilledEvents(
    first: $first
    orderBy: timestamp
    orderDirection: asc
    where: { timestamp_gt: $timestamp_gt, timestamp_lte: $timestamp_lte }
  ) {
    id
    transactionHash
    orderHash
    timestamp
    maker
    taker
    makerAssetId
    takerAssetId
    makerAmountFilled
    takerAmountFilled
    fee
  }
}"""


def build_query_variables(
    *,
    timestamp_gt: int,
    timestamp_lte: int,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """Build GraphQL query variables for OrderFilledEvents.

    Args:
        timestamp_gt: Lower bound Unix timestamp (exclusive) for cursor.
        timestamp_lte: Upper bound Unix timestamp (inclusive).
        page_size: Number of records per page.

    Returns:
        Dict of GraphQL variables.
    """
    return {
        "first": page_size,
        "timestamp_gt": str(timestamp_gt),
        "timestamp_lte": str(timestamp_lte),
    }


class GoldskyClient:
    """Async client for Goldsky subgraph API.

    Fetches OrderFilledEvent data via GraphQL POST requests with
    id_gt cursor-based pagination and timestamp filtering.

    Example:
        async with GoldskyClient() as client:
            events = await client.fetch_all_order_filled_events(
                timestamp_gte=1700000000, timestamp_lte=1700086400,
            )
    """

    def __init__(
        self,
        *,
        retry_config: RetryConfig | None = None,
        timeout_config: TimeoutConfig | None = None,
        page_delay: float = 0.2,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> None:
        self._retry_config = retry_config or RetryConfig()
        self._timeout_config = timeout_config or TimeoutConfig()
        self._page_delay = page_delay
        self._page_size = page_size
        self._http_client: HttpClient | None = None
        self._logger: structlog.stdlib.BoundLogger = get_logger(__name__)

    async def __aenter__(self) -> "GoldskyClient":
        self._http_client = HttpClient(
            retry_config=self._retry_config,
            timeout_config=self._timeout_config,
        )
        await self._http_client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        if self._http_client is not None:
            await self._http_client.__aexit__(exc_type, exc_val, exc_tb)
            self._http_client = None

    def _ensure_client(self) -> HttpClient:
        if self._http_client is None:
            raise RuntimeError(
                "GoldskyClient must be used as async context manager: "
                "async with GoldskyClient() as client: ..."
            )
        return self._http_client

    async def fetch_order_filled_page(
        self,
        *,
        timestamp_gt: int,
        timestamp_lte: int,
    ) -> list[dict[str, Any]]:
        """Fetch a single page of OrderFilledEvents.

        Args:
            timestamp_gt: Lower bound Unix timestamp (exclusive) for cursor.
            timestamp_lte: Upper bound Unix timestamp (inclusive).

        Returns:
            List of OrderFilledEvent records. Empty list means no more pages.
        """
        client = self._ensure_client()

        variables = build_query_variables(
            timestamp_gt=timestamp_gt,
            timestamp_lte=timestamp_lte,
            page_size=self._page_size,
        )

        payload = {"query": ORDER_FILLED_QUERY, "variables": variables}

        self._logger.debug(
            "Fetching Goldsky order filled page",
            timestamp_gt=timestamp_gt,
            timestamp_lte=timestamp_lte,
        )

        response = await client.post(GOLDSKY_API_BASE_URL, json=payload)
        data: dict[str, Any] = response.json()

        if "errors" in data:
            raise RuntimeError(f"Goldsky GraphQL error: {data['errors']}")

        events: list[dict[str, Any]] = data.get("data", {}).get("orderFilledEvents", [])

        self._logger.debug(
            "Fetched Goldsky order filled page",
            count=len(events),
        )

        return events

    async def fetch_all_order_filled_events(
        self,
        *,
        timestamp_gte: int,
        timestamp_lte: int,
    ) -> list[dict[str, Any]]:
        """Fetch all OrderFilledEvents for a timestamp range with automatic pagination.

        Uses timestamp cursor pagination for chronological progress. Orders by timestamp
        and uses timestamp_gt for efficient indexed queries on Goldsky.

        Args:
            timestamp_gte: Lower bound Unix timestamp (inclusive).
            timestamp_lte: Upper bound Unix timestamp (inclusive).

        Returns:
            List of all matching OrderFilledEvent records.
        """
        all_events: list[dict[str, Any]] = []
        # Start with timestamp_gt = timestamp_gte - 1 so first page includes timestamp_gte
        cursor_ts = timestamp_gte - 1
        page_count = 0

        self._logger.info(
            "Starting Goldsky order filled fetch",
            timestamp_gte=timestamp_gte,
            timestamp_lte=timestamp_lte,
        )

        while True:
            events = await self.fetch_order_filled_page(
                timestamp_gt=cursor_ts,
                timestamp_lte=timestamp_lte,
            )

            if not events:
                break

            all_events.extend(events)
            page_count += 1
            cursor_ts = int(events[-1]["timestamp"])

            self._logger.info(
                "Goldsky order filled pagination progress",
                page=page_count,
                page_count=len(events),
                total_fetched=len(all_events),
                cursor_timestamp=cursor_ts,
            )

            # If we got fewer than page_size, we've reached the end
            if len(events) < self._page_size:
                break

            # Rate limit between pages
            if self._page_delay > 0:
                await asyncio.sleep(self._page_delay)

        self._logger.info(
            "Goldsky order filled fetch complete",
            total_fetched=len(all_events),
            pages=page_count,
        )

        return all_events

    async def iter_order_filled_batches(
        self,
        *,
        timestamp_gte: int,
        timestamp_lte: int,
        batch_size: int = 500_000,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """Yield batches of OrderFilledEvents, flushing every ``batch_size`` records.

        Same pagination logic as :meth:`fetch_all_order_filled_events` but
        yields batches instead of accumulating everything in memory.

        Args:
            timestamp_gte: Lower bound Unix timestamp (inclusive).
            timestamp_lte: Upper bound Unix timestamp (inclusive).
            batch_size: Number of records per yielded batch.

        Yields:
            Lists of OrderFilledEvent records, each up to ``batch_size`` long.
        """
        buffer: list[dict[str, Any]] = []
        # Start with timestamp_gt = timestamp_gte - 1 so first page includes timestamp_gte
        cursor_ts = timestamp_gte - 1
        page_count = 0
        total_fetched = 0

        self._logger.info(
            "Starting Goldsky order filled batched fetch",
            timestamp_gte=timestamp_gte,
            timestamp_lte=timestamp_lte,
            batch_size=batch_size,
        )

        while True:
            events = await self.fetch_order_filled_page(
                timestamp_gt=cursor_ts,
                timestamp_lte=timestamp_lte,
            )

            if not events:
                break

            buffer.extend(events)
            page_count += 1
            total_fetched += len(events)
            cursor_ts = int(events[-1]["timestamp"])

            self._logger.info(
                "Goldsky order filled pagination progress",
                page=page_count,
                page_count=len(events),
                total_fetched=total_fetched,
                buffer_size=len(buffer),
                cursor_timestamp=cursor_ts,
            )

            # Flush buffer when it reaches batch_size
            while len(buffer) >= batch_size:
                yield buffer[:batch_size]
                buffer = buffer[batch_size:]

            # If we got fewer than page_size, we've reached the end
            if len(events) < self._page_size:
                break

            if self._page_delay > 0:
                await asyncio.sleep(self._page_delay)

        # Yield any remaining records
        if buffer:
            yield buffer

        self._logger.info(
            "Goldsky order filled batched fetch complete",
            total_fetched=total_fetched,
            pages=page_count,
        )
