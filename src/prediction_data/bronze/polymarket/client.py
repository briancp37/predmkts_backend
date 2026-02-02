"""Polymarket API client with pagination support."""

from dataclasses import dataclass
from typing import Any

import structlog

from prediction_data.core.http import HttpClient, RetryConfig, TimeoutConfig
from prediction_data.core.logging import get_logger

# API base URLs
GAMMA_API_BASE_URL = "https://gamma-api.polymarket.com"
DATA_API_BASE_URL = "https://data-api.polymarket.com"

# Pagination limits
DEFAULT_PAGE_SIZE = 100
MAX_TRADES_OFFSET = 10000
MAX_TRADES_LIMIT = 10000


@dataclass
class PaginationState:
    """Tracks pagination state during fetching.

    Attributes:
        offset: Current offset in the result set.
        limit: Number of records per page.
        total_fetched: Total number of records fetched so far.
        is_complete: Whether all pages have been fetched.
    """

    offset: int = 0
    limit: int = DEFAULT_PAGE_SIZE
    total_fetched: int = 0
    is_complete: bool = False


class PolymarketClient:
    """Async client for Polymarket APIs.

    Provides methods to fetch markets (from Gamma API) and trades (from Data API)
    with pagination support. Uses the shared HTTP client with retry logic.

    Example:
        async with PolymarketClient() as client:
            # Fetch all markets
            markets = await client.fetch_all_markets()

            # Fetch trades (up to offset limit)
            trades = await client.fetch_trades()
    """

    def __init__(
        self,
        *,
        retry_config: RetryConfig | None = None,
        timeout_config: TimeoutConfig | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> None:
        """Initialize the Polymarket client.

        Args:
            retry_config: Retry behavior configuration.
            timeout_config: Timeout settings configuration.
            page_size: Number of records per page for pagination.
        """
        self._retry_config = retry_config or RetryConfig()
        self._timeout_config = timeout_config or TimeoutConfig()
        self._page_size = page_size
        self._gamma_client: HttpClient | None = None
        self._data_client: HttpClient | None = None
        self._logger: structlog.stdlib.BoundLogger = get_logger(__name__)

    async def __aenter__(self) -> "PolymarketClient":
        """Enter async context manager."""
        self._gamma_client = HttpClient(
            base_url=GAMMA_API_BASE_URL,
            retry_config=self._retry_config,
            timeout_config=self._timeout_config,
        )
        self._data_client = HttpClient(
            base_url=DATA_API_BASE_URL,
            retry_config=self._retry_config,
            timeout_config=self._timeout_config,
        )
        await self._gamma_client.__aenter__()
        await self._data_client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit async context manager."""
        if self._gamma_client is not None:
            await self._gamma_client.__aexit__(exc_type, exc_val, exc_tb)
            self._gamma_client = None
        if self._data_client is not None:
            await self._data_client.__aexit__(exc_type, exc_val, exc_tb)
            self._data_client = None

    def _ensure_clients(self) -> tuple[HttpClient, HttpClient]:
        """Ensure clients are initialized.

        Returns:
            Tuple of (gamma_client, data_client).

        Raises:
            RuntimeError: If client is not used as context manager.
        """
        if self._gamma_client is None or self._data_client is None:
            raise RuntimeError(
                "PolymarketClient must be used as async context manager: "
                "async with PolymarketClient() as client: ..."
            )
        return self._gamma_client, self._data_client

    async def fetch_markets_page(
        self,
        *,
        offset: int = 0,
        limit: int | None = None,
        include_closed: bool = True,
    ) -> list[dict[str, Any]]:
        """Fetch a single page of markets from the Gamma API.

        Args:
            offset: Starting position for pagination.
            limit: Number of records to fetch (defaults to page_size).
            include_closed: Whether to include closed/resolved markets.

        Returns:
            List of market records from the API.
        """
        gamma_client, _ = self._ensure_clients()
        limit = limit or self._page_size

        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
        }
        if include_closed:
            params["closed"] = "true"

        self._logger.debug(
            "Fetching markets page",
            offset=offset,
            limit=limit,
        )

        response = await gamma_client.get("/markets", params=params)
        markets: list[dict[str, Any]] = response.json()

        self._logger.debug(
            "Fetched markets page",
            offset=offset,
            count=len(markets),
        )

        return markets

    async def fetch_all_markets(
        self,
        *,
        include_closed: bool = True,
    ) -> list[dict[str, Any]]:
        """Fetch all markets with automatic pagination.

        Paginates through all available markets until no more results
        are returned.

        Args:
            include_closed: Whether to include closed/resolved markets.

        Returns:
            List of all market records.
        """
        gamma_client, _ = self._ensure_clients()
        all_markets: list[dict[str, Any]] = []
        state = PaginationState(limit=self._page_size)

        self._logger.info("Starting markets fetch", include_closed=include_closed)

        while not state.is_complete:
            markets = await self.fetch_markets_page(
                offset=state.offset,
                limit=state.limit,
                include_closed=include_closed,
            )

            if not markets:
                state.is_complete = True
                self._logger.info(
                    "Markets fetch complete (empty page)",
                    total_fetched=state.total_fetched,
                )
                break

            all_markets.extend(markets)
            state.total_fetched += len(markets)
            state.offset += state.limit

            self._logger.info(
                "Markets pagination progress",
                offset=state.offset,
                page_count=len(markets),
                total_fetched=state.total_fetched,
            )

            # If we received fewer records than the limit, we've reached the end
            if len(markets) < state.limit:
                state.is_complete = True
                self._logger.info(
                    "Markets fetch complete (partial page)",
                    total_fetched=state.total_fetched,
                )

        return all_markets

    async def fetch_events_page(
        self,
        *,
        offset: int = 0,
        limit: int | None = None,
        include_closed: bool = True,
    ) -> list[dict[str, Any]]:
        """Fetch a single page of events from the Gamma API.

        Args:
            offset: Starting position for pagination.
            limit: Number of records to fetch (defaults to page_size).
            include_closed: Whether to include closed/resolved events.

        Returns:
            List of event records from the API.
        """
        gamma_client, _ = self._ensure_clients()
        limit = limit or self._page_size

        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
        }
        if include_closed:
            params["closed"] = "true"

        self._logger.debug(
            "Fetching events page",
            offset=offset,
            limit=limit,
        )

        response = await gamma_client.get("/events", params=params)
        events: list[dict[str, Any]] = response.json()

        self._logger.debug(
            "Fetched events page",
            offset=offset,
            count=len(events),
        )

        return events

    async def fetch_all_events(
        self,
        *,
        include_closed: bool = True,
    ) -> list[dict[str, Any]]:
        """Fetch all events with automatic pagination.

        Paginates through all available events until no more results
        are returned.

        Args:
            include_closed: Whether to include closed/resolved events.

        Returns:
            List of all event records.
        """
        gamma_client, _ = self._ensure_clients()
        all_events: list[dict[str, Any]] = []
        state = PaginationState(limit=self._page_size)

        self._logger.info("Starting events fetch", include_closed=include_closed)

        while not state.is_complete:
            events = await self.fetch_events_page(
                offset=state.offset,
                limit=state.limit,
                include_closed=include_closed,
            )

            if not events:
                state.is_complete = True
                self._logger.info(
                    "Events fetch complete (empty page)",
                    total_fetched=state.total_fetched,
                )
                break

            all_events.extend(events)
            state.total_fetched += len(events)
            state.offset += state.limit

            self._logger.info(
                "Events pagination progress",
                offset=state.offset,
                page_count=len(events),
                total_fetched=state.total_fetched,
            )

            # If we received fewer records than the limit, we've reached the end
            if len(events) < state.limit:
                state.is_complete = True
                self._logger.info(
                    "Events fetch complete (partial page)",
                    total_fetched=state.total_fetched,
                )

        return all_events

    async def fetch_markets_incremental(
        self,
        *,
        since_updated_at: str,
        include_closed: bool = True,
    ) -> tuple[list[dict[str, Any]], str]:
        """Fetch markets updated after a cutoff timestamp.

        Paginates through markets ordered by updatedAt descending, collecting
        only records whose updatedAt > since_updated_at. Stops when a record's
        updatedAt <= since_updated_at.

        Args:
            since_updated_at: ISO 8601 cutoff timestamp. Only records with
                updatedAt strictly greater than this value are returned.
            include_closed: Whether to include closed/resolved markets.

        Returns:
            Tuple of (list of changed market records, max_updated_at seen).
            max_updated_at is the highest updatedAt value among returned records,
            or since_updated_at if no new records were found.
        """
        gamma_client, _ = self._ensure_clients()
        collected: list[dict[str, Any]] = []
        max_updated_at = since_updated_at
        offset = 0

        self._logger.info(
            "Starting incremental markets fetch",
            since_updated_at=since_updated_at,
        )

        while True:
            params: dict[str, Any] = {
                "limit": self._page_size,
                "offset": offset,
                "order": "updatedAt",
                "ascending": "false",
            }
            if include_closed:
                params["closed"] = "true"

            response = await gamma_client.get("/markets", params=params)
            page: list[dict[str, Any]] = response.json()

            if not page:
                self._logger.info(
                    "Incremental markets fetch complete (empty page)",
                    collected=len(collected),
                )
                break

            found_old = False
            for record in page:
                if record.get("updatedAt", "") > since_updated_at:
                    collected.append(record)
                    if record["updatedAt"] > max_updated_at:
                        max_updated_at = record["updatedAt"]
                else:
                    found_old = True
                    break

            if found_old:
                self._logger.info(
                    "Incremental markets fetch complete (reached cutoff)",
                    collected=len(collected),
                    max_updated_at=max_updated_at,
                )
                break

            offset += self._page_size
            self._logger.info(
                "Incremental markets pagination progress",
                offset=offset,
                collected=len(collected),
            )

        return collected, max_updated_at

    async def fetch_events_incremental(
        self,
        *,
        since_updated_at: str,
        include_closed: bool = True,
    ) -> tuple[list[dict[str, Any]], str]:
        """Fetch events updated after a cutoff timestamp.

        Paginates through events ordered by updatedAt descending, collecting
        only records whose updatedAt > since_updated_at. Stops when a record's
        updatedAt <= since_updated_at.

        Args:
            since_updated_at: ISO 8601 cutoff timestamp. Only records with
                updatedAt strictly greater than this value are returned.
            include_closed: Whether to include closed/resolved events.

        Returns:
            Tuple of (list of changed event records, max_updated_at seen).
            max_updated_at is the highest updatedAt value among returned records,
            or since_updated_at if no new records were found.
        """
        gamma_client, _ = self._ensure_clients()
        collected: list[dict[str, Any]] = []
        max_updated_at = since_updated_at
        offset = 0

        self._logger.info(
            "Starting incremental events fetch",
            since_updated_at=since_updated_at,
        )

        while True:
            params: dict[str, Any] = {
                "limit": self._page_size,
                "offset": offset,
                "order": "updatedAt",
                "ascending": "false",
            }
            if include_closed:
                params["closed"] = "true"

            response = await gamma_client.get("/events", params=params)
            page: list[dict[str, Any]] = response.json()

            if not page:
                self._logger.info(
                    "Incremental events fetch complete (empty page)",
                    collected=len(collected),
                )
                break

            found_old = False
            for record in page:
                if record.get("updatedAt", "") > since_updated_at:
                    collected.append(record)
                    if record["updatedAt"] > max_updated_at:
                        max_updated_at = record["updatedAt"]
                else:
                    found_old = True
                    break

            if found_old:
                self._logger.info(
                    "Incremental events fetch complete (reached cutoff)",
                    collected=len(collected),
                    max_updated_at=max_updated_at,
                )
                break

            offset += self._page_size
            self._logger.info(
                "Incremental events pagination progress",
                offset=offset,
                collected=len(collected),
            )

        return collected, max_updated_at

    async def fetch_trades_page(
        self,
        *,
        offset: int = 0,
        limit: int | None = None,
        market: str | None = None,
        event_id: str | None = None,
        taker_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Fetch a single page of trades from the Data API.

        Args:
            offset: Starting position for pagination (max 10,000).
            limit: Number of records to fetch (defaults to page_size, max 10,000).
            market: Comma-separated condition IDs to filter by.
            event_id: Comma-separated event IDs to filter by.
            taker_only: Whether to only include taker trades.

        Returns:
            List of trade records from the API.

        Raises:
            ValueError: If offset exceeds the API limit.
        """
        _, data_client = self._ensure_clients()
        limit = limit or self._page_size

        if offset > MAX_TRADES_OFFSET:
            raise ValueError(
                f"Trades API offset cannot exceed {MAX_TRADES_OFFSET}. "
                f"Use market or event filtering to reduce result set."
            )

        params: dict[str, Any] = {
            "limit": min(limit, MAX_TRADES_LIMIT),
            "offset": offset,
            "takerOnly": str(taker_only).lower(),
        }

        # market and eventId are mutually exclusive
        if market is not None and event_id is not None:
            raise ValueError("Cannot specify both 'market' and 'event_id' parameters")

        if market is not None:
            params["market"] = market
        if event_id is not None:
            params["eventId"] = event_id

        self._logger.debug(
            "Fetching trades page",
            offset=offset,
            limit=limit,
        )

        response = await data_client.get("/trades", params=params)
        trades: list[dict[str, Any]] = response.json()

        self._logger.debug(
            "Fetched trades page",
            offset=offset,
            count=len(trades),
        )

        return trades

    async def fetch_trades(
        self,
        *,
        market: str | None = None,
        event_id: str | None = None,
        taker_only: bool = True,
        max_records: int | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Fetch trades with automatic pagination.

        Paginates through trades until no more results are returned
        or the API offset limit is reached.

        Note: The Polymarket trades API has a maximum offset of 10,000.
        If there are more trades than can be fetched, the second return
        value will be True to indicate truncation.

        Args:
            market: Comma-separated condition IDs to filter by.
            event_id: Comma-separated event IDs to filter by.
            taker_only: Whether to only include taker trades.
            max_records: Maximum number of records to fetch (optional).

        Returns:
            Tuple of (list of trade records, was_truncated flag).
            was_truncated is True if we hit the offset limit.
        """
        _, data_client = self._ensure_clients()
        all_trades: list[dict[str, Any]] = []
        state = PaginationState(limit=self._page_size)
        was_truncated = False

        self._logger.info(
            "Starting trades fetch",
            market=market,
            event_id=event_id,
            taker_only=taker_only,
        )

        while not state.is_complete:
            # Check if we would exceed the offset limit
            if state.offset > MAX_TRADES_OFFSET:
                was_truncated = True
                self._logger.warning(
                    "Trades fetch truncated due to API offset limit",
                    max_offset=MAX_TRADES_OFFSET,
                    total_fetched=state.total_fetched,
                )
                break

            # Check if we've reached max_records
            if max_records is not None and state.total_fetched >= max_records:
                self._logger.info(
                    "Trades fetch complete (max_records reached)",
                    max_records=max_records,
                    total_fetched=state.total_fetched,
                )
                break

            trades = await self.fetch_trades_page(
                offset=state.offset,
                limit=state.limit,
                market=market,
                event_id=event_id,
                taker_only=taker_only,
            )

            if not trades:
                state.is_complete = True
                self._logger.info(
                    "Trades fetch complete (empty page)",
                    total_fetched=state.total_fetched,
                )
                break

            all_trades.extend(trades)
            state.total_fetched += len(trades)
            state.offset += state.limit

            self._logger.info(
                "Trades pagination progress",
                offset=state.offset,
                page_count=len(trades),
                total_fetched=state.total_fetched,
            )

            # If we received fewer records than the limit, we've reached the end
            if len(trades) < state.limit:
                state.is_complete = True
                self._logger.info(
                    "Trades fetch complete (partial page)",
                    total_fetched=state.total_fetched,
                )

        # Trim to max_records if specified
        if max_records is not None and len(all_trades) > max_records:
            all_trades = all_trades[:max_records]

        return all_trades, was_truncated
