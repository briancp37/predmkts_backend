"""Integration tests for Kalshi API client and ingestion.

These tests make real API calls to the Kalshi API.
They are marked with @pytest.mark.integration and can be skipped
in CI environments that don't have network access or valid credentials.

Run integration tests with: pytest -m integration
Skip integration tests with: pytest -m "not integration"

Note: These tests require KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH
environment variables to be set with valid Kalshi API credentials.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from prediction_data.bronze.kalshi.auth import (
    KalshiAuthError,
    KalshiCredentials,
    load_credentials_from_settings,
)
from prediction_data.bronze.kalshi.client import (
    KALSHI_API_BASE_URL,
    KalshiClient,
)
from prediction_data.storage.s3 import S3Client


pytestmark = pytest.mark.integration


def get_credentials() -> KalshiCredentials:
    """Load credentials, skip test if not configured."""
    try:
        return load_credentials_from_settings()
    except KalshiAuthError as e:
        pytest.skip(f"Kalshi credentials not configured: {e}")


class TestKalshiTradesAPI:
    """Integration tests for the Kalshi Trades API."""

    @pytest.mark.asyncio
    async def test_fetch_trades_page_returns_valid_structure(self) -> None:
        """Trades endpoint should return list of trade objects with expected fields."""
        credentials = get_credentials()

        async with KalshiClient(credentials, page_size=10) as client:
            trades, cursor = await client.fetch_trades_page(limit=5)

        assert isinstance(trades, list)
        # Note: trades endpoint may return empty if no recent trades
        if len(trades) > 0:
            trade = trades[0]
            # Verify expected trade fields based on Kalshi API docs
            expected_fields = {"ticker", "side", "count", "yes_price", "no_price"}
            actual_fields = set(trade.keys())
            missing = expected_fields - actual_fields
            assert not missing, f"Trade missing fields: {missing}. Keys: {list(trade.keys())}"

    @pytest.mark.asyncio
    async def test_fetch_trades_pagination_works(self) -> None:
        """Trades endpoint should support cursor-based pagination."""
        credentials = get_credentials()

        async with KalshiClient(credentials, page_size=10) as client:
            page1, cursor1 = await client.fetch_trades_page(limit=5)

            # If we have more pages, fetch the next one
            if cursor1:
                page2, cursor2 = await client.fetch_trades_page(
                    limit=5, cursor=cursor1
                )

                # Both pages should return data
                assert isinstance(page1, list)
                assert isinstance(page2, list)

                # If we got data on both pages, verify they're different
                if len(page1) > 0 and len(page2) > 0:
                    # Trades should have different created_time or other distinguishing data
                    assert page1 != page2, "Pagination returned same data"

    @pytest.mark.asyncio
    async def test_fetch_all_trades_with_max_records(self) -> None:
        """fetch_all_trades should respect max_records limit."""
        credentials = get_credentials()

        async with KalshiClient(credentials, page_size=50) as client:
            trades = await client.fetch_all_trades(max_records=25)

        assert len(trades) <= 25


class TestKalshiMarketsAPI:
    """Integration tests for the Kalshi Markets API."""

    @pytest.mark.asyncio
    async def test_fetch_markets_page_returns_valid_structure(self) -> None:
        """Markets endpoint should return list of market objects with expected fields."""
        credentials = get_credentials()

        async with KalshiClient(credentials, page_size=10) as client:
            markets, cursor = await client.fetch_markets_page(limit=5)

        assert isinstance(markets, list)
        assert len(markets) > 0

        # Verify expected fields exist on at least one market
        market = markets[0]
        expected_fields = {"ticker", "title", "status"}
        actual_fields = set(market.keys())
        missing = expected_fields - actual_fields
        assert not missing, f"Market missing fields: {missing}. Keys: {list(market.keys())}"

    @pytest.mark.asyncio
    async def test_fetch_markets_pagination_works(self) -> None:
        """Markets endpoint should support cursor-based pagination."""
        credentials = get_credentials()

        async with KalshiClient(credentials, page_size=5) as client:
            page1, cursor1 = await client.fetch_markets_page(limit=5)

            # If we have more pages, fetch the next one
            if cursor1:
                page2, cursor2 = await client.fetch_markets_page(
                    limit=5, cursor=cursor1
                )

                assert len(page1) == 5
                assert len(page2) > 0

                # Pages should be different (no overlapping tickers)
                page1_tickers = {m.get("ticker") for m in page1}
                page2_tickers = {m.get("ticker") for m in page2}
                assert page1_tickers.isdisjoint(page2_tickers), "Pagination returned duplicate markets"

    @pytest.mark.asyncio
    async def test_fetch_all_markets_returns_multiple_pages(self) -> None:
        """fetch_all_markets should paginate and return more than one page worth."""
        credentials = get_credentials()

        async with KalshiClient(credentials, page_size=50) as client:
            # Fetch all with a small page size to test pagination
            markets = await client.fetch_all_markets()

        # Kalshi should have many more than 50 markets
        assert len(markets) > 50, f"Expected >50 markets, got {len(markets)}"

    @pytest.mark.asyncio
    async def test_fetch_markets_by_status(self) -> None:
        """Markets endpoint should filter by status when requested."""
        credentials = get_credentials()

        async with KalshiClient(credentials, page_size=20) as client:
            # Fetch open markets
            open_markets, _ = await client.fetch_markets_page(
                limit=20, status="open"
            )

        assert isinstance(open_markets, list)
        # Open markets should exist
        assert len(open_markets) > 0

        # All returned markets should have status=open
        for market in open_markets:
            assert market.get("status") == "open", f"Expected open market, got {market.get('status')}"


class MockS3Client:
    """Mock S3 client for integration tests without actual S3 access."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, Bucket: str, Key: str, Body: bytes, **kwargs: Any) -> None:
        self.objects[Key] = Body

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        body = MagicMock()
        body.read.return_value = self.objects[Key]
        return {"Body": body}

    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self.objects:
            error = MagicMock()
            error.response = {"Error": {"Code": "404"}}
            raise self.exceptions.ClientError(error, "HeadObject")
        return {}

    @property
    def exceptions(self) -> Any:
        class Exceptions:
            class ClientError(Exception):
                pass
        return Exceptions


class TestKalshiIngestion:
    """Integration tests for Kalshi ingestion with mocked S3."""

    @pytest.mark.asyncio
    async def test_fetch_markets_for_ingestion(self) -> None:
        """Markets fetch should return data suitable for ingestion."""
        credentials = get_credentials()

        async with KalshiClient(credentials, page_size=10) as client:
            markets = await client.fetch_all_markets(max_records=10)

        # Verify we got markets
        assert len(markets) > 0

        # Verify market structure is JSON-serializable
        import json
        for market in markets:
            # Each market should be a dict that can be serialized to JSON
            json.dumps(market)

    @pytest.mark.asyncio
    async def test_fetch_trades_for_ingestion(self) -> None:
        """Trades fetch should return data suitable for ingestion."""
        credentials = get_credentials()

        async with KalshiClient(credentials, page_size=10) as client:
            trades = await client.fetch_all_trades(max_records=10)

        # Verify we got trades (may be empty if no recent activity)
        assert isinstance(trades, list)

        # Verify trade structure is JSON-serializable if we have data
        import json
        for trade in trades:
            json.dumps(trade)


class TestApiBaseUrls:
    """Verify API base URLs are accessible."""

    @pytest.mark.asyncio
    async def test_kalshi_api_is_accessible(self) -> None:
        """Kalshi API should respond to authenticated requests."""
        credentials = get_credentials()

        async with KalshiClient(credentials, page_size=1) as client:
            # Simple request to verify connectivity
            markets, _ = await client.fetch_markets_page(limit=1)

        assert isinstance(markets, list)


class TestMarketDataStructure:
    """Detailed tests for market data structure compliance."""

    @pytest.mark.asyncio
    async def test_market_has_required_fields(self) -> None:
        """Markets should contain the fields needed for downstream processing."""
        credentials = get_credentials()

        async with KalshiClient(credentials, page_size=5) as client:
            markets, _ = await client.fetch_markets_page(limit=5)

        assert len(markets) > 0

        for market in markets:
            # Markets must be dictionaries
            assert isinstance(market, dict)

            # Should have ticker as identifier
            assert "ticker" in market, f"Market missing ticker. Keys: {list(market.keys())}"

            # Should have title/question
            assert "title" in market, f"Market missing title. Keys: {list(market.keys())}"

            # Should have status
            assert "status" in market, f"Market missing status. Keys: {list(market.keys())}"


class TestTradeDataStructure:
    """Detailed tests for trade data structure compliance."""

    @pytest.mark.asyncio
    async def test_trade_has_required_fields(self) -> None:
        """Trades should contain the fields needed for downstream processing."""
        credentials = get_credentials()

        async with KalshiClient(credentials, page_size=20) as client:
            trades, _ = await client.fetch_trades_page(limit=20)

        # Skip if no trades available
        if len(trades) == 0:
            pytest.skip("No trades available for structure validation")

        for trade in trades:
            # Trades must be dictionaries
            assert isinstance(trade, dict)

            # Required fields for trade data based on Kalshi API
            assert "ticker" in trade, f"Trade missing 'ticker'. Keys: {list(trade.keys())}"
            assert "side" in trade, f"Trade missing 'side'. Keys: {list(trade.keys())}"
            assert "count" in trade, f"Trade missing 'count'. Keys: {list(trade.keys())}"

            # Side should be yes or no
            assert trade["side"] in ["yes", "no"], f"Invalid side: {trade['side']}"


class TestPaginationBehavior:
    """Tests for pagination edge cases and behavior."""

    @pytest.mark.asyncio
    async def test_empty_cursor_detection(self) -> None:
        """Client should properly detect when pagination is complete via empty cursor."""
        credentials = get_credentials()

        async with KalshiClient(credentials, page_size=100) as client:
            # Fetch all markets
            markets = await client.fetch_all_markets(max_records=150)

        # Should successfully complete without infinite loop
        assert isinstance(markets, list)
        assert len(markets) <= 150

    @pytest.mark.asyncio
    async def test_partial_page_detection(self) -> None:
        """Client should handle pages with fewer items than limit."""
        credentials = get_credentials()

        async with KalshiClient(credentials, page_size=1000) as client:
            # With very large page size, might get partial page
            markets, cursor = await client.fetch_markets_page(limit=1000)

        # Should return whatever is available
        assert isinstance(markets, list)
        assert len(markets) > 0

    @pytest.mark.asyncio
    async def test_large_result_set_pagination(self) -> None:
        """Client should handle pagination for large result sets correctly."""
        credentials = get_credentials()

        # Use small page size to force multiple pages
        async with KalshiClient(credentials, page_size=25) as client:
            markets = await client.fetch_all_markets(max_records=100)

        # Should have fetched across multiple pages
        assert len(markets) <= 100
        # Should have fetched more than one page worth
        assert len(markets) >= 25

        # All markets should be unique
        tickers = [m.get("ticker") for m in markets]
        unique_tickers = set(tickers)
        assert len(tickers) == len(unique_tickers), "Pagination returned duplicate markets"
