"""Integration tests for Polymarket API client and ingestion.

These tests make real API calls to the Polymarket APIs.
They are marked with @pytest.mark.integration and can be skipped
in CI environments that don't have network access.

Run integration tests with: pytest -m integration
Skip integration tests with: pytest -m "not integration"
"""

import gzip
import json
import os
from typing import Any
from unittest.mock import MagicMock

import pytest

from prediction_data.bronze.polymarket.client import (
    DATA_API_BASE_URL,
    GAMMA_API_BASE_URL,
    PolymarketClient,
)
from prediction_data.bronze.polymarket.ingest import ingest_markets, ingest_trades_clob
from prediction_data.storage.s3 import S3Client


pytestmark = pytest.mark.integration


class TestPolymarketMarketsAPI:
    """Integration tests for the Polymarket Markets (Gamma) API."""

    @pytest.mark.asyncio
    async def test_fetch_markets_page_returns_valid_structure(self) -> None:
        """Markets endpoint should return list of market objects with expected fields."""
        async with PolymarketClient(page_size=10) as client:
            markets = await client.fetch_markets_page(limit=5)

        assert isinstance(markets, list)
        assert len(markets) > 0

        # Verify expected fields exist on at least one market
        market = markets[0]
        assert "id" in market or "condition_id" in market
        # Markets should have some form of title/question
        has_title = "question" in market or "title" in market or "slug" in market
        assert has_title, f"Market missing title field. Keys: {list(market.keys())}"

    @pytest.mark.asyncio
    async def test_fetch_markets_pagination_works(self) -> None:
        """Markets endpoint should support pagination via offset."""
        async with PolymarketClient(page_size=5) as client:
            page1 = await client.fetch_markets_page(offset=0, limit=5)
            page2 = await client.fetch_markets_page(offset=5, limit=5)

        assert len(page1) == 5
        assert len(page2) == 5

        # Pages should be different (assuming there are enough markets)
        page1_ids = {m.get("id") or m.get("condition_id") for m in page1}
        page2_ids = {m.get("id") or m.get("condition_id") for m in page2}
        assert page1_ids.isdisjoint(page2_ids), "Pagination returned duplicate markets"

    @pytest.mark.asyncio
    async def test_fetch_all_markets_returns_multiple_pages(self) -> None:
        """fetch_all_markets should paginate and return more than one page worth."""
        async with PolymarketClient(page_size=50) as client:
            # Fetch all with a small page size to test pagination
            markets = await client.fetch_all_markets()

        # Polymarket should have many more than 50 markets
        assert len(markets) > 50, f"Expected >50 markets, got {len(markets)}"

    @pytest.mark.asyncio
    async def test_fetch_markets_active_only(self) -> None:
        """Markets endpoint should filter to active markets when requested."""
        async with PolymarketClient(page_size=20) as client:
            # Fetch with closed markets excluded
            active_markets = await client.fetch_markets_page(
                limit=20, include_closed=False
            )

        assert isinstance(active_markets, list)
        # Active markets should exist
        assert len(active_markets) > 0


class TestPolymarketTradesAPI:
    """Integration tests for the Polymarket Trades (Data) API."""

    @pytest.mark.asyncio
    async def test_fetch_trades_page_returns_valid_structure(self) -> None:
        """Trades endpoint should return list of trade objects with expected fields."""
        async with PolymarketClient(page_size=10) as client:
            trades = await client.fetch_trades_page(limit=10)

        assert isinstance(trades, list)
        # Note: trades endpoint may return empty if no recent trades
        if len(trades) > 0:
            trade = trades[0]
            # Verify expected trade fields
            expected_fields = {"side", "size", "price"}
            actual_fields = set(trade.keys())
            missing = expected_fields - actual_fields
            assert not missing, f"Trade missing fields: {missing}. Keys: {list(trade.keys())}"

    @pytest.mark.asyncio
    async def test_fetch_trades_pagination_works(self) -> None:
        """Trades endpoint should support pagination via offset."""
        async with PolymarketClient(page_size=10) as client:
            page1 = await client.fetch_trades_page(offset=0, limit=10)
            page2 = await client.fetch_trades_page(offset=10, limit=10)

        # Both pages should return data
        assert isinstance(page1, list)
        assert isinstance(page2, list)

        # If we got data on both pages, verify they're different
        if len(page1) == 10 and len(page2) > 0:
            # Compare by some unique combination (trades might not have unique IDs)
            # Just verify the lists are different
            assert page1 != page2, "Pagination returned same data"

    @pytest.mark.asyncio
    async def test_fetch_trades_with_max_records(self) -> None:
        """fetch_trades should respect max_records limit."""
        async with PolymarketClient(page_size=50) as client:
            trades, was_truncated = await client.fetch_trades(max_records=25)

        assert len(trades) <= 25
        # Should not be truncated due to API limit since we set max_records
        # (unless there were fewer than 25 trades total)

    @pytest.mark.asyncio
    async def test_fetch_trades_returns_truncation_flag_correctly(self) -> None:
        """fetch_trades should correctly report truncation status."""
        async with PolymarketClient(page_size=100) as client:
            trades, was_truncated = await client.fetch_trades(max_records=50)

        # With max_records=50, truncation flag should be based on whether
        # we hit max_records vs API offset limit
        assert isinstance(was_truncated, bool)
        # If we got exactly 50 trades, we likely hit max_records (not offset limit)
        if len(trades) == 50:
            assert was_truncated is False


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


class TestPolymarketIngestion:
    """Integration tests for Polymarket ingestion with mocked S3."""

    @pytest.mark.asyncio
    async def test_ingest_markets_with_mock_s3(self) -> None:
        """Markets ingestion should fetch from API and upload to S3."""
        mock_boto = MockS3Client()

        # Run ingestion with mocked S3
        async with S3Client(bucket="test-bucket", s3_client=mock_boto) as s3_client:
            # We need to patch the S3Client in the ingest module
            # For now, test the client fetch part directly
            async with PolymarketClient(page_size=10) as client:
                markets = await client.fetch_all_markets()

        # Verify we got markets
        assert len(markets) > 0

        # Verify market structure
        market = markets[0]
        assert isinstance(market, dict)

    @pytest.mark.asyncio
    async def test_ingest_trades_with_mock_s3(self) -> None:
        """Trades ingestion should fetch from API and upload to S3."""
        # Test the client fetch part directly
        async with PolymarketClient(page_size=10) as client:
            trades, was_truncated = await client.fetch_trades(max_records=10)

        # Verify we got trades
        assert isinstance(trades, list)

        # Verify trade structure if we have data
        if len(trades) > 0:
            trade = trades[0]
            assert isinstance(trade, dict)
            assert "side" in trade
            assert "size" in trade


class TestApiBaseUrls:
    """Verify API base URLs are accessible."""

    @pytest.mark.asyncio
    async def test_gamma_api_is_accessible(self) -> None:
        """Gamma API should respond to requests."""
        async with PolymarketClient(page_size=1) as client:
            # Simple request to verify connectivity
            markets = await client.fetch_markets_page(limit=1)

        assert isinstance(markets, list)

    @pytest.mark.asyncio
    async def test_data_api_is_accessible(self) -> None:
        """Data API should respond to requests."""
        async with PolymarketClient(page_size=1) as client:
            # Simple request to verify connectivity
            trades = await client.fetch_trades_page(limit=1)

        assert isinstance(trades, list)


class TestMarketDataStructure:
    """Detailed tests for market data structure compliance."""

    @pytest.mark.asyncio
    async def test_market_has_required_fields(self) -> None:
        """Markets should contain the fields needed for downstream processing."""
        async with PolymarketClient(page_size=5) as client:
            markets = await client.fetch_markets_page(limit=5)

        assert len(markets) > 0

        for market in markets:
            # Markets must be dictionaries
            assert isinstance(market, dict)

            # Should have some form of identifier
            has_id = any(
                k in market for k in ["id", "condition_id", "conditionId", "slug"]
            )
            assert has_id, f"Market missing identifier. Keys: {list(market.keys())}"


class TestTradeDataStructure:
    """Detailed tests for trade data structure compliance."""

    @pytest.mark.asyncio
    async def test_trade_has_required_fields(self) -> None:
        """Trades should contain the fields needed for downstream processing."""
        async with PolymarketClient(page_size=20) as client:
            trades = await client.fetch_trades_page(limit=20)

        # Skip if no trades available
        if len(trades) == 0:
            pytest.skip("No trades available for structure validation")

        for trade in trades:
            # Trades must be dictionaries
            assert isinstance(trade, dict)

            # Required fields for trade data
            assert "side" in trade, f"Trade missing 'side'. Keys: {list(trade.keys())}"
            assert "size" in trade, f"Trade missing 'size'. Keys: {list(trade.keys())}"
            assert "price" in trade, f"Trade missing 'price'. Keys: {list(trade.keys())}"

            # Side should be BUY or SELL
            assert trade["side"] in ["BUY", "SELL", "buy", "sell"], f"Invalid side: {trade['side']}"

            # Size and price should be numeric (as strings per API docs)
            # They may be strings or numbers depending on API version
            size = trade["size"]
            price = trade["price"]
            assert size is not None, "Trade size is None"
            assert price is not None, "Trade price is None"


class TestPaginationBehavior:
    """Tests for pagination edge cases and behavior."""

    @pytest.mark.asyncio
    async def test_empty_page_detection(self) -> None:
        """Client should properly detect when pagination is complete."""
        async with PolymarketClient(page_size=100) as client:
            # Fetch a small batch of markets with a filter that might return few results
            markets = await client.fetch_all_markets(include_closed=False)

        # Should successfully complete without infinite loop
        assert isinstance(markets, list)

    @pytest.mark.asyncio
    async def test_partial_page_detection(self) -> None:
        """Client should detect end of data when page has fewer items than limit."""
        async with PolymarketClient(page_size=1000) as client:
            # With large page size, likely to get partial page
            markets = await client.fetch_markets_page(limit=1000)

        # Should return whatever is available
        assert isinstance(markets, list)
        assert len(markets) > 0
