"""Tests for tracked traders API endpoints.

Tests the tracked traders flow with tier limit enforcement.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient

from tests.api.conftest import TEST_TRADER_ADDRESS, make_mock_ch_response


# Additional test addresses
def make_trader_address(index: int) -> str:
    """Generate unique test trader addresses."""
    hex_char = hex(index % 16)[2:]
    return "0x" + hex_char * 40


class TestAddTrackedTrader:
    """Tests for POST /api/v1/tracked-traders."""

    @pytest.mark.asyncio
    async def test_add_tracked_trader_success(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test adding a trader to tracked list."""
        response = await client.post(
            "/api/v1/tracked-traders",
            headers=auth_headers,
            json={"traderAddress": TEST_TRADER_ADDRESS},
        )

        assert response.status_code == 201
        data = response.json()
        # Address is normalized to lowercase
        assert data["traderAddress"] == TEST_TRADER_ADDRESS.lower()
        assert "id" in data
        assert "createdAt" in data

    @pytest.mark.asyncio
    async def test_add_tracked_trader_with_custom_name(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test adding a trader with custom name."""
        response = await client.post(
            "/api/v1/tracked-traders",
            headers=auth_headers,
            json={
                "traderAddress": TEST_TRADER_ADDRESS,
                "customName": "My Whale",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["customName"] == "My Whale"

    @pytest.mark.asyncio
    async def test_add_tracked_trader_no_auth(self, client: AsyncClient) -> None:
        """Test adding tracked trader without auth fails."""
        response = await client.post(
            "/api/v1/tracked-traders",
            json={"traderAddress": TEST_TRADER_ADDRESS},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_add_tracked_trader_duplicate(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test adding duplicate trader fails."""
        # Add trader first time
        response1 = await client.post(
            "/api/v1/tracked-traders",
            headers=auth_headers,
            json={"traderAddress": TEST_TRADER_ADDRESS},
        )
        assert response1.status_code == 201

        # Try to add same trader again
        response2 = await client.post(
            "/api/v1/tracked-traders",
            headers=auth_headers,
            json={"traderAddress": TEST_TRADER_ADDRESS},
        )
        assert response2.status_code == 400
        assert "already in tracked list" in response2.json()["detail"]

    @pytest.mark.asyncio
    async def test_add_tracked_trader_invalid_address(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test adding trader with invalid address fails."""
        response = await client.post(
            "/api/v1/tracked-traders",
            headers=auth_headers,
            json={"traderAddress": "not-a-valid-address"},
        )

        assert response.status_code == 422


class TestTrackedTraderTierLimits:
    """Tests for tier-based limits on tracked traders."""

    @pytest.mark.asyncio
    async def test_free_tier_limit(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test FREE tier limit of 6 tracked traders."""
        # Add 6 traders (the limit for FREE tier)
        for i in range(6):
            response = await client.post(
                "/api/v1/tracked-traders",
                headers=auth_headers,
                json={"traderAddress": make_trader_address(i)},
            )
            assert response.status_code == 201, f"Failed to add trader {i}: {response.json()}"

        # Try to add 7th trader - should fail
        response = await client.post(
            "/api/v1/tracked-traders",
            headers=auth_headers,
            json={"traderAddress": make_trader_address(6)},
        )

        assert response.status_code == 403  # Tier limit exceeded
        data = response.json()
        assert "limit reached" in data["detail"].lower()
        assert data.get("limit") == 6
        assert data.get("count") == 6


class TestGetTrackedTraders:
    """Tests for GET /api/v1/tracked-traders."""

    @pytest.mark.asyncio
    async def test_get_tracked_traders_empty(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test getting empty tracked traders list."""
        response = await client.get("/api/v1/tracked-traders", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["count"] == 0
        assert "limit" in data  # Should include tier limit

    @pytest.mark.asyncio
    async def test_get_tracked_traders_with_items(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        mock_clickhouse_client: MagicMock,
    ) -> None:
        """Test getting tracked traders with stats."""
        # Add a trader
        add_response = await client.post(
            "/api/v1/tracked-traders",
            headers=auth_headers,
            json={"traderAddress": TEST_TRADER_ADDRESS, "customName": "Test Whale"},
        )
        assert add_response.status_code == 201

        # Mock ClickHouse stats queries
        mock_clickhouse_client.query.return_value = make_mock_ch_response(
            columns=["wallet_address", "total_pnl"],
            rows=[(TEST_TRADER_ADDRESS.lower(), 1234.56)],
        )

        # Get tracked traders
        response = await client.get("/api/v1/tracked-traders", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["traderAddress"] == TEST_TRADER_ADDRESS.lower()
        assert data["items"][0]["customName"] == "Test Whale"

    @pytest.mark.asyncio
    async def test_get_tracked_traders_no_auth(self, client: AsyncClient) -> None:
        """Test getting tracked traders without auth fails."""
        response = await client.get("/api/v1/tracked-traders")

        assert response.status_code == 401


class TestRemoveTrackedTrader:
    """Tests for DELETE /api/v1/tracked-traders/{tracker_id}."""

    @pytest.mark.asyncio
    async def test_remove_tracked_trader_success(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test removing a tracked trader."""
        # Add trader first
        add_response = await client.post(
            "/api/v1/tracked-traders",
            headers=auth_headers,
            json={"traderAddress": TEST_TRADER_ADDRESS},
        )
        assert add_response.status_code == 201
        tracker_id = add_response.json()["id"]

        # Remove trader
        response = await client.delete(
            f"/api/v1/tracked-traders/{tracker_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_remove_tracked_trader_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test removing non-existent tracker fails."""
        fake_id = str(uuid.uuid4())
        response = await client.delete(
            f"/api/v1/tracked-traders/{fake_id}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_remove_tracked_trader_no_auth(self, client: AsyncClient) -> None:
        """Test removing tracked trader without auth fails."""
        response = await client.delete(f"/api/v1/tracked-traders/{uuid.uuid4()}")

        assert response.status_code == 401


class TestUpdateTrackedTrader:
    """Tests for PATCH /api/v1/tracked-traders/{tracker_id}."""

    @pytest.mark.asyncio
    async def test_update_custom_name(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test updating tracked trader's custom name."""
        # Add trader first
        add_response = await client.post(
            "/api/v1/tracked-traders",
            headers=auth_headers,
            json={"traderAddress": TEST_TRADER_ADDRESS},
        )
        assert add_response.status_code == 201
        tracker_id = add_response.json()["id"]

        # Update custom name
        response = await client.patch(
            f"/api/v1/tracked-traders/{tracker_id}",
            headers=auth_headers,
            json={"customName": "Updated Name"},
        )

        assert response.status_code == 200
        assert response.json()["customName"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_clear_custom_name(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test clearing tracked trader's custom name."""
        # Add trader with custom name
        add_response = await client.post(
            "/api/v1/tracked-traders",
            headers=auth_headers,
            json={"traderAddress": TEST_TRADER_ADDRESS, "customName": "My Whale"},
        )
        assert add_response.status_code == 201
        tracker_id = add_response.json()["id"]

        # Clear custom name
        response = await client.patch(
            f"/api/v1/tracked-traders/{tracker_id}",
            headers=auth_headers,
            json={"customName": None},
        )

        assert response.status_code == 200
        assert response.json()["customName"] is None


class TestTrackedTraderActivity:
    """Tests for GET /api/v1/tracked-traders/activity."""

    @pytest.mark.asyncio
    async def test_get_activity_empty(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test getting activity with no tracked traders."""
        response = await client.get("/api/v1/tracked-traders/activity", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_activity_with_traders(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        mock_clickhouse_client: MagicMock,
    ) -> None:
        """Test getting activity feed with tracked traders."""
        # Add a trader
        add_response = await client.post(
            "/api/v1/tracked-traders",
            headers=auth_headers,
            json={"traderAddress": TEST_TRADER_ADDRESS},
        )
        assert add_response.status_code == 201

        # Mock activity query - return empty for simplicity
        mock_clickhouse_client.query.return_value = make_mock_ch_response(
            columns=[], rows=[]
        )

        # Get activity
        response = await client.get("/api/v1/tracked-traders/activity", headers=auth_headers)

        assert response.status_code == 200
        # Activity may be empty depending on mock
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_get_activity_no_auth(self, client: AsyncClient) -> None:
        """Test getting activity without auth fails."""
        response = await client.get("/api/v1/tracked-traders/activity")

        assert response.status_code == 401


class TestTrackedTradersFlow:
    """Integration test for complete tracked traders flow."""

    @pytest.mark.asyncio
    async def test_add_list_update_remove_flow(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        mock_clickhouse_client: MagicMock,
    ) -> None:
        """Test full flow: add -> list -> update -> remove."""
        # Mock ClickHouse for stats
        mock_clickhouse_client.query.return_value = make_mock_ch_response(
            columns=["wallet_address", "total_pnl"],
            rows=[],
        )

        # Step 1: Add tracked trader
        add_response = await client.post(
            "/api/v1/tracked-traders",
            headers=auth_headers,
            json={"traderAddress": TEST_TRADER_ADDRESS, "customName": "Original Name"},
        )
        assert add_response.status_code == 201
        tracker_id = add_response.json()["id"]

        # Step 2: List tracked traders
        list_response = await client.get("/api/v1/tracked-traders", headers=auth_headers)
        assert list_response.status_code == 200
        assert list_response.json()["count"] == 1

        # Step 3: Update custom name
        update_response = await client.patch(
            f"/api/v1/tracked-traders/{tracker_id}",
            headers=auth_headers,
            json={"customName": "Updated Name"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["customName"] == "Updated Name"

        # Step 4: Remove tracked trader
        remove_response = await client.delete(
            f"/api/v1/tracked-traders/{tracker_id}",
            headers=auth_headers,
        )
        assert remove_response.status_code == 204

        # Step 5: Verify list is empty
        final_list_response = await client.get("/api/v1/tracked-traders", headers=auth_headers)
        assert final_list_response.status_code == 200
        assert final_list_response.json()["count"] == 0

    @pytest.mark.asyncio
    async def test_tier_limit_then_remove_then_add_again(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that removing a trader allows adding another when at limit."""
        # Add 6 traders (FREE tier limit)
        tracker_ids: list[str] = []
        for i in range(6):
            response = await client.post(
                "/api/v1/tracked-traders",
                headers=auth_headers,
                json={"traderAddress": make_trader_address(i)},
            )
            assert response.status_code == 201
            tracker_ids.append(response.json()["id"])

        # Verify can't add 7th
        response = await client.post(
            "/api/v1/tracked-traders",
            headers=auth_headers,
            json={"traderAddress": make_trader_address(6)},
        )
        assert response.status_code == 403  # Tier limit exceeded

        # Remove one
        remove_response = await client.delete(
            f"/api/v1/tracked-traders/{tracker_ids[0]}",
            headers=auth_headers,
        )
        assert remove_response.status_code == 204

        # Now can add another
        response = await client.post(
            "/api/v1/tracked-traders",
            headers=auth_headers,
            json={"traderAddress": make_trader_address(6)},
        )
        assert response.status_code == 201
