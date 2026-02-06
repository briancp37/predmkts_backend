"""Tests for authentication API endpoints.

Tests the full auth flow: register -> login -> access protected endpoint -> refresh tokens.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from tests.api.conftest import (
    TEST_USER_EMAIL,
    TEST_USER_PASSWORD,
    login_test_user,
    register_test_user,
)


class TestRegister:
    """Tests for POST /api/v1/auth/register."""

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient) -> None:
        """Test successful user registration."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "securepassword123",
                "name": "New User",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["name"] == "New User"
        assert data["tier"] == "FREE"
        assert "id" in data
        assert "password" not in data
        assert "password_hash" not in data

    @pytest.mark.asyncio
    async def test_register_without_name(self, client: AsyncClient) -> None:
        """Test registration without optional name field."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "noname@example.com",
                "password": "securepassword123",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "noname@example.com"
        assert data["name"] is None

    @pytest.mark.asyncio
    async def test_register_duplicate_email(
        self, client: AsyncClient, test_user: dict[str, Any]
    ) -> None:
        """Test registration with existing email fails."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": TEST_USER_EMAIL,
                "password": "securepassword123",
            },
        )

        assert response.status_code == 400
        assert "Email already registered" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client: AsyncClient) -> None:
        """Test registration with invalid email fails validation."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "not-an-email",
                "password": "securepassword123",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_weak_password(self, client: AsyncClient) -> None:
        """Test registration with password less than 8 chars fails."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "weak@example.com",
                "password": "short",
            },
        )

        assert response.status_code == 422
        # Check that validation error mentions password
        errors = response.json().get("errors", [])
        assert any("password" in e.get("field", "").lower() for e in errors)


class TestLogin:
    """Tests for POST /api/v1/auth/login."""

    @pytest.mark.asyncio
    async def test_login_success(
        self, client: AsyncClient, test_user: dict[str, Any]
    ) -> None:
        """Test successful login returns tokens."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password(
        self, client: AsyncClient, test_user: dict[str, Any]
    ) -> None:
        """Test login with wrong password fails."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": TEST_USER_EMAIL,
                "password": "wrongpassword",
            },
        )

        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient) -> None:
        """Test login with non-existent email fails."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "somepassword123",
            },
        )

        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]


class TestGetCurrentUser:
    """Tests for GET /api/v1/auth/me."""

    @pytest.mark.asyncio
    async def test_get_me_authenticated(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Test getting current user with valid token."""
        response = await client.get("/api/v1/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == TEST_USER_EMAIL
        assert data["tier"] == "FREE"

    @pytest.mark.asyncio
    async def test_get_me_no_token(self, client: AsyncClient) -> None:
        """Test getting current user without token fails."""
        response = await client.get("/api/v1/auth/me")

        assert response.status_code == 401  # No token provided

    @pytest.mark.asyncio
    async def test_get_me_invalid_token(self, client: AsyncClient) -> None:
        """Test getting current user with invalid token fails."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid-token"},
        )

        assert response.status_code == 401


class TestRefreshToken:
    """Tests for POST /api/v1/auth/refresh."""

    @pytest.mark.asyncio
    async def test_refresh_token_success(
        self, client: AsyncClient, auth_headers_with_refresh: dict[str, str]
    ) -> None:
        """Test refreshing tokens with valid refresh token."""
        refresh_token = auth_headers_with_refresh["_refresh_token"]
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_refresh_token_invalid(self, client: AsyncClient) -> None:
        """Test refresh with invalid token fails."""
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid-refresh-token"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_with_access_token_fails(
        self, client: AsyncClient, auth_headers_with_refresh: dict[str, str]
    ) -> None:
        """Test that using an access token as refresh token fails."""
        # Extract the access token from headers
        access_token = auth_headers_with_refresh["Authorization"].replace("Bearer ", "")

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": access_token},
        )

        assert response.status_code == 401
        assert "Invalid token type" in response.json()["detail"]


class TestUpdateUser:
    """Tests for PATCH /api/v1/auth/me."""

    @pytest.mark.asyncio
    async def test_update_name(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Test updating user's name."""
        response = await client.patch(
            "/api/v1/auth/me",
            headers=auth_headers,
            json={"name": "Updated Name"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_no_auth(self, client: AsyncClient) -> None:
        """Test update without authentication fails."""
        response = await client.patch(
            "/api/v1/auth/me",
            json={"name": "New Name"},
        )

        assert response.status_code == 401


class TestFullAuthFlow:
    """Integration test for complete auth flow."""

    @pytest.mark.asyncio
    async def test_register_login_access_protected_endpoint(
        self, client: AsyncClient
    ) -> None:
        """Test full flow: register -> login -> access protected endpoint."""
        # Step 1: Register
        register_response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "flowtest@example.com",
                "password": "securepassword123",
                "name": "Flow Test User",
            },
        )
        assert register_response.status_code == 201
        user_data = register_response.json()
        assert user_data["email"] == "flowtest@example.com"

        # Step 2: Login
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "flowtest@example.com",
                "password": "securepassword123",
            },
        )
        assert login_response.status_code == 200
        tokens = login_response.json()
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]

        # Step 3: Access protected endpoint with access token
        me_response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_response.status_code == 200
        assert me_response.json()["email"] == "flowtest@example.com"

        # Step 4: Refresh tokens
        refresh_response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_response.status_code == 200
        new_tokens = refresh_response.json()
        new_access_token = new_tokens["access_token"]

        # Step 5: Access with new token
        new_me_response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_access_token}"},
        )
        assert new_me_response.status_code == 200
        assert new_me_response.json()["email"] == "flowtest@example.com"
