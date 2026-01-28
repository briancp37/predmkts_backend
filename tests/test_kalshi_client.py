"""Tests for Kalshi API client."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prediction_data.bronze.kalshi.auth import KalshiCredentials
from prediction_data.bronze.kalshi.client import (
    DEFAULT_PAGE_SIZE,
    KALSHI_API_BASE_URL,
    KALSHI_DEMO_API_BASE_URL,
    MAX_PAGE_SIZE,
    KalshiClient,
)
from prediction_data.core.http import RetryConfig, TimeoutConfig


def _create_mock_credentials() -> KalshiCredentials:
    """Create mock Kalshi credentials for testing."""
    mock_private_key = MagicMock()
    return KalshiCredentials(
        api_key_id="test-key-id",
        private_key=mock_private_key,
    )


def _create_mock_response(data: dict[str, Any]) -> MagicMock:
    """Create a mock HTTP response with JSON data."""
    mock_response = MagicMock()
    mock_response.json.return_value = data
    return mock_response


class TestKalshiClientInit:
    """Tests for KalshiClient initialization."""

    def test_default_configuration(self) -> None:
        """Client should have default configuration."""
        credentials = _create_mock_credentials()
        # Provide base_url to avoid calling get_settings()
        client = KalshiClient(credentials, base_url=KALSHI_API_BASE_URL)
        assert client._page_size == DEFAULT_PAGE_SIZE
        assert client._retry_config is not None
        assert client._timeout_config is not None
        assert client._credentials == credentials

    def test_custom_page_size(self) -> None:
        """Client should accept custom page size."""
        credentials = _create_mock_credentials()
        client = KalshiClient(credentials, page_size=500, base_url=KALSHI_API_BASE_URL)
        assert client._page_size == 500

    def test_page_size_capped_at_max(self) -> None:
        """Client should cap page size at MAX_PAGE_SIZE."""
        credentials = _create_mock_credentials()
        client = KalshiClient(credentials, page_size=2000, base_url=KALSHI_API_BASE_URL)
        assert client._page_size == MAX_PAGE_SIZE

    def test_custom_retry_config(self) -> None:
        """Client should accept custom retry configuration."""
        credentials = _create_mock_credentials()
        retry_config = RetryConfig(max_retries=5)
        client = KalshiClient(credentials, retry_config=retry_config, base_url=KALSHI_API_BASE_URL)
        assert client._retry_config.max_retries == 5

    def test_custom_timeout_config(self) -> None:
        """Client should accept custom timeout configuration."""
        credentials = _create_mock_credentials()
        timeout_config = TimeoutConfig(connect=20.0)
        client = KalshiClient(
            credentials, timeout_config=timeout_config, base_url=KALSHI_API_BASE_URL
        )
        assert client._timeout_config.connect == 20.0

    def test_custom_base_url(self) -> None:
        """Client should accept custom base URL."""
        credentials = _create_mock_credentials()
        client = KalshiClient(credentials, base_url=KALSHI_DEMO_API_BASE_URL)
        assert client._base_url == KALSHI_DEMO_API_BASE_URL


class TestKalshiClientContextManager:
    """Tests for KalshiClient context manager."""

    @pytest.mark.asyncio
    async def test_requires_context_manager(self) -> None:
        """Client should require async context manager usage."""
        credentials = _create_mock_credentials()
        client = KalshiClient(credentials, base_url=KALSHI_API_BASE_URL)
        with pytest.raises(RuntimeError, match="must be used as async context manager"):
            await client.fetch_markets_page()

    @pytest.mark.asyncio
    async def test_context_manager_enters_and_exits(self) -> None:
        """Client should properly enter and exit context manager."""
        credentials = _create_mock_credentials()

        with patch("prediction_data.bronze.kalshi.client.HttpClient") as mock_http:
            mock_instance = AsyncMock()
            mock_http.return_value = mock_instance

            async with KalshiClient(credentials, base_url=KALSHI_API_BASE_URL) as client:
                assert mock_http.call_count == 1
                # Verify base URL is passed
                call_kwargs = mock_http.call_args.kwargs
                assert "base_url" in call_kwargs

            # Should have closed the client
            assert mock_instance.__aexit__.call_count == 1


class TestFetchTradesPage:
    """Tests for fetch_trades_page method."""

    @pytest.mark.asyncio
    async def test_fetch_trades_page_basic(self) -> None:
        """Should fetch a page of trades."""
        credentials = _create_mock_credentials()
        trades = [
            {"trade_id": "1", "ticker": "TICKER1", "yes_price": 55},
            {"trade_id": "2", "ticker": "TICKER2", "yes_price": 45},
        ]
        response_data = {"trades": trades, "cursor": "next-cursor"}

        with (
            patch("prediction_data.bronze.kalshi.client.HttpClient") as mock_http,
            patch(
                "prediction_data.bronze.kalshi.client.generate_auth_headers"
            ) as mock_auth,
        ):
            mock_instance = AsyncMock()
            mock_http.return_value = mock_instance
            mock_instance.request = AsyncMock(
                return_value=_create_mock_response(response_data)
            )
            mock_auth.return_value = {"KALSHI-ACCESS-KEY": "test"}

            async with KalshiClient(credentials, base_url=KALSHI_API_BASE_URL) as client:
                result_trades, cursor = await client.fetch_trades_page()

            assert result_trades == trades
            assert cursor == "next-cursor"
            mock_instance.request.assert_called_once()
            call_args = mock_instance.request.call_args
            assert call_args[0][0] == "GET"
            assert call_args[0][1] == "/markets/trades"
            assert call_args[1]["params"]["limit"] == DEFAULT_PAGE_SIZE

    @pytest.mark.asyncio
    async def test_fetch_trades_page_with_cursor(self) -> None:
        """Should include cursor in request."""
        credentials = _create_mock_credentials()
        response_data = {"trades": [], "cursor": ""}

        with (
            patch("prediction_data.bronze.kalshi.client.HttpClient") as mock_http,
            patch(
                "prediction_data.bronze.kalshi.client.generate_auth_headers"
            ) as mock_auth,
        ):
            mock_instance = AsyncMock()
            mock_http.return_value = mock_instance
            mock_instance.request = AsyncMock(
                return_value=_create_mock_response(response_data)
            )
            mock_auth.return_value = {}

            async with KalshiClient(credentials, base_url=KALSHI_API_BASE_URL) as client:
                await client.fetch_trades_page(cursor="prev-cursor")

            call_args = mock_instance.request.call_args
            assert call_args[1]["params"]["cursor"] == "prev-cursor"

    @pytest.mark.asyncio
    async def test_fetch_trades_page_with_filters(self) -> None:
        """Should include filters in request."""
        credentials = _create_mock_credentials()
        response_data = {"trades": [], "cursor": ""}

        with (
            patch("prediction_data.bronze.kalshi.client.HttpClient") as mock_http,
            patch(
                "prediction_data.bronze.kalshi.client.generate_auth_headers"
            ) as mock_auth,
        ):
            mock_instance = AsyncMock()
            mock_http.return_value = mock_instance
            mock_instance.request = AsyncMock(
                return_value=_create_mock_response(response_data)
            )
            mock_auth.return_value = {}

            async with KalshiClient(credentials, base_url=KALSHI_API_BASE_URL) as client:
                await client.fetch_trades_page(
                    ticker="TEST-TICKER",
                    min_ts=1700000000,
                    max_ts=1700100000,
                )

            call_args = mock_instance.request.call_args
            params = call_args[1]["params"]
            assert params["ticker"] == "TEST-TICKER"
            assert params["min_ts"] == 1700000000
            assert params["max_ts"] == 1700100000

    @pytest.mark.asyncio
    async def test_fetch_trades_page_empty_cursor_returns_none(self) -> None:
        """Should return None for empty cursor."""
        credentials = _create_mock_credentials()
        response_data = {"trades": [], "cursor": ""}

        with (
            patch("prediction_data.bronze.kalshi.client.HttpClient") as mock_http,
            patch(
                "prediction_data.bronze.kalshi.client.generate_auth_headers"
            ) as mock_auth,
        ):
            mock_instance = AsyncMock()
            mock_http.return_value = mock_instance
            mock_instance.request = AsyncMock(
                return_value=_create_mock_response(response_data)
            )
            mock_auth.return_value = {}

            async with KalshiClient(credentials, base_url=KALSHI_API_BASE_URL) as client:
                _, cursor = await client.fetch_trades_page()

            assert cursor is None


class TestFetchAllTrades:
    """Tests for fetch_all_trades method."""

    @pytest.mark.asyncio
    async def test_fetch_all_trades_single_page(self) -> None:
        """Should fetch all trades when they fit in one page."""
        credentials = _create_mock_credentials()
        trades = [{"trade_id": str(i)} for i in range(50)]

        with (
            patch("prediction_data.bronze.kalshi.client.HttpClient") as mock_http,
            patch(
                "prediction_data.bronze.kalshi.client.generate_auth_headers"
            ) as mock_auth,
        ):
            mock_instance = AsyncMock()
            mock_http.return_value = mock_instance
            mock_instance.request = AsyncMock(
                return_value=_create_mock_response({"trades": trades, "cursor": ""})
            )
            mock_auth.return_value = {}

            async with KalshiClient(
                credentials, page_size=100, base_url=KALSHI_API_BASE_URL
            ) as client:
                result = await client.fetch_all_trades()

            assert len(result) == 50
            assert mock_instance.request.call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_all_trades_multiple_pages(self) -> None:
        """Should paginate through all trades."""
        credentials = _create_mock_credentials()
        page1 = [{"trade_id": str(i)} for i in range(100)]
        page2 = [{"trade_id": str(i)} for i in range(100, 150)]

        with (
            patch("prediction_data.bronze.kalshi.client.HttpClient") as mock_http,
            patch(
                "prediction_data.bronze.kalshi.client.generate_auth_headers"
            ) as mock_auth,
        ):
            mock_instance = AsyncMock()
            mock_http.return_value = mock_instance
            mock_instance.request = AsyncMock(
                side_effect=[
                    _create_mock_response({"trades": page1, "cursor": "cursor1"}),
                    _create_mock_response({"trades": page2, "cursor": ""}),
                ]
            )
            mock_auth.return_value = {}

            async with KalshiClient(
                credentials, page_size=100, base_url=KALSHI_API_BASE_URL
            ) as client:
                result = await client.fetch_all_trades()

            assert len(result) == 150
            assert mock_instance.request.call_count == 2

    @pytest.mark.asyncio
    async def test_fetch_all_trades_empty_page_terminates(self) -> None:
        """Should stop when an empty page is returned."""
        credentials = _create_mock_credentials()
        page1 = [{"trade_id": str(i)} for i in range(100)]

        with (
            patch("prediction_data.bronze.kalshi.client.HttpClient") as mock_http,
            patch(
                "prediction_data.bronze.kalshi.client.generate_auth_headers"
            ) as mock_auth,
        ):
            mock_instance = AsyncMock()
            mock_http.return_value = mock_instance
            mock_instance.request = AsyncMock(
                side_effect=[
                    _create_mock_response({"trades": page1, "cursor": "cursor1"}),
                    _create_mock_response({"trades": [], "cursor": ""}),
                ]
            )
            mock_auth.return_value = {}

            async with KalshiClient(
                credentials, page_size=100, base_url=KALSHI_API_BASE_URL
            ) as client:
                result = await client.fetch_all_trades()

            assert len(result) == 100
            assert mock_instance.request.call_count == 2

    @pytest.mark.asyncio
    async def test_fetch_all_trades_with_max_records(self) -> None:
        """Should respect max_records limit."""
        credentials = _create_mock_credentials()
        full_page = [{"trade_id": str(i)} for i in range(100)]

        with (
            patch("prediction_data.bronze.kalshi.client.HttpClient") as mock_http,
            patch(
                "prediction_data.bronze.kalshi.client.generate_auth_headers"
            ) as mock_auth,
        ):
            mock_instance = AsyncMock()
            mock_http.return_value = mock_instance
            mock_instance.request = AsyncMock(
                side_effect=[
                    _create_mock_response({"trades": full_page, "cursor": "cursor1"}),
                    _create_mock_response({"trades": full_page, "cursor": ""}),
                ]
            )
            mock_auth.return_value = {}

            async with KalshiClient(
                credentials, page_size=100, base_url=KALSHI_API_BASE_URL
            ) as client:
                result = await client.fetch_all_trades(max_records=150)

            assert len(result) == 150

    @pytest.mark.asyncio
    async def test_fetch_all_trades_with_filters(self) -> None:
        """Should pass filters to page requests."""
        credentials = _create_mock_credentials()

        with (
            patch("prediction_data.bronze.kalshi.client.HttpClient") as mock_http,
            patch(
                "prediction_data.bronze.kalshi.client.generate_auth_headers"
            ) as mock_auth,
        ):
            mock_instance = AsyncMock()
            mock_http.return_value = mock_instance
            mock_instance.request = AsyncMock(
                return_value=_create_mock_response({"trades": [], "cursor": ""})
            )
            mock_auth.return_value = {}

            async with KalshiClient(credentials, base_url=KALSHI_API_BASE_URL) as client:
                await client.fetch_all_trades(
                    ticker="TEST", min_ts=1700000000, max_ts=1700100000
                )

            call_args = mock_instance.request.call_args
            params = call_args[1]["params"]
            assert params["ticker"] == "TEST"
            assert params["min_ts"] == 1700000000
            assert params["max_ts"] == 1700100000


class TestFetchMarketsPage:
    """Tests for fetch_markets_page method."""

    @pytest.mark.asyncio
    async def test_fetch_markets_page_basic(self) -> None:
        """Should fetch a page of markets."""
        credentials = _create_mock_credentials()
        markets = [
            {"ticker": "MARKET1", "status": "open"},
            {"ticker": "MARKET2", "status": "closed"},
        ]
        response_data = {"markets": markets, "cursor": "next-cursor"}

        with (
            patch("prediction_data.bronze.kalshi.client.HttpClient") as mock_http,
            patch(
                "prediction_data.bronze.kalshi.client.generate_auth_headers"
            ) as mock_auth,
        ):
            mock_instance = AsyncMock()
            mock_http.return_value = mock_instance
            mock_instance.request = AsyncMock(
                return_value=_create_mock_response(response_data)
            )
            mock_auth.return_value = {}

            async with KalshiClient(credentials, base_url=KALSHI_API_BASE_URL) as client:
                result_markets, cursor = await client.fetch_markets_page()

            assert result_markets == markets
            assert cursor == "next-cursor"
            mock_instance.request.assert_called_once()
            call_args = mock_instance.request.call_args
            assert call_args[0][0] == "GET"
            assert call_args[0][1] == "/markets"

    @pytest.mark.asyncio
    async def test_fetch_markets_page_with_filters(self) -> None:
        """Should include filters in request."""
        credentials = _create_mock_credentials()
        response_data = {"markets": [], "cursor": ""}

        with (
            patch("prediction_data.bronze.kalshi.client.HttpClient") as mock_http,
            patch(
                "prediction_data.bronze.kalshi.client.generate_auth_headers"
            ) as mock_auth,
        ):
            mock_instance = AsyncMock()
            mock_http.return_value = mock_instance
            mock_instance.request = AsyncMock(
                return_value=_create_mock_response(response_data)
            )
            mock_auth.return_value = {}

            async with KalshiClient(credentials, base_url=KALSHI_API_BASE_URL) as client:
                await client.fetch_markets_page(
                    event_ticker="EVENT-1",
                    series_ticker="SERIES-1",
                    status="open",
                    tickers="TICK1,TICK2",
                    min_close_ts=1700000000,
                    max_close_ts=1700100000,
                )

            call_args = mock_instance.request.call_args
            params = call_args[1]["params"]
            assert params["event_ticker"] == "EVENT-1"
            assert params["series_ticker"] == "SERIES-1"
            assert params["status"] == "open"
            assert params["tickers"] == "TICK1,TICK2"
            assert params["min_close_ts"] == 1700000000
            assert params["max_close_ts"] == 1700100000


class TestFetchAllMarkets:
    """Tests for fetch_all_markets method."""

    @pytest.mark.asyncio
    async def test_fetch_all_markets_single_page(self) -> None:
        """Should fetch all markets when they fit in one page."""
        credentials = _create_mock_credentials()
        markets = [{"ticker": f"MARKET{i}"} for i in range(50)]

        with (
            patch("prediction_data.bronze.kalshi.client.HttpClient") as mock_http,
            patch(
                "prediction_data.bronze.kalshi.client.generate_auth_headers"
            ) as mock_auth,
        ):
            mock_instance = AsyncMock()
            mock_http.return_value = mock_instance
            mock_instance.request = AsyncMock(
                return_value=_create_mock_response({"markets": markets, "cursor": ""})
            )
            mock_auth.return_value = {}

            async with KalshiClient(
                credentials, page_size=100, base_url=KALSHI_API_BASE_URL
            ) as client:
                result = await client.fetch_all_markets()

            assert len(result) == 50
            assert mock_instance.request.call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_all_markets_multiple_pages(self) -> None:
        """Should paginate through all markets."""
        credentials = _create_mock_credentials()
        page1 = [{"ticker": f"MARKET{i}"} for i in range(100)]
        page2 = [{"ticker": f"MARKET{i}"} for i in range(100, 150)]

        with (
            patch("prediction_data.bronze.kalshi.client.HttpClient") as mock_http,
            patch(
                "prediction_data.bronze.kalshi.client.generate_auth_headers"
            ) as mock_auth,
        ):
            mock_instance = AsyncMock()
            mock_http.return_value = mock_instance
            mock_instance.request = AsyncMock(
                side_effect=[
                    _create_mock_response({"markets": page1, "cursor": "cursor1"}),
                    _create_mock_response({"markets": page2, "cursor": ""}),
                ]
            )
            mock_auth.return_value = {}

            async with KalshiClient(
                credentials, page_size=100, base_url=KALSHI_API_BASE_URL
            ) as client:
                result = await client.fetch_all_markets()

            assert len(result) == 150
            assert mock_instance.request.call_count == 2

    @pytest.mark.asyncio
    async def test_fetch_all_markets_with_max_records(self) -> None:
        """Should respect max_records limit."""
        credentials = _create_mock_credentials()
        full_page = [{"ticker": f"MARKET{i}"} for i in range(100)]

        with (
            patch("prediction_data.bronze.kalshi.client.HttpClient") as mock_http,
            patch(
                "prediction_data.bronze.kalshi.client.generate_auth_headers"
            ) as mock_auth,
        ):
            mock_instance = AsyncMock()
            mock_http.return_value = mock_instance
            mock_instance.request = AsyncMock(
                side_effect=[
                    _create_mock_response({"markets": full_page, "cursor": "cursor1"}),
                    _create_mock_response({"markets": full_page, "cursor": ""}),
                ]
            )
            mock_auth.return_value = {}

            async with KalshiClient(
                credentials, page_size=100, base_url=KALSHI_API_BASE_URL
            ) as client:
                result = await client.fetch_all_markets(max_records=150)

            assert len(result) == 150


class TestAuthenticationIntegration:
    """Tests for authentication header integration."""

    @pytest.mark.asyncio
    async def test_auth_headers_are_generated_per_request(self) -> None:
        """Should generate auth headers for each request."""
        credentials = _create_mock_credentials()

        with (
            patch("prediction_data.bronze.kalshi.client.HttpClient") as mock_http,
            patch(
                "prediction_data.bronze.kalshi.client.generate_auth_headers"
            ) as mock_auth,
        ):
            mock_instance = AsyncMock()
            mock_http.return_value = mock_instance
            mock_instance.request = AsyncMock(
                return_value=_create_mock_response({"trades": [], "cursor": ""})
            )
            mock_auth.return_value = {
                "KALSHI-ACCESS-KEY": "test-key",
                "KALSHI-ACCESS-TIMESTAMP": "12345",
                "KALSHI-ACCESS-SIGNATURE": "sig",
            }

            async with KalshiClient(credentials, base_url=KALSHI_API_BASE_URL) as client:
                await client.fetch_trades_page()

            # Verify auth headers were generated
            mock_auth.assert_called_once_with(credentials, "GET", "/markets/trades")

            # Verify headers were passed to request
            call_args = mock_instance.request.call_args
            headers = call_args[1]["headers"]
            assert headers["KALSHI-ACCESS-KEY"] == "test-key"
            assert headers["KALSHI-ACCESS-TIMESTAMP"] == "12345"
            assert headers["KALSHI-ACCESS-SIGNATURE"] == "sig"


class TestApiUrls:
    """Tests for API URL constants."""

    def test_production_api_url(self) -> None:
        """Production API URL should be correct."""
        assert KALSHI_API_BASE_URL == "https://api.elections.kalshi.com/trade-api/v2"

    def test_demo_api_url(self) -> None:
        """Demo API URL should be correct."""
        assert KALSHI_DEMO_API_BASE_URL == "https://demo-api.kalshi.co/trade-api/v2"


class TestPageSizeConstants:
    """Tests for pagination constants."""

    def test_default_page_size(self) -> None:
        """Default page size should be 100."""
        assert DEFAULT_PAGE_SIZE == 100

    def test_max_page_size(self) -> None:
        """Max page size should be 1000."""
        assert MAX_PAGE_SIZE == 1000
