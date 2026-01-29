"""Polymarket CLOB API client with L2 auth and cursor-based pagination."""

import asyncio
import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any

import structlog

from prediction_data.core.config import get_settings
from prediction_data.core.http import HttpClient, RetryConfig, TimeoutConfig
from prediction_data.core.logging import get_logger

CLOB_API_BASE_URL = "https://clob.polymarket.com"

# Cursor sentinel indicating no more pages
END_CURSOR = "LTE="

# Default initial cursor (base64 of "0")
INITIAL_CURSOR = "MA=="

# Default page size for CLOB trades
CLOB_DEFAULT_PAGE_SIZE = 500


@dataclass
class ClobCredentials:
    """Polymarket CLOB L2 API credentials.

    Attributes:
        address: Polygon wallet public address.
        api_key: Builder API key.
        secret: Builder API secret (base64-encoded).
        passphrase: Builder API passphrase.
    """

    address: str
    api_key: str
    secret: str
    passphrase: str


def load_clob_credentials() -> ClobCredentials:
    """Load CLOB credentials from application settings.

    Returns:
        ClobCredentials populated from environment variables.

    Raises:
        ValueError: If required CLOB credentials are missing.
    """
    settings = get_settings()

    address = getattr(settings, "polygon_wallet_address", None)
    api_key = getattr(settings, "polymarket_builder_api_key", None)
    secret = getattr(settings, "polymarket_builder_secret", None)
    passphrase = getattr(settings, "polymarket_builder_passphrase", None)

    missing = []
    if not address:
        missing.append("POLYGON_WALLET_ADDRESS")
    if not api_key:
        missing.append("POLYMARKET_BUILDER_API_KEY")
    if not secret:
        missing.append("POLYMARKET_BUILDER_SECRET")
    if not passphrase:
        missing.append("POLYMARKET_BUILDER_PASSPHRASE")

    if missing:
        raise ValueError(
            f"Missing required CLOB credentials: {', '.join(missing)}. "
            f"Set these environment variables in your .env file."
        )

    return ClobCredentials(
        address=address,  # type: ignore[arg-type]
        api_key=api_key,  # type: ignore[arg-type]
        secret=secret,  # type: ignore[arg-type]
        passphrase=passphrase,  # type: ignore[arg-type]
    )


def _build_hmac_signature(secret: str, timestamp: str, method: str, request_path: str) -> str:
    """Build HMAC-SHA256 signature for CLOB L2 auth.

    Args:
        secret: Base64-encoded API secret.
        timestamp: Unix timestamp as string.
        method: HTTP method (e.g. "GET").
        request_path: Request path (e.g. "/data/trades"). Query params excluded.

    Returns:
        Base64-encoded HMAC-SHA256 signature.
    """
    decoded_secret = base64.urlsafe_b64decode(secret)
    message = timestamp + method + request_path
    h = hmac.new(decoded_secret, message.encode("utf-8"), hashlib.sha256)
    return base64.urlsafe_b64encode(h.digest()).decode("utf-8")


def _build_l2_headers(credentials: ClobCredentials, method: str, request_path: str) -> dict[str, str]:
    """Build L2 authentication headers for a CLOB API request.

    Args:
        credentials: CLOB API credentials.
        method: HTTP method.
        request_path: Request path (query params excluded from signature).

    Returns:
        Dict of auth headers.
    """
    timestamp = str(int(time.time()))
    signature = _build_hmac_signature(credentials.secret, timestamp, method, request_path)
    return {
        "POLY_ADDRESS": credentials.address,
        "POLY_SIGNATURE": signature,
        "POLY_TIMESTAMP": timestamp,
        "POLY_API_KEY": credentials.api_key,
        "POLY_PASSPHRASE": credentials.passphrase,
    }


class PolymarketClobClient:
    """Async client for Polymarket CLOB API with L2 auth.

    Fetches trades via GET /data/trades with cursor-based pagination
    and optional timestamp filtering (before/after).

    Example:
        async with PolymarketClobClient(credentials) as client:
            trades = await client.fetch_all_trades(after=start_ts, before=end_ts)
    """

    def __init__(
        self,
        credentials: ClobCredentials,
        *,
        retry_config: RetryConfig | None = None,
        timeout_config: TimeoutConfig | None = None,
        page_delay: float = 0.2,
    ) -> None:
        """Initialize the CLOB client.

        Args:
            credentials: L2 API credentials.
            retry_config: Retry behavior configuration.
            timeout_config: Timeout settings configuration.
            page_delay: Seconds to sleep between paginated requests.
        """
        self._credentials = credentials
        self._retry_config = retry_config or RetryConfig()
        self._timeout_config = timeout_config or TimeoutConfig()
        self._page_delay = page_delay
        self._http_client: HttpClient | None = None
        self._logger: structlog.stdlib.BoundLogger = get_logger(__name__)

    async def __aenter__(self) -> "PolymarketClobClient":
        """Enter async context manager."""
        self._http_client = HttpClient(
            base_url=CLOB_API_BASE_URL,
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
        """Ensure HTTP client is initialized.

        Returns:
            The HTTP client.

        Raises:
            RuntimeError: If client is not used as context manager.
        """
        if self._http_client is None:
            raise RuntimeError(
                "PolymarketClobClient must be used as async context manager: "
                "async with PolymarketClobClient(creds) as client: ..."
            )
        return self._http_client

    async def fetch_trades_page(
        self,
        *,
        before: int | None = None,
        after: int | None = None,
        market: str | None = None,
        maker: str | None = None,
        cursor: str = INITIAL_CURSOR,
    ) -> tuple[list[dict[str, Any]], str]:
        """Fetch a single page of trades from the CLOB API.

        Args:
            before: Unix timestamp upper bound filter.
            after: Unix timestamp lower bound filter.
            market: Condition ID to filter by.
            maker: Maker address to filter by.
            cursor: Pagination cursor.

        Returns:
            Tuple of (trades list, next_cursor). next_cursor is END_CURSOR
            when no more pages remain.
        """
        client = self._ensure_client()
        request_path = "/data/trades"

        headers = _build_l2_headers(self._credentials, "GET", request_path)

        params: dict[str, Any] = {"next_cursor": cursor}
        if before is not None:
            params["before"] = before
        if after is not None:
            params["after"] = after
        if market is not None:
            params["market"] = market
        if maker is not None:
            params["maker"] = maker

        self._logger.debug(
            "Fetching CLOB trades page",
            cursor=cursor,
            before=before,
            after=after,
        )

        response = await client.get(request_path, params=params, headers=headers)
        data: dict[str, Any] = response.json()

        trades: list[dict[str, Any]] = data.get("data", [])
        next_cursor: str = data.get("next_cursor", END_CURSOR)

        self._logger.debug(
            "Fetched CLOB trades page",
            count=len(trades),
            next_cursor=next_cursor,
        )

        return trades, next_cursor

    async def fetch_all_trades(
        self,
        *,
        before: int | None = None,
        after: int | None = None,
        market: str | None = None,
        maker: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all trades with automatic cursor-based pagination.

        Paginates through all matching trades until the end cursor is reached.
        Sleeps between pages to respect rate limits.

        Args:
            before: Unix timestamp upper bound filter.
            after: Unix timestamp lower bound filter.
            market: Condition ID to filter by.
            maker: Maker address to filter by.

        Returns:
            List of all matching trade records.
        """
        client = self._ensure_client()
        all_trades: list[dict[str, Any]] = []
        cursor = INITIAL_CURSOR
        page_count = 0

        self._logger.info(
            "Starting CLOB trades fetch",
            before=before,
            after=after,
            market=market,
        )

        while cursor != END_CURSOR:
            trades, cursor = await self.fetch_trades_page(
                before=before,
                after=after,
                market=market,
                maker=maker,
                cursor=cursor,
            )

            if not trades:
                break

            all_trades.extend(trades)
            page_count += 1

            self._logger.info(
                "CLOB trades pagination progress",
                page=page_count,
                page_count=len(trades),
                total_fetched=len(all_trades),
            )

            # Rate limit between pages
            if cursor != END_CURSOR and self._page_delay > 0:
                await asyncio.sleep(self._page_delay)

        self._logger.info(
            "CLOB trades fetch complete",
            total_fetched=len(all_trades),
            pages=page_count,
        )

        return all_trades
