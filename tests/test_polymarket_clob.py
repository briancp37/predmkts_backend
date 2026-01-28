"""Tests for Polymarket CLOB API client."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prediction_data.bronze.polymarket.clob import (
    CLOB_API_BASE_URL,
    END_CURSOR,
    INITIAL_CURSOR,
    ClobCredentials,
    PolymarketClobClient,
    _build_hmac_signature,
    _build_l2_headers,
)


def _make_creds() -> ClobCredentials:
    """Create test credentials."""
    return ClobCredentials(
        address="0xTestAddress",
        api_key="test-api-key",
        secret="dGVzdC1zZWNyZXQtdmFsdWU=",  # base64 of "test-secret-value"
        passphrase="test-passphrase",
    )


def _create_mock_response(data: dict[str, Any]) -> MagicMock:
    """Create a mock HTTP response with JSON data."""
    mock_response = MagicMock()
    mock_response.json.return_value = data
    return mock_response


class TestHmacSignature:
    """Tests for HMAC signature generation."""

    def test_build_hmac_signature_produces_base64(self) -> None:
        """Signature should be a valid base64 string."""
        sig = _build_hmac_signature(
            secret="dGVzdC1zZWNyZXQtdmFsdWU=",
            timestamp="1700000000",
            method="GET",
            request_path="/data/trades",
        )
        assert isinstance(sig, str)
        assert len(sig) > 0

    def test_build_hmac_signature_deterministic(self) -> None:
        """Same inputs should produce the same signature."""
        kwargs = {
            "secret": "dGVzdC1zZWNyZXQtdmFsdWU=",
            "timestamp": "1700000000",
            "method": "GET",
            "request_path": "/data/trades",
        }
        assert _build_hmac_signature(**kwargs) == _build_hmac_signature(**kwargs)

    def test_build_hmac_signature_varies_with_timestamp(self) -> None:
        """Different timestamps should produce different signatures."""
        base = {
            "secret": "dGVzdC1zZWNyZXQtdmFsdWU=",
            "method": "GET",
            "request_path": "/data/trades",
        }
        sig1 = _build_hmac_signature(timestamp="1700000000", **base)
        sig2 = _build_hmac_signature(timestamp="1700000001", **base)
        assert sig1 != sig2


class TestL2Headers:
    """Tests for L2 header construction."""

    def test_build_l2_headers_contains_all_keys(self) -> None:
        """Headers should contain all required POLY_ keys."""
        creds = _make_creds()
        headers = _build_l2_headers(creds, "GET", "/data/trades")
        assert "POLY_ADDRESS" in headers
        assert "POLY_SIGNATURE" in headers
        assert "POLY_TIMESTAMP" in headers
        assert "POLY_API_KEY" in headers
        assert "POLY_PASSPHRASE" in headers

    def test_build_l2_headers_uses_credentials(self) -> None:
        """Headers should use the provided credentials."""
        creds = _make_creds()
        headers = _build_l2_headers(creds, "GET", "/data/trades")
        assert headers["POLY_ADDRESS"] == "0xTestAddress"
        assert headers["POLY_API_KEY"] == "test-api-key"
        assert headers["POLY_PASSPHRASE"] == "test-passphrase"


class TestClobClientContextManager:
    """Tests for PolymarketClobClient context manager."""

    @pytest.mark.asyncio
    async def test_requires_context_manager(self) -> None:
        """Client should require async context manager usage."""
        client = PolymarketClobClient(_make_creds())
        with pytest.raises(RuntimeError, match="must be used as async context manager"):
            await client.fetch_trades_page()

    @pytest.mark.asyncio
    async def test_context_manager_creates_http_client(self) -> None:
        """Context manager should create an HTTP client with CLOB base URL."""
        with patch("prediction_data.bronze.polymarket.clob.HttpClient") as mock_http:
            mock_instance = AsyncMock()
            mock_http.return_value = mock_instance

            async with PolymarketClobClient(_make_creds()) as client:
                assert mock_http.call_count == 1
                assert mock_http.call_args.kwargs["base_url"] == CLOB_API_BASE_URL

            mock_instance.__aexit__.assert_called_once()


class TestFetchTradesPage:
    """Tests for fetch_trades_page method."""

    @pytest.mark.asyncio
    async def test_basic_fetch(self) -> None:
        """Should fetch a page of trades and return next cursor."""
        trades = [{"id": "t1", "side": "BUY"}, {"id": "t2", "side": "SELL"}]
        response_data = {"data": trades, "next_cursor": "abc123"}

        with patch("prediction_data.bronze.polymarket.clob.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.get = AsyncMock(return_value=_create_mock_response(response_data))

            async with PolymarketClobClient(_make_creds()) as client:
                result, next_cursor = await client.fetch_trades_page()

            assert result == trades
            assert next_cursor == "abc123"

    @pytest.mark.asyncio
    async def test_passes_timestamp_filters(self) -> None:
        """Should pass before/after as query params."""
        response_data = {"data": [], "next_cursor": END_CURSOR}

        with patch("prediction_data.bronze.polymarket.clob.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.get = AsyncMock(return_value=_create_mock_response(response_data))

            async with PolymarketClobClient(_make_creds()) as client:
                await client.fetch_trades_page(before=1700000000, after=1699900000)

            call_kwargs = mock_client.get.call_args[1]
            assert call_kwargs["params"]["before"] == 1700000000
            assert call_kwargs["params"]["after"] == 1699900000

    @pytest.mark.asyncio
    async def test_passes_market_filter(self) -> None:
        """Should pass market as query param."""
        response_data = {"data": [], "next_cursor": END_CURSOR}

        with patch("prediction_data.bronze.polymarket.clob.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.get = AsyncMock(return_value=_create_mock_response(response_data))

            async with PolymarketClobClient(_make_creds()) as client:
                await client.fetch_trades_page(market="0xabc")

            call_kwargs = mock_client.get.call_args[1]
            assert call_kwargs["params"]["market"] == "0xabc"

    @pytest.mark.asyncio
    async def test_includes_auth_headers(self) -> None:
        """Should include L2 auth headers in request."""
        response_data = {"data": [], "next_cursor": END_CURSOR}

        with patch("prediction_data.bronze.polymarket.clob.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.get = AsyncMock(return_value=_create_mock_response(response_data))

            async with PolymarketClobClient(_make_creds()) as client:
                await client.fetch_trades_page()

            call_kwargs = mock_client.get.call_args[1]
            headers = call_kwargs["headers"]
            assert "POLY_ADDRESS" in headers
            assert "POLY_SIGNATURE" in headers
            assert "POLY_API_KEY" in headers

    @pytest.mark.asyncio
    async def test_end_cursor_on_missing_field(self) -> None:
        """Should return END_CURSOR if next_cursor not in response."""
        response_data = {"data": []}

        with patch("prediction_data.bronze.polymarket.clob.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.get = AsyncMock(return_value=_create_mock_response(response_data))

            async with PolymarketClobClient(_make_creds()) as client:
                _, next_cursor = await client.fetch_trades_page()

            assert next_cursor == END_CURSOR


class TestFetchAllTrades:
    """Tests for fetch_all_trades pagination logic."""

    @pytest.mark.asyncio
    async def test_single_page(self) -> None:
        """Should return trades from a single page when cursor ends."""
        trades = [{"id": f"t{i}"} for i in range(5)]

        with patch("prediction_data.bronze.polymarket.clob.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.get = AsyncMock(
                return_value=_create_mock_response({"data": trades, "next_cursor": END_CURSOR})
            )

            async with PolymarketClobClient(_make_creds(), page_delay=0) as client:
                result = await client.fetch_all_trades()

            assert len(result) == 5
            assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_multi_page_pagination(self) -> None:
        """Should paginate through multiple pages until END_CURSOR."""
        page1_trades = [{"id": f"t{i}"} for i in range(10)]
        page2_trades = [{"id": f"t{i}"} for i in range(10, 15)]

        with patch("prediction_data.bronze.polymarket.clob.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.get = AsyncMock(
                side_effect=[
                    _create_mock_response({"data": page1_trades, "next_cursor": "cursor2"}),
                    _create_mock_response({"data": page2_trades, "next_cursor": END_CURSOR}),
                ]
            )

            async with PolymarketClobClient(_make_creds(), page_delay=0) as client:
                result = await client.fetch_all_trades()

            assert len(result) == 15
            assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_stops_on_empty_page(self) -> None:
        """Should stop if a page returns empty trades list."""
        with patch("prediction_data.bronze.polymarket.clob.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.get = AsyncMock(
                return_value=_create_mock_response({"data": [], "next_cursor": "cursor2"})
            )

            async with PolymarketClobClient(_make_creds(), page_delay=0) as client:
                result = await client.fetch_all_trades()

            assert len(result) == 0
            assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_passes_filters_to_pages(self) -> None:
        """Should forward timestamp and market filters to each page request."""
        with patch("prediction_data.bronze.polymarket.clob.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.get = AsyncMock(
                return_value=_create_mock_response({"data": [], "next_cursor": END_CURSOR})
            )

            async with PolymarketClobClient(_make_creds(), page_delay=0) as client:
                await client.fetch_all_trades(
                    before=1700000000, after=1699900000, market="0xabc"
                )

            call_kwargs = mock_client.get.call_args[1]
            assert call_kwargs["params"]["before"] == 1700000000
            assert call_kwargs["params"]["after"] == 1699900000
            assert call_kwargs["params"]["market"] == "0xabc"

    @pytest.mark.asyncio
    async def test_cursor_forwarded_between_pages(self) -> None:
        """Should use next_cursor from previous page as cursor for next page."""
        with patch("prediction_data.bronze.polymarket.clob.HttpClient") as mock_http:
            mock_client = AsyncMock()
            mock_http.return_value = mock_client
            mock_client.get = AsyncMock(
                side_effect=[
                    _create_mock_response({"data": [{"id": "1"}], "next_cursor": "page2cursor"}),
                    _create_mock_response({"data": [], "next_cursor": END_CURSOR}),
                ]
            )

            async with PolymarketClobClient(_make_creds(), page_delay=0) as client:
                await client.fetch_all_trades()

            # First call uses initial cursor
            first_call_params = mock_client.get.call_args_list[0][1]["params"]
            assert first_call_params["next_cursor"] == INITIAL_CURSOR

            # Second call uses cursor from first response
            second_call_params = mock_client.get.call_args_list[1][1]["params"]
            assert second_call_params["next_cursor"] == "page2cursor"
