"""Tests for Goldsky subgraph client."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prediction_data.bronze.polymarket.goldsky import (
    DEFAULT_PAGE_SIZE,
    GOLDSKY_API_BASE_URL,
    ORDER_FILLED_QUERY,
    GoldskyClient,
    build_query_variables,
)


def _create_mock_response(data: dict[str, Any]) -> MagicMock:
    """Create a mock HTTP response with JSON data."""
    mock_response = MagicMock()
    mock_response.json.return_value = data
    return mock_response


def _make_event(event_id: str) -> dict[str, Any]:
    """Create a test OrderFilledEvent."""
    return {
        "id": event_id,
        "transactionHash": "0xabc",
        "orderHash": "0xdef",
        "timestamp": "1700000000",
        "maker": "0xmaker",
        "taker": "0xtaker",
        "makerAssetId": "123",
        "takerAssetId": "456",
        "makerAmountFilled": "1000000",
        "takerAmountFilled": "2000000",
        "fee": "10000",
    }


class TestBuildQueryVariables:
    """Tests for GraphQL query variable construction."""

    def test_default_cursor(self) -> None:
        result = build_query_variables(timestamp_gte=100, timestamp_lte=200)
        assert result["cursor"] == ""
        assert result["first"] == DEFAULT_PAGE_SIZE

    def test_custom_cursor(self) -> None:
        result = build_query_variables(
            cursor="abc123", timestamp_gte=100, timestamp_lte=200
        )
        assert result["cursor"] == "abc123"

    def test_timestamps_as_strings(self) -> None:
        result = build_query_variables(timestamp_gte=1700000000, timestamp_lte=1700086400)
        assert result["timestamp_gte"] == "1700000000"
        assert result["timestamp_lte"] == "1700086400"

    def test_custom_page_size(self) -> None:
        result = build_query_variables(
            timestamp_gte=100, timestamp_lte=200, page_size=500
        )
        assert result["first"] == 500


class TestGoldskyClientContextManager:
    """Tests for GoldskyClient context manager."""

    @pytest.mark.asyncio
    async def test_requires_context_manager(self) -> None:
        client = GoldskyClient()
        with pytest.raises(RuntimeError, match="must be used as async context manager"):
            await client.fetch_order_filled_page(
                timestamp_gte=100, timestamp_lte=200
            )

    @pytest.mark.asyncio
    async def test_context_manager_creates_http_client(self) -> None:
        with patch("prediction_data.bronze.polymarket.goldsky.HttpClient") as mock_http:
            mock_instance = AsyncMock()
            mock_http.return_value = mock_instance

            async with GoldskyClient() as client:
                assert mock_http.call_count == 1

            mock_instance.__aexit__.assert_called_once()


class TestFetchOrderFilledPage:
    """Tests for fetch_order_filled_page method."""

    @pytest.mark.asyncio
    async def test_basic_fetch(self) -> None:
        events = [_make_event("1"), _make_event("2")]
        response_data = {"data": {"orderFilledEvents": events}}

        with patch("prediction_data.bronze.polymarket.goldsky.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.post = AsyncMock(
                return_value=_create_mock_response(response_data)
            )

            async with GoldskyClient() as client:
                result = await client.fetch_order_filled_page(
                    timestamp_gte=1700000000, timestamp_lte=1700086400
                )

            assert result == events
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_posts_to_goldsky_url(self) -> None:
        response_data = {"data": {"orderFilledEvents": []}}

        with patch("prediction_data.bronze.polymarket.goldsky.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.post = AsyncMock(
                return_value=_create_mock_response(response_data)
            )

            async with GoldskyClient() as client:
                await client.fetch_order_filled_page(
                    timestamp_gte=100, timestamp_lte=200
                )

            call_args = mock_client.post.call_args
            assert call_args[0][0] == GOLDSKY_API_BASE_URL

    @pytest.mark.asyncio
    async def test_sends_graphql_query(self) -> None:
        response_data = {"data": {"orderFilledEvents": []}}

        with patch("prediction_data.bronze.polymarket.goldsky.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.post = AsyncMock(
                return_value=_create_mock_response(response_data)
            )

            async with GoldskyClient() as client:
                await client.fetch_order_filled_page(
                    timestamp_gte=1700000000, timestamp_lte=1700086400
                )

            call_kwargs = mock_client.post.call_args[1]
            payload = call_kwargs["json"]
            assert payload["query"] == ORDER_FILLED_QUERY
            assert payload["variables"]["timestamp_gte"] == "1700000000"
            assert payload["variables"]["timestamp_lte"] == "1700086400"

    @pytest.mark.asyncio
    async def test_passes_cursor(self) -> None:
        response_data = {"data": {"orderFilledEvents": []}}

        with patch("prediction_data.bronze.polymarket.goldsky.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.post = AsyncMock(
                return_value=_create_mock_response(response_data)
            )

            async with GoldskyClient() as client:
                await client.fetch_order_filled_page(
                    timestamp_gte=100, timestamp_lte=200, cursor="mycursor"
                )

            call_kwargs = mock_client.post.call_args[1]
            assert call_kwargs["json"]["variables"]["cursor"] == "mycursor"

    @pytest.mark.asyncio
    async def test_raises_on_graphql_errors(self) -> None:
        response_data = {"errors": [{"message": "bad query"}]}

        with patch("prediction_data.bronze.polymarket.goldsky.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.post = AsyncMock(
                return_value=_create_mock_response(response_data)
            )

            async with GoldskyClient() as client:
                with pytest.raises(RuntimeError, match="Goldsky GraphQL error"):
                    await client.fetch_order_filled_page(
                        timestamp_gte=100, timestamp_lte=200
                    )

    @pytest.mark.asyncio
    async def test_empty_response(self) -> None:
        response_data = {"data": {"orderFilledEvents": []}}

        with patch("prediction_data.bronze.polymarket.goldsky.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.post = AsyncMock(
                return_value=_create_mock_response(response_data)
            )

            async with GoldskyClient() as client:
                result = await client.fetch_order_filled_page(
                    timestamp_gte=100, timestamp_lte=200
                )

            assert result == []


class TestFetchAllOrderFilledEvents:
    """Tests for fetch_all_order_filled_events pagination logic."""

    @pytest.mark.asyncio
    async def test_single_page(self) -> None:
        events = [_make_event(str(i)) for i in range(5)]
        response_data = {"data": {"orderFilledEvents": events}}

        with patch("prediction_data.bronze.polymarket.goldsky.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.post = AsyncMock(
                return_value=_create_mock_response(response_data)
            )

            async with GoldskyClient(page_delay=0) as client:
                result = await client.fetch_all_order_filled_events(
                    timestamp_gte=100, timestamp_lte=200
                )

            assert len(result) == 5
            # Fewer than page_size means single page
            assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_multi_page_pagination(self) -> None:
        page1 = [_make_event(str(i)) for i in range(DEFAULT_PAGE_SIZE)]
        page2 = [_make_event(str(DEFAULT_PAGE_SIZE + i)) for i in range(5)]

        with patch("prediction_data.bronze.polymarket.goldsky.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.post = AsyncMock(
                side_effect=[
                    _create_mock_response({"data": {"orderFilledEvents": page1}}),
                    _create_mock_response({"data": {"orderFilledEvents": page2}}),
                ]
            )

            async with GoldskyClient(page_delay=0) as client:
                result = await client.fetch_all_order_filled_events(
                    timestamp_gte=100, timestamp_lte=200
                )

            assert len(result) == DEFAULT_PAGE_SIZE + 5
            assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_stops_on_empty_page(self) -> None:
        with patch("prediction_data.bronze.polymarket.goldsky.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.post = AsyncMock(
                return_value=_create_mock_response(
                    {"data": {"orderFilledEvents": []}}
                )
            )

            async with GoldskyClient(page_delay=0) as client:
                result = await client.fetch_all_order_filled_events(
                    timestamp_gte=100, timestamp_lte=200
                )

            assert len(result) == 0
            assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_cursor_forwarded_between_pages(self) -> None:
        # Full page triggers pagination; last id becomes cursor for next page
        page1 = [_make_event(f"event_{i}") for i in range(DEFAULT_PAGE_SIZE)]

        with patch("prediction_data.bronze.polymarket.goldsky.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.post = AsyncMock(
                side_effect=[
                    _create_mock_response({"data": {"orderFilledEvents": page1}}),
                    _create_mock_response({"data": {"orderFilledEvents": []}}),
                ]
            )

            async with GoldskyClient(page_delay=0) as client:
                await client.fetch_all_order_filled_events(
                    timestamp_gte=100, timestamp_lte=200
                )

            # First call: empty cursor
            first_vars = mock_client.post.call_args_list[0][1]["json"]["variables"]
            assert first_vars["cursor"] == ""

            # Second call: uses last event id as cursor
            second_vars = mock_client.post.call_args_list[1][1]["json"]["variables"]
            assert second_vars["cursor"] == f"event_{DEFAULT_PAGE_SIZE - 1}"
