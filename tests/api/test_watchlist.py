"""Tests for watchlist API endpoints.

Tests the watchlist flow: add market -> list watchlist -> remove market.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient

from tests.api.conftest import TEST_MARKET_ID, make_mock_ch_response


class TestAddToWatchlist:
    """Tests for POST /api/v1/watchlist."""

    @pytest.mark.asyncio
    async def test_add_to_watchlist_success(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        mock_clickhouse_client: MagicMock,
    ) -> None:
        """Test adding a market to watchlist."""
        # Mock market existence check to return True
        mock_clickhouse_client.query.return_value = make_mock_ch_response(
            columns=["1"], rows=[(1,)]
        )

        response = await client.post(
            "/api/v1/watchlist",
            headers=auth_headers,
            json={"marketId": TEST_MARKET_ID},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["marketId"] == TEST_MARKET_ID
        assert "id" in data
        assert "createdAt" in data

    @pytest.mark.asyncio
    async def test_add_to_watchlist_no_auth(self, client: AsyncClient) -> None:
        """Test adding to watchlist without authentication fails."""
        response = await client.post(
            "/api/v1/watchlist",
            json={"marketId": TEST_MARKET_ID},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_add_to_watchlist_market_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        mock_clickhouse_client: MagicMock,
    ) -> None:
        """Test adding non-existent market fails."""
        # Mock market existence check to return empty (not found)
        mock_clickhouse_client.query.return_value = make_mock_ch_response(
            columns=[], rows=[]
        )

        response = await client.post(
            "/api/v1/watchlist",
            headers=auth_headers,
            json={"marketId": TEST_MARKET_ID},
        )

        assert response.status_code == 400
        assert "Market not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_add_to_watchlist_duplicate(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        mock_clickhouse_client: MagicMock,
    ) -> None:
        """Test adding duplicate market fails."""
        # Mock market existence check
        mock_clickhouse_client.query.return_value = make_mock_ch_response(
            columns=["1"], rows=[(1,)]
        )

        # Add market first time
        response1 = await client.post(
            "/api/v1/watchlist",
            headers=auth_headers,
            json={"marketId": TEST_MARKET_ID},
        )
        assert response1.status_code == 201

        # Try to add same market again
        response2 = await client.post(
            "/api/v1/watchlist",
            headers=auth_headers,
            json={"marketId": TEST_MARKET_ID},
        )
        assert response2.status_code == 400
        assert "already in watchlist" in response2.json()["detail"]

    @pytest.mark.asyncio
    async def test_add_to_watchlist_invalid_market_id(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test adding market with invalid ID format fails validation."""
        response = await client.post(
            "/api/v1/watchlist",
            headers=auth_headers,
            json={"marketId": "invalid-market-id"},
        )

        assert response.status_code == 422


class TestGetWatchlist:
    """Tests for GET /api/v1/watchlist."""

    @pytest.mark.asyncio
    async def test_get_watchlist_empty(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test getting empty watchlist."""
        response = await client.get("/api/v1/watchlist", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_get_watchlist_with_items(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        mock_clickhouse_client: MagicMock,
    ) -> None:
        """Test getting watchlist with items."""
        # Add a market first
        mock_clickhouse_client.query.return_value = make_mock_ch_response(
            columns=["1"], rows=[(1,)]
        )
        add_response = await client.post(
            "/api/v1/watchlist",
            headers=auth_headers,
            json={"marketId": TEST_MARKET_ID},
        )
        assert add_response.status_code == 201

        # Mock market details query for list
        mock_clickhouse_client.query.return_value = make_mock_ch_response(
            columns=["market_id", "question", "category", "status"],
            rows=[(TEST_MARKET_ID, "Will X happen?", "Politics", "open")],
        )

        # Get watchlist
        response = await client.get("/api/v1/watchlist", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["marketId"] == TEST_MARKET_ID

    @pytest.mark.asyncio
    async def test_get_watchlist_no_auth(self, client: AsyncClient) -> None:
        """Test getting watchlist without auth fails."""
        response = await client.get("/api/v1/watchlist")

        assert response.status_code == 401


class TestRemoveFromWatchlist:
    """Tests for DELETE /api/v1/watchlist/{market_id}."""

    @pytest.mark.asyncio
    async def test_remove_from_watchlist_success(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        mock_clickhouse_client: MagicMock,
    ) -> None:
        """Test removing a market from watchlist."""
        # Add market first
        mock_clickhouse_client.query.return_value = make_mock_ch_response(
            columns=["1"], rows=[(1,)]
        )
        add_response = await client.post(
            "/api/v1/watchlist",
            headers=auth_headers,
            json={"marketId": TEST_MARKET_ID},
        )
        assert add_response.status_code == 201

        # Remove market
        response = await client.delete(
            f"/api/v1/watchlist/{TEST_MARKET_ID}",
            headers=auth_headers,
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_remove_from_watchlist_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test removing non-existent watchlist item fails."""
        response = await client.delete(
            f"/api/v1/watchlist/{TEST_MARKET_ID}",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found in watchlist" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_remove_from_watchlist_no_auth(self, client: AsyncClient) -> None:
        """Test removing from watchlist without auth fails."""
        response = await client.delete(f"/api/v1/watchlist/{TEST_MARKET_ID}")

        assert response.status_code == 401


class TestWatchlistFlow:
    """Integration test for complete watchlist flow."""

    @pytest.mark.asyncio
    async def test_add_list_remove_flow(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        mock_clickhouse_client: MagicMock,
    ) -> None:
        """Test full flow: add -> list -> remove."""
        # Mock market existence
        mock_clickhouse_client.query.return_value = make_mock_ch_response(
            columns=["1"], rows=[(1,)]
        )

        # Step 1: Add market to watchlist
        add_response = await client.post(
            "/api/v1/watchlist",
            headers=auth_headers,
            json={"marketId": TEST_MARKET_ID},
        )
        assert add_response.status_code == 201

        # Step 2: List watchlist and verify market is present
        # Mock market details for list
        mock_clickhouse_client.query.return_value = make_mock_ch_response(
            columns=["market_id", "question", "category", "status"],
            rows=[(TEST_MARKET_ID, "Will X happen?", "Politics", "open")],
        )
        list_response = await client.get("/api/v1/watchlist", headers=auth_headers)
        assert list_response.status_code == 200
        assert list_response.json()["count"] == 1

        # Step 3: Remove market from watchlist
        remove_response = await client.delete(
            f"/api/v1/watchlist/{TEST_MARKET_ID}",
            headers=auth_headers,
        )
        assert remove_response.status_code == 204

        # Step 4: Verify watchlist is empty
        # Empty list doesn't need market details
        mock_clickhouse_client.query.return_value = make_mock_ch_response(
            columns=[], rows=[]
        )
        final_list_response = await client.get("/api/v1/watchlist", headers=auth_headers)
        assert final_list_response.status_code == 200
        assert final_list_response.json()["count"] == 0
