"""Tests for Polymarket API client."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prediction_data.bronze.polymarket.client import (
    DATA_API_BASE_URL,
    DEFAULT_PAGE_SIZE,
    GAMMA_API_BASE_URL,
    MAX_TRADES_OFFSET,
    PaginationState,
    PolymarketClient,
)
from prediction_data.core.http import RetryConfig, TimeoutConfig


class TestPaginationState:
    """Tests for PaginationState dataclass."""

    def test_default_values(self) -> None:
        """PaginationState should have sensible defaults."""
        state = PaginationState()
        assert state.offset == 0
        assert state.limit == DEFAULT_PAGE_SIZE
        assert state.total_fetched == 0
        assert state.is_complete is False

    def test_custom_values(self) -> None:
        """PaginationState should accept custom values."""
        state = PaginationState(
            offset=100,
            limit=50,
            total_fetched=500,
            is_complete=True,
        )
        assert state.offset == 100
        assert state.limit == 50
        assert state.total_fetched == 500
        assert state.is_complete is True


class TestPolymarketClientInit:
    """Tests for PolymarketClient initialization."""

    def test_default_configuration(self) -> None:
        """Client should have default configuration."""
        client = PolymarketClient()
        assert client._page_size == DEFAULT_PAGE_SIZE
        assert client._retry_config is not None
        assert client._timeout_config is not None

    def test_custom_page_size(self) -> None:
        """Client should accept custom page size."""
        client = PolymarketClient(page_size=50)
        assert client._page_size == 50

    def test_custom_retry_config(self) -> None:
        """Client should accept custom retry configuration."""
        retry_config = RetryConfig(max_retries=5)
        client = PolymarketClient(retry_config=retry_config)
        assert client._retry_config.max_retries == 5

    def test_custom_timeout_config(self) -> None:
        """Client should accept custom timeout configuration."""
        timeout_config = TimeoutConfig(connect=20.0)
        client = PolymarketClient(timeout_config=timeout_config)
        assert client._timeout_config.connect == 20.0


class TestPolymarketClientContextManager:
    """Tests for PolymarketClient context manager."""

    @pytest.mark.asyncio
    async def test_requires_context_manager(self) -> None:
        """Client should require async context manager usage."""
        client = PolymarketClient()
        with pytest.raises(RuntimeError, match="must be used as async context manager"):
            await client.fetch_markets_page()

    @pytest.mark.asyncio
    async def test_context_manager_enters_and_exits(self) -> None:
        """Client should properly enter and exit context manager."""
        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_instance = AsyncMock()
            mock_http.return_value = mock_instance

            async with PolymarketClient() as client:
                # Should have created two HTTP clients
                assert mock_http.call_count == 2

                # Verify base URLs
                calls = mock_http.call_args_list
                assert calls[0].kwargs["base_url"] == GAMMA_API_BASE_URL
                assert calls[1].kwargs["base_url"] == DATA_API_BASE_URL

            # Should have closed both clients
            assert mock_instance.__aexit__.call_count == 2


def _create_mock_response(data: list[dict[str, Any]]) -> MagicMock:
    """Create a mock HTTP response with JSON data."""
    mock_response = MagicMock()
    mock_response.json.return_value = data
    return mock_response


class TestFetchMarketsPage:
    """Tests for fetch_markets_page method."""

    @pytest.mark.asyncio
    async def test_fetch_markets_page_basic(self) -> None:
        """Should fetch a page of markets."""
        markets = [{"id": 1, "title": "Market 1"}, {"id": 2, "title": "Market 2"}]

        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            mock_gamma.get = AsyncMock(return_value=_create_mock_response(markets))

            async with PolymarketClient() as client:
                result = await client.fetch_markets_page()

            assert result == markets
            mock_gamma.get.assert_called_once()
            call_args = mock_gamma.get.call_args
            assert call_args[0][0] == "/markets"
            assert call_args[1]["params"]["limit"] == DEFAULT_PAGE_SIZE
            assert call_args[1]["params"]["offset"] == 0
            assert call_args[1]["params"]["closed"] == "true"

    @pytest.mark.asyncio
    async def test_fetch_markets_page_with_offset(self) -> None:
        """Should fetch markets with specified offset."""
        markets = [{"id": 3, "title": "Market 3"}]

        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            mock_gamma.get = AsyncMock(return_value=_create_mock_response(markets))

            async with PolymarketClient() as client:
                result = await client.fetch_markets_page(offset=100, limit=50)

            assert result == markets
            call_args = mock_gamma.get.call_args
            assert call_args[1]["params"]["offset"] == 100
            assert call_args[1]["params"]["limit"] == 50

    @pytest.mark.asyncio
    async def test_fetch_markets_page_exclude_closed(self) -> None:
        """Should exclude closed markets when specified."""
        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            mock_gamma.get = AsyncMock(return_value=_create_mock_response([]))

            async with PolymarketClient() as client:
                await client.fetch_markets_page(include_closed=False)

            call_args = mock_gamma.get.call_args
            assert "closed" not in call_args[1]["params"]


class TestFetchAllMarkets:
    """Tests for fetch_all_markets method."""

    @pytest.mark.asyncio
    async def test_fetch_all_markets_single_page(self) -> None:
        """Should fetch all markets when they fit in one page."""
        markets = [{"id": i, "title": f"Market {i}"} for i in range(50)]

        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            # Return markets on first call, empty on second
            mock_gamma.get = AsyncMock(
                side_effect=[
                    _create_mock_response(markets),
                ]
            )

            async with PolymarketClient(page_size=100) as client:
                result = await client.fetch_all_markets()

            assert len(result) == 50
            assert mock_gamma.get.call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_all_markets_multiple_pages(self) -> None:
        """Should paginate through all markets."""
        page1 = [{"id": i, "title": f"Market {i}"} for i in range(100)]
        page2 = [{"id": i, "title": f"Market {i}"} for i in range(100, 150)]

        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            mock_gamma.get = AsyncMock(
                side_effect=[
                    _create_mock_response(page1),
                    _create_mock_response(page2),
                ]
            )

            async with PolymarketClient(page_size=100) as client:
                result = await client.fetch_all_markets()

            assert len(result) == 150
            assert mock_gamma.get.call_count == 2

    @pytest.mark.asyncio
    async def test_fetch_all_markets_empty_page_terminates(self) -> None:
        """Should stop when an empty page is returned."""
        # Use a full page followed by empty to test empty page termination
        page1 = [{"id": i} for i in range(100)]  # Full page

        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            mock_gamma.get = AsyncMock(
                side_effect=[
                    _create_mock_response(page1),
                    _create_mock_response([]),  # Empty page terminates
                ]
            )

            async with PolymarketClient(page_size=100) as client:
                result = await client.fetch_all_markets()

            assert len(result) == 100
            assert mock_gamma.get.call_count == 2


class TestFetchEventsPage:
    """Tests for fetch_events_page method."""

    @pytest.mark.asyncio
    async def test_fetch_events_page_basic(self) -> None:
        """Should fetch a page of events."""
        events = [{"id": 1, "title": "Event 1"}, {"id": 2, "title": "Event 2"}]

        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            mock_gamma.get = AsyncMock(return_value=_create_mock_response(events))

            async with PolymarketClient() as client:
                result = await client.fetch_events_page()

            assert result == events
            mock_gamma.get.assert_called_once()
            call_args = mock_gamma.get.call_args
            assert call_args[0][0] == "/events"
            assert call_args[1]["params"]["limit"] == DEFAULT_PAGE_SIZE
            assert call_args[1]["params"]["offset"] == 0
            assert call_args[1]["params"]["closed"] == "true"

    @pytest.mark.asyncio
    async def test_fetch_events_page_with_offset(self) -> None:
        """Should fetch events with specified offset."""
        events = [{"id": 3, "title": "Event 3"}]

        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            mock_gamma.get = AsyncMock(return_value=_create_mock_response(events))

            async with PolymarketClient() as client:
                result = await client.fetch_events_page(offset=100, limit=50)

            assert result == events
            call_args = mock_gamma.get.call_args
            assert call_args[1]["params"]["offset"] == 100
            assert call_args[1]["params"]["limit"] == 50

    @pytest.mark.asyncio
    async def test_fetch_events_page_exclude_closed(self) -> None:
        """Should exclude closed events when specified."""
        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            mock_gamma.get = AsyncMock(return_value=_create_mock_response([]))

            async with PolymarketClient() as client:
                await client.fetch_events_page(include_closed=False)

            call_args = mock_gamma.get.call_args
            assert "closed" not in call_args[1]["params"]


class TestFetchAllEvents:
    """Tests for fetch_all_events method."""

    @pytest.mark.asyncio
    async def test_fetch_all_events_single_page(self) -> None:
        """Should fetch all events when they fit in one page."""
        events = [{"id": i, "title": f"Event {i}"} for i in range(50)]

        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            mock_gamma.get = AsyncMock(
                side_effect=[
                    _create_mock_response(events),
                ]
            )

            async with PolymarketClient(page_size=100) as client:
                result = await client.fetch_all_events()

            assert len(result) == 50
            assert mock_gamma.get.call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_all_events_multiple_pages(self) -> None:
        """Should paginate through all events."""
        page1 = [{"id": i, "title": f"Event {i}"} for i in range(100)]
        page2 = [{"id": i, "title": f"Event {i}"} for i in range(100, 150)]

        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            mock_gamma.get = AsyncMock(
                side_effect=[
                    _create_mock_response(page1),
                    _create_mock_response(page2),
                ]
            )

            async with PolymarketClient(page_size=100) as client:
                result = await client.fetch_all_events()

            assert len(result) == 150
            assert mock_gamma.get.call_count == 2

    @pytest.mark.asyncio
    async def test_fetch_all_events_empty_page_terminates(self) -> None:
        """Should stop when an empty page is returned."""
        page1 = [{"id": i} for i in range(100)]

        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            mock_gamma.get = AsyncMock(
                side_effect=[
                    _create_mock_response(page1),
                    _create_mock_response([]),
                ]
            )

            async with PolymarketClient(page_size=100) as client:
                result = await client.fetch_all_events()

            assert len(result) == 100
            assert mock_gamma.get.call_count == 2


class TestFetchTradesPage:
    """Tests for fetch_trades_page method."""

    @pytest.mark.asyncio
    async def test_fetch_trades_page_basic(self) -> None:
        """Should fetch a page of trades."""
        trades = [{"side": "BUY", "size": "100"}, {"side": "SELL", "size": "50"}]

        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            mock_data.get = AsyncMock(return_value=_create_mock_response(trades))

            async with PolymarketClient() as client:
                result = await client.fetch_trades_page()

            assert result == trades
            mock_data.get.assert_called_once()
            call_args = mock_data.get.call_args
            assert call_args[0][0] == "/trades"
            assert call_args[1]["params"]["limit"] == DEFAULT_PAGE_SIZE
            assert call_args[1]["params"]["offset"] == 0
            assert call_args[1]["params"]["takerOnly"] == "true"

    @pytest.mark.asyncio
    async def test_fetch_trades_page_with_market_filter(self) -> None:
        """Should fetch trades filtered by market."""
        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            mock_data.get = AsyncMock(return_value=_create_mock_response([]))

            async with PolymarketClient() as client:
                await client.fetch_trades_page(market="condition123")

            call_args = mock_data.get.call_args
            assert call_args[1]["params"]["market"] == "condition123"

    @pytest.mark.asyncio
    async def test_fetch_trades_page_with_event_filter(self) -> None:
        """Should fetch trades filtered by event."""
        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            mock_data.get = AsyncMock(return_value=_create_mock_response([]))

            async with PolymarketClient() as client:
                await client.fetch_trades_page(event_id="event456")

            call_args = mock_data.get.call_args
            assert call_args[1]["params"]["eventId"] == "event456"

    @pytest.mark.asyncio
    async def test_fetch_trades_page_market_and_event_exclusive(self) -> None:
        """Should raise error if both market and event_id are specified."""
        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            async with PolymarketClient() as client:
                with pytest.raises(ValueError, match="Cannot specify both"):
                    await client.fetch_trades_page(market="m1", event_id="e1")

    @pytest.mark.asyncio
    async def test_fetch_trades_page_offset_limit_exceeded(self) -> None:
        """Should raise error if offset exceeds API limit."""
        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            async with PolymarketClient() as client:
                with pytest.raises(ValueError, match="offset cannot exceed"):
                    await client.fetch_trades_page(offset=MAX_TRADES_OFFSET + 1)

    @pytest.mark.asyncio
    async def test_fetch_trades_page_taker_only_false(self) -> None:
        """Should set takerOnly to false when specified."""
        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            mock_data.get = AsyncMock(return_value=_create_mock_response([]))

            async with PolymarketClient() as client:
                await client.fetch_trades_page(taker_only=False)

            call_args = mock_data.get.call_args
            assert call_args[1]["params"]["takerOnly"] == "false"


class TestFetchTrades:
    """Tests for fetch_trades method."""

    @pytest.mark.asyncio
    async def test_fetch_trades_single_page(self) -> None:
        """Should fetch all trades when they fit in one page."""
        trades = [{"side": "BUY", "size": str(i)} for i in range(50)]

        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            mock_data.get = AsyncMock(side_effect=[_create_mock_response(trades)])

            async with PolymarketClient(page_size=100) as client:
                result, was_truncated = await client.fetch_trades()

            assert len(result) == 50
            assert was_truncated is False
            assert mock_data.get.call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_trades_multiple_pages(self) -> None:
        """Should paginate through trades."""
        page1 = [{"side": "BUY", "size": str(i)} for i in range(100)]
        page2 = [{"side": "SELL", "size": str(i)} for i in range(50)]

        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            mock_data.get = AsyncMock(
                side_effect=[
                    _create_mock_response(page1),
                    _create_mock_response(page2),
                ]
            )

            async with PolymarketClient(page_size=100) as client:
                result, was_truncated = await client.fetch_trades()

            assert len(result) == 150
            assert was_truncated is False

    @pytest.mark.asyncio
    async def test_fetch_trades_offset_limit_truncation(self) -> None:
        """Should truncate and signal when offset limit is reached."""
        # Create enough pages to exceed the offset limit
        page_size = 100
        pages_before_limit = (MAX_TRADES_OFFSET // page_size) + 1

        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            # Always return full pages
            full_page = [{"side": "BUY"} for _ in range(page_size)]
            mock_data.get = AsyncMock(return_value=_create_mock_response(full_page))

            async with PolymarketClient(page_size=page_size) as client:
                result, was_truncated = await client.fetch_trades()

            assert was_truncated is True
            # Should have fetched up to the offset limit
            assert mock_data.get.call_count == pages_before_limit

    @pytest.mark.asyncio
    async def test_fetch_trades_with_max_records(self) -> None:
        """Should respect max_records limit."""
        full_page = [{"side": "BUY"} for _ in range(100)]

        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            mock_data.get = AsyncMock(
                side_effect=[
                    _create_mock_response(full_page),
                    _create_mock_response(full_page),
                ]
            )

            async with PolymarketClient(page_size=100) as client:
                result, was_truncated = await client.fetch_trades(max_records=150)

            assert len(result) == 150
            assert was_truncated is False

    @pytest.mark.asyncio
    async def test_fetch_trades_with_market_filter(self) -> None:
        """Should pass market filter to pages."""
        with patch("prediction_data.bronze.polymarket.client.HttpClient") as mock_http:
            mock_gamma = AsyncMock()
            mock_data = AsyncMock()
            mock_http.side_effect = [mock_gamma, mock_data]

            mock_data.get = AsyncMock(return_value=_create_mock_response([]))

            async with PolymarketClient() as client:
                await client.fetch_trades(market="condition123")

            call_args = mock_data.get.call_args
            assert call_args[1]["params"]["market"] == "condition123"


class TestApiUrls:
    """Tests for API URL constants."""

    def test_gamma_api_url(self) -> None:
        """Gamma API URL should be correct."""
        assert GAMMA_API_BASE_URL == "https://gamma-api.polymarket.com"

    def test_data_api_url(self) -> None:
        """Data API URL should be correct."""
        assert DATA_API_BASE_URL == "https://data-api.polymarket.com"
