"""Kalshi API client with pagination support."""

from typing import Any

import structlog

from prediction_data.core.config import get_settings
from prediction_data.core.http import HttpClient, RetryConfig, TimeoutConfig
from prediction_data.core.logging import get_logger

from .auth import KalshiCredentials, generate_auth_headers, load_credentials_from_settings

# API base URLs
KALSHI_API_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
KALSHI_DEMO_API_BASE_URL = "https://demo-api.kalshi.co/trade-api/v2"

# Pagination limits
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000


class KalshiClient:
    """Async client for the Kalshi API.

    Provides methods to fetch trades and markets with pagination support.
    Uses the shared HTTP client with retry logic and RSA-PSS authentication.

    Example:
        credentials = load_credentials_from_settings()
        async with KalshiClient(credentials) as client:
            # Fetch all markets
            markets = await client.fetch_all_markets()

            # Fetch trades with filtering
            trades = await client.fetch_all_trades(min_ts=1706467200)
    """

    def __init__(
        self,
        credentials: KalshiCredentials,
        *,
        retry_config: RetryConfig | None = None,
        timeout_config: TimeoutConfig | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        base_url: str | None = None,
    ) -> None:
        """Initialize the Kalshi client.

        Args:
            credentials: Kalshi API credentials for authentication.
            retry_config: Retry behavior configuration.
            timeout_config: Timeout settings configuration.
            page_size: Number of records per page for pagination (max 1000).
            base_url: API base URL. If None, uses the configured default.
        """
        self._credentials = credentials
        self._retry_config = retry_config or RetryConfig()
        self._timeout_config = timeout_config or TimeoutConfig()
        self._page_size = min(page_size, MAX_PAGE_SIZE)
        self._base_url = base_url or get_settings().kalshi_api_base_url
        self._http_client: HttpClient | None = None
        self._logger: structlog.stdlib.BoundLogger = get_logger(__name__)

    async def __aenter__(self) -> "KalshiClient":
        """Enter async context manager."""
        self._http_client = HttpClient(
            base_url=self._base_url,
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
        """Exit async context manager."""
        if self._http_client is not None:
            await self._http_client.__aexit__(exc_type, exc_val, exc_tb)
            self._http_client = None

    def _ensure_client(self) -> HttpClient:
        """Ensure client is initialized.

        Returns:
            The HTTP client.

        Raises:
            RuntimeError: If client is not used as context manager.
        """
        if self._http_client is None:
            raise RuntimeError(
                "KalshiClient must be used as async context manager: "
                "async with KalshiClient(credentials) as client: ..."
            )
        return self._http_client

    async def _request_with_auth(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        """Make an authenticated request to the Kalshi API.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: API path (e.g., /markets/trades).
            **kwargs: Additional arguments passed to the HTTP client.

        Returns:
            JSON response data.
        """
        client = self._ensure_client()

        # Generate auth headers (path must not include query params)
        headers = generate_auth_headers(self._credentials, method, path)

        # Merge with any existing headers
        existing_headers = kwargs.pop("headers", {})
        headers.update(existing_headers)

        response = await client.request(method, path, headers=headers, **kwargs)
        return response.json()

    async def fetch_trades_page(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Fetch a single page of trades from the API.

        Args:
            cursor: Pagination cursor from previous response.
            limit: Number of records to fetch (defaults to page_size).
            ticker: Filter by market ticker.
            min_ts: Filter trades after this Unix timestamp.
            max_ts: Filter trades before this Unix timestamp.

        Returns:
            Tuple of (list of trades, cursor for next page or None if done).
        """
        limit = limit or self._page_size

        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if ticker:
            params["ticker"] = ticker
        if min_ts is not None:
            params["min_ts"] = min_ts
        if max_ts is not None:
            params["max_ts"] = max_ts

        self._logger.debug(
            "Fetching trades page",
            cursor=cursor,
            limit=limit,
            ticker=ticker,
        )

        data = await self._request_with_auth("GET", "/markets/trades", params=params)
        trades: list[dict[str, Any]] = data.get("trades", [])
        next_cursor: str | None = data.get("cursor") or None

        self._logger.debug(
            "Fetched trades page",
            count=len(trades),
            has_more=next_cursor is not None,
        )

        return trades, next_cursor

    async def fetch_all_trades(
        self,
        *,
        ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        max_records: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all trades with automatic pagination.

        Paginates through all available trades using cursor-based pagination
        until no more results are returned.

        Args:
            ticker: Filter by market ticker.
            min_ts: Filter trades after this Unix timestamp.
            max_ts: Filter trades before this Unix timestamp.
            max_records: Maximum number of records to fetch (optional).

        Returns:
            List of all trade records.
        """
        all_trades: list[dict[str, Any]] = []
        cursor: str | None = None

        self._logger.info(
            "Starting trades fetch",
            ticker=ticker,
            min_ts=min_ts,
            max_ts=max_ts,
        )

        while True:
            # Check if we've reached max_records
            if max_records is not None and len(all_trades) >= max_records:
                self._logger.info(
                    "Trades fetch complete (max_records reached)",
                    max_records=max_records,
                    total_fetched=len(all_trades),
                )
                break

            trades, cursor = await self.fetch_trades_page(
                cursor=cursor,
                limit=self._page_size,
                ticker=ticker,
                min_ts=min_ts,
                max_ts=max_ts,
            )

            if not trades:
                self._logger.info(
                    "Trades fetch complete (empty page)",
                    total_fetched=len(all_trades),
                )
                break

            all_trades.extend(trades)

            self._logger.info(
                "Trades pagination progress",
                page_count=len(trades),
                total_fetched=len(all_trades),
            )

            if not cursor:
                self._logger.info(
                    "Trades fetch complete (no more pages)",
                    total_fetched=len(all_trades),
                )
                break

        # Trim to max_records if specified
        if max_records is not None and len(all_trades) > max_records:
            all_trades = all_trades[:max_records]

        return all_trades

    async def fetch_markets_page(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        status: str | None = None,
        tickers: str | None = None,
        min_close_ts: int | None = None,
        max_close_ts: int | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Fetch a single page of markets from the API.

        Args:
            cursor: Pagination cursor from previous response.
            limit: Number of records to fetch (defaults to page_size).
            event_ticker: Filter by event ticker (up to 10 comma-separated).
            series_ticker: Filter by series ticker.
            status: Filter by market status (unopened, open, paused, closed, settled).
            tickers: Comma-separated market tickers.
            min_close_ts: Markets closing after this timestamp.
            max_close_ts: Markets closing before this timestamp.

        Returns:
            Tuple of (list of markets, cursor for next page or None if done).
        """
        limit = limit or self._page_size

        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if event_ticker:
            params["event_ticker"] = event_ticker
        if series_ticker:
            params["series_ticker"] = series_ticker
        if status:
            params["status"] = status
        if tickers:
            params["tickers"] = tickers
        if min_close_ts is not None:
            params["min_close_ts"] = min_close_ts
        if max_close_ts is not None:
            params["max_close_ts"] = max_close_ts

        self._logger.debug(
            "Fetching markets page",
            cursor=cursor,
            limit=limit,
            status=status,
        )

        data = await self._request_with_auth("GET", "/markets", params=params)
        markets: list[dict[str, Any]] = data.get("markets", [])
        next_cursor: str | None = data.get("cursor") or None

        self._logger.debug(
            "Fetched markets page",
            count=len(markets),
            has_more=next_cursor is not None,
        )

        return markets, next_cursor

    async def fetch_events_page(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        status: str | None = None,
        with_nested_markets: bool = False,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Fetch a single page of events from the API.

        Args:
            cursor: Pagination cursor from previous response.
            limit: Number of records to fetch (defaults to page_size, max 200).
            status: Filter by event status (open, closed, settled).
            with_nested_markets: Whether to include nested market objects.

        Returns:
            Tuple of (list of events, cursor for next page or None if done).
        """
        limit = min(limit or self._page_size, 200)

        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if status:
            params["status"] = status
        if with_nested_markets:
            params["with_nested_markets"] = "true"

        self._logger.debug(
            "Fetching events page",
            cursor=cursor,
            limit=limit,
            status=status,
        )

        data = await self._request_with_auth("GET", "/events", params=params)
        events: list[dict[str, Any]] = data.get("events", [])
        next_cursor: str | None = data.get("cursor") or None

        self._logger.debug(
            "Fetched events page",
            count=len(events),
            has_more=next_cursor is not None,
        )

        return events, next_cursor

    async def fetch_all_events(
        self,
        *,
        status: str | None = None,
        with_nested_markets: bool = False,
        max_records: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all events with automatic pagination.

        Paginates through all available events using cursor-based pagination
        until no more results are returned.

        Args:
            status: Filter by event status (open, closed, settled).
            with_nested_markets: Whether to include nested market objects.
            max_records: Maximum number of records to fetch (optional).

        Returns:
            List of all event records.
        """
        all_events: list[dict[str, Any]] = []
        cursor: str | None = None

        self._logger.info(
            "Starting events fetch",
            status=status,
        )

        while True:
            # Check if we've reached max_records
            if max_records is not None and len(all_events) >= max_records:
                self._logger.info(
                    "Events fetch complete (max_records reached)",
                    max_records=max_records,
                    total_fetched=len(all_events),
                )
                break

            events, cursor = await self.fetch_events_page(
                cursor=cursor,
                limit=min(self._page_size, 200),
                status=status,
                with_nested_markets=with_nested_markets,
            )

            if not events:
                self._logger.info(
                    "Events fetch complete (empty page)",
                    total_fetched=len(all_events),
                )
                break

            all_events.extend(events)

            self._logger.info(
                "Events pagination progress",
                page_count=len(events),
                total_fetched=len(all_events),
            )

            if not cursor:
                self._logger.info(
                    "Events fetch complete (no more pages)",
                    total_fetched=len(all_events),
                )
                break

        # Trim to max_records if specified
        if max_records is not None and len(all_events) > max_records:
            all_events = all_events[:max_records]

        return all_events

    async def fetch_all_markets(
        self,
        *,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        status: str | None = None,
        tickers: str | None = None,
        min_close_ts: int | None = None,
        max_close_ts: int | None = None,
        max_records: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all markets with automatic pagination.

        Paginates through all available markets using cursor-based pagination
        until no more results are returned.

        Args:
            event_ticker: Filter by event ticker (up to 10 comma-separated).
            series_ticker: Filter by series ticker.
            status: Filter by market status (unopened, open, paused, closed, settled).
            tickers: Comma-separated market tickers.
            min_close_ts: Markets closing after this timestamp.
            max_close_ts: Markets closing before this timestamp.
            max_records: Maximum number of records to fetch (optional).

        Returns:
            List of all market records.
        """
        all_markets: list[dict[str, Any]] = []
        cursor: str | None = None

        self._logger.info(
            "Starting markets fetch",
            event_ticker=event_ticker,
            status=status,
        )

        while True:
            # Check if we've reached max_records
            if max_records is not None and len(all_markets) >= max_records:
                self._logger.info(
                    "Markets fetch complete (max_records reached)",
                    max_records=max_records,
                    total_fetched=len(all_markets),
                )
                break

            markets, cursor = await self.fetch_markets_page(
                cursor=cursor,
                limit=self._page_size,
                event_ticker=event_ticker,
                series_ticker=series_ticker,
                status=status,
                tickers=tickers,
                min_close_ts=min_close_ts,
                max_close_ts=max_close_ts,
            )

            if not markets:
                self._logger.info(
                    "Markets fetch complete (empty page)",
                    total_fetched=len(all_markets),
                )
                break

            all_markets.extend(markets)

            self._logger.info(
                "Markets pagination progress",
                page_count=len(markets),
                total_fetched=len(all_markets),
            )

            if not cursor:
                self._logger.info(
                    "Markets fetch complete (no more pages)",
                    total_fetched=len(all_markets),
                )
                break

        # Trim to max_records if specified
        if max_records is not None and len(all_markets) > max_records:
            all_markets = all_markets[:max_records]

        return all_markets
