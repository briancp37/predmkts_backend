"""Tests for tag templates API endpoints.

Tests the tag template CRUD flow: create -> list -> get -> update -> delete.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


class TestCreateTagTemplate:
    """Tests for POST /api/v1/tag-templates."""

    @pytest.mark.asyncio
    async def test_create_tag_template_success(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test creating a tag template."""
        response = await client.post(
            "/api/v1/tag-templates",
            headers=auth_headers,
            json={
                "name": "Sports Only",
                "includeTags": ["Sports", "Basketball"],
                "excludeTags": ["Politics"],
                "isDefault": False,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Sports Only"
        assert data["includeTags"] == ["Sports", "Basketball"]
        assert data["excludeTags"] == ["Politics"]
        assert data["isDefault"] is False
        assert "id" in data
        assert "createdAt" in data
        assert "updatedAt" in data

    @pytest.mark.asyncio
    async def test_create_tag_template_minimal(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test creating a template with only name (tags default to empty)."""
        response = await client.post(
            "/api/v1/tag-templates",
            headers=auth_headers,
            json={"name": "Empty Template"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Empty Template"
        assert data["includeTags"] == []
        assert data["excludeTags"] == []
        assert data["isDefault"] is False

    @pytest.mark.asyncio
    async def test_create_tag_template_no_auth(self, client: AsyncClient) -> None:
        """Test creating template without authentication fails."""
        response = await client.post(
            "/api/v1/tag-templates",
            json={"name": "Test Template"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_tag_template_duplicate_name(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test creating template with duplicate name fails."""
        # Create first template
        response1 = await client.post(
            "/api/v1/tag-templates",
            headers=auth_headers,
            json={"name": "My Template"},
        )
        assert response1.status_code == 201

        # Try to create with same name
        response2 = await client.post(
            "/api/v1/tag-templates",
            headers=auth_headers,
            json={"name": "My Template"},
        )
        assert response2.status_code == 400
        assert "already exists" in response2.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_tag_template_default_unsets_previous(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test setting new default unsets previous default."""
        # Create first template as default
        response1 = await client.post(
            "/api/v1/tag-templates",
            headers=auth_headers,
            json={"name": "Template 1", "isDefault": True},
        )
        assert response1.status_code == 201
        template1_id = response1.json()["id"]

        # Create second template as default
        response2 = await client.post(
            "/api/v1/tag-templates",
            headers=auth_headers,
            json={"name": "Template 2", "isDefault": True},
        )
        assert response2.status_code == 201
        assert response2.json()["isDefault"] is True

        # Check first template is no longer default
        get_response = await client.get(
            f"/api/v1/tag-templates/{template1_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 200
        assert get_response.json()["isDefault"] is False

    @pytest.mark.asyncio
    async def test_create_tag_template_empty_name_fails(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test creating template with empty name fails validation."""
        response = await client.post(
            "/api/v1/tag-templates",
            headers=auth_headers,
            json={"name": ""},
        )

        assert response.status_code == 422


class TestListTagTemplates:
    """Tests for GET /api/v1/tag-templates."""

    @pytest.mark.asyncio
    async def test_list_tag_templates_empty(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test listing empty templates."""
        response = await client.get("/api/v1/tag-templates", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_list_tag_templates_with_items(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test listing templates with items."""
        # Create templates
        await client.post(
            "/api/v1/tag-templates",
            headers=auth_headers,
            json={"name": "Template 1"},
        )
        await client.post(
            "/api/v1/tag-templates",
            headers=auth_headers,
            json={"name": "Template 2"},
        )

        response = await client.get("/api/v1/tag-templates", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_tag_templates_no_auth(self, client: AsyncClient) -> None:
        """Test listing templates without auth fails."""
        response = await client.get("/api/v1/tag-templates")

        assert response.status_code == 401


class TestGetTagTemplate:
    """Tests for GET /api/v1/tag-templates/{id}."""

    @pytest.mark.asyncio
    async def test_get_tag_template_success(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test getting a specific template."""
        # Create template
        create_response = await client.post(
            "/api/v1/tag-templates",
            headers=auth_headers,
            json={"name": "My Template", "includeTags": ["Sports"]},
        )
        template_id = create_response.json()["id"]

        # Get template
        response = await client.get(
            f"/api/v1/tag-templates/{template_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == template_id
        assert data["name"] == "My Template"
        assert data["includeTags"] == ["Sports"]

    @pytest.mark.asyncio
    async def test_get_tag_template_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test getting non-existent template fails."""
        random_uuid = str(uuid.uuid4())
        response = await client.get(
            f"/api/v1/tag-templates/{random_uuid}",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_tag_template_no_auth(self, client: AsyncClient) -> None:
        """Test getting template without auth fails."""
        random_uuid = str(uuid.uuid4())
        response = await client.get(f"/api/v1/tag-templates/{random_uuid}")

        assert response.status_code == 401


class TestUpdateTagTemplate:
    """Tests for PUT /api/v1/tag-templates/{id}."""

    @pytest.mark.asyncio
    async def test_update_tag_template_success(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test updating a template."""
        # Create template
        create_response = await client.post(
            "/api/v1/tag-templates",
            headers=auth_headers,
            json={"name": "Original Name", "includeTags": ["Sports"]},
        )
        template_id = create_response.json()["id"]

        # Update template
        response = await client.put(
            f"/api/v1/tag-templates/{template_id}",
            headers=auth_headers,
            json={
                "name": "Updated Name",
                "includeTags": ["Politics", "Crypto"],
                "excludeTags": ["Sports"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["includeTags"] == ["Politics", "Crypto"]
        assert data["excludeTags"] == ["Sports"]

    @pytest.mark.asyncio
    async def test_update_tag_template_partial(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test partial update (only update name)."""
        # Create template
        create_response = await client.post(
            "/api/v1/tag-templates",
            headers=auth_headers,
            json={"name": "Original", "includeTags": ["Sports"]},
        )
        template_id = create_response.json()["id"]

        # Update only name
        response = await client.put(
            f"/api/v1/tag-templates/{template_id}",
            headers=auth_headers,
            json={"name": "Updated"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated"
        assert data["includeTags"] == ["Sports"]  # Unchanged

    @pytest.mark.asyncio
    async def test_update_tag_template_set_default(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test setting template as default via update."""
        # Create two templates
        response1 = await client.post(
            "/api/v1/tag-templates",
            headers=auth_headers,
            json={"name": "Template 1", "isDefault": True},
        )
        template1_id = response1.json()["id"]

        response2 = await client.post(
            "/api/v1/tag-templates",
            headers=auth_headers,
            json={"name": "Template 2"},
        )
        template2_id = response2.json()["id"]

        # Set template 2 as default via update
        await client.put(
            f"/api/v1/tag-templates/{template2_id}",
            headers=auth_headers,
            json={"isDefault": True},
        )

        # Check template 1 is no longer default
        get_response = await client.get(
            f"/api/v1/tag-templates/{template1_id}",
            headers=auth_headers,
        )
        assert get_response.json()["isDefault"] is False

        # Check template 2 is now default
        get_response2 = await client.get(
            f"/api/v1/tag-templates/{template2_id}",
            headers=auth_headers,
        )
        assert get_response2.json()["isDefault"] is True

    @pytest.mark.asyncio
    async def test_update_tag_template_duplicate_name(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test updating to duplicate name fails."""
        # Create two templates
        await client.post(
            "/api/v1/tag-templates",
            headers=auth_headers,
            json={"name": "Template 1"},
        )
        response2 = await client.post(
            "/api/v1/tag-templates",
            headers=auth_headers,
            json={"name": "Template 2"},
        )
        template2_id = response2.json()["id"]

        # Try to update template 2 with template 1's name
        response = await client.put(
            f"/api/v1/tag-templates/{template2_id}",
            headers=auth_headers,
            json={"name": "Template 1"},
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_tag_template_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test updating non-existent template fails."""
        random_uuid = str(uuid.uuid4())
        response = await client.put(
            f"/api/v1/tag-templates/{random_uuid}",
            headers=auth_headers,
            json={"name": "New Name"},
        )

        assert response.status_code == 404


class TestDeleteTagTemplate:
    """Tests for DELETE /api/v1/tag-templates/{id}."""

    @pytest.mark.asyncio
    async def test_delete_tag_template_success(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test deleting a template."""
        # Create template
        create_response = await client.post(
            "/api/v1/tag-templates",
            headers=auth_headers,
            json={"name": "To Delete"},
        )
        template_id = create_response.json()["id"]

        # Delete template
        response = await client.delete(
            f"/api/v1/tag-templates/{template_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify it's gone
        get_response = await client.get(
            f"/api/v1/tag-templates/{template_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_tag_template_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test deleting non-existent template fails."""
        random_uuid = str(uuid.uuid4())
        response = await client.delete(
            f"/api/v1/tag-templates/{random_uuid}",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_tag_template_no_auth(self, client: AsyncClient) -> None:
        """Test deleting template without auth fails."""
        random_uuid = str(uuid.uuid4())
        response = await client.delete(f"/api/v1/tag-templates/{random_uuid}")

        assert response.status_code == 401


class TestTagTemplateFlow:
    """Integration test for complete tag template flow."""

    @pytest.mark.asyncio
    async def test_create_list_update_delete_flow(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test full flow: create -> list -> update -> delete."""
        # Step 1: Create template
        create_response = await client.post(
            "/api/v1/tag-templates",
            headers=auth_headers,
            json={
                "name": "My Filter",
                "includeTags": ["Sports"],
                "excludeTags": ["Politics"],
            },
        )
        assert create_response.status_code == 201
        template_id = create_response.json()["id"]

        # Step 2: List templates and verify
        list_response = await client.get("/api/v1/tag-templates", headers=auth_headers)
        assert list_response.status_code == 200
        assert list_response.json()["count"] == 1

        # Step 3: Update template
        update_response = await client.put(
            f"/api/v1/tag-templates/{template_id}",
            headers=auth_headers,
            json={"name": "Updated Filter", "isDefault": True},
        )
        assert update_response.status_code == 200
        assert update_response.json()["name"] == "Updated Filter"
        assert update_response.json()["isDefault"] is True

        # Step 4: Delete template
        delete_response = await client.delete(
            f"/api/v1/tag-templates/{template_id}",
            headers=auth_headers,
        )
        assert delete_response.status_code == 204

        # Step 5: Verify list is empty
        final_list_response = await client.get(
            "/api/v1/tag-templates", headers=auth_headers
        )
        assert final_list_response.status_code == 200
        assert final_list_response.json()["count"] == 0
