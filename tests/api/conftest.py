"""Pytest fixtures for API integration tests.

Uses httpx AsyncClient with async database setup for clean test isolation.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from prediction_data.api.clickhouse import get_clickhouse_client
from prediction_data.api.main import app
from prediction_data.api.rate_limit import limiter
from prediction_data.db.base import Base
from prediction_data.db.session import get_db


# Set environment variables BEFORE importing modules that use get_settings
os.environ.setdefault("BRONZE_BUCKET", "test-bucket")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing-only-32chars")
os.environ.setdefault("DEBUG", "true")

# Test database URL - use SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def test_engine() -> Any:
    """Create a test database engine using SQLite."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session_factory(
    test_engine: Any,
) -> async_sessionmaker[AsyncSession]:
    """Create test session factory."""
    factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return factory


@pytest.fixture
def mock_clickhouse_client() -> MagicMock:
    """Create a mock ClickHouse client."""
    client = MagicMock()
    # Default response for queries
    client.query.return_value.column_names = []
    client.query.return_value.result_rows = []
    return client


@pytest_asyncio.fixture(scope="function")
async def client(
    test_session_factory: async_sessionmaker[AsyncSession],
    mock_clickhouse_client: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client with database and ClickHouse overrides."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    def override_get_clickhouse() -> MagicMock:
        return mock_clickhouse_client

    # Override dependencies
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_clickhouse_client] = override_get_clickhouse

    # Disable rate limiting for tests
    limiter.enabled = False

    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as ac:
        yield ac

    # Cleanup
    app.dependency_overrides.clear()
    limiter.enabled = True  # Re-enable for next test


def make_mock_ch_response(columns: list[str], rows: list[tuple[Any, ...]]) -> MagicMock:
    """Helper to create a mock ClickHouse query response."""
    mock_result = MagicMock()
    mock_result.column_names = columns
    mock_result.result_rows = rows
    mock_result.first_row = rows[0] if rows else None
    return mock_result


# Test credentials
TEST_USER_EMAIL = "test@example.com"
TEST_USER_PASSWORD = "testpassword123"
TEST_PRO_USER_EMAIL = "pro@example.com"


async def register_test_user(
    client: AsyncClient,
    email: str = TEST_USER_EMAIL,
    password: str = TEST_USER_PASSWORD,
    name: str | None = "Test User",
) -> dict[str, Any]:
    """Helper to register a test user via the API."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": name},
    )
    assert response.status_code == 201, f"Failed to register: {response.json()}"
    return response.json()


async def login_test_user(
    client: AsyncClient,
    email: str = TEST_USER_EMAIL,
    password: str = TEST_USER_PASSWORD,
) -> dict[str, str]:
    """Helper to login and get auth headers."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, f"Failed to login: {response.json()}"
    tokens = response.json()
    return {
        "Authorization": f"Bearer {tokens['access_token']}",
        "_refresh_token": tokens["refresh_token"],
    }


@pytest_asyncio.fixture(scope="function")
async def test_user(client: AsyncClient) -> dict[str, Any]:
    """Create and register a test user, returning user data."""
    return await register_test_user(client)


@pytest_asyncio.fixture(scope="function")
async def auth_headers(client: AsyncClient, test_user: dict[str, Any]) -> dict[str, str]:
    """Get auth headers for the test user."""
    headers = await login_test_user(client)
    return {"Authorization": headers["Authorization"]}


@pytest_asyncio.fixture(scope="function")
async def auth_headers_with_refresh(
    client: AsyncClient, test_user: dict[str, Any]
) -> dict[str, str]:
    """Get auth headers including refresh token."""
    return await login_test_user(client)


@pytest_asyncio.fixture(scope="function")
async def test_user_pro(client: AsyncClient) -> dict[str, Any]:
    """Create a PRO tier user (just a regular user - tier upgrade needs DB access)."""
    return await register_test_user(
        client,
        email=TEST_PRO_USER_EMAIL,
        password=TEST_USER_PASSWORD,
        name="Pro User",
    )


@pytest_asyncio.fixture(scope="function")
async def auth_headers_pro(
    client: AsyncClient, test_user_pro: dict[str, Any]
) -> dict[str, str]:
    """Get auth headers for the PRO user."""
    headers = await login_test_user(client, email=TEST_PRO_USER_EMAIL)
    return {"Authorization": headers["Authorization"]}


# Valid test market ID (0x + 64 hex chars)
TEST_MARKET_ID = "0x" + "a" * 64

# Valid test trader address (0x + 40 hex chars)
TEST_TRADER_ADDRESS = "0x" + "b" * 40
