"""Pytest configuration and fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest


@pytest.fixture
def sample_fixture() -> str:
    """Sample fixture for testing."""
    return "test"


# ---------------------------------------------------------------------------
# Quality-violation fixtures: common bad-data patterns for Silver checks
# ---------------------------------------------------------------------------


@pytest.fixture
def null_violation_records() -> list[dict]:
    """Records with null values in critical columns."""
    return [
        {"event_ts": datetime(2025, 6, 15, tzinfo=UTC), "platform_trade_id": "t1", "platform_market_id": "m1"},
        {"event_ts": None, "platform_trade_id": "t2", "platform_market_id": "m2"},
        {"event_ts": datetime(2025, 6, 15, tzinfo=UTC), "platform_trade_id": None, "platform_market_id": "m3"},
        {"event_ts": datetime(2025, 6, 15, tzinfo=UTC), "platform_trade_id": "t4"},  # missing key
    ]


@pytest.fixture
def duplicate_violation_records() -> list[dict]:
    """Records with duplicate dedup keys."""
    return [
        {"platform_trade_id": "t1", "event_ts": datetime(2025, 6, 15, tzinfo=UTC)},
        {"platform_trade_id": "t2", "event_ts": datetime(2025, 6, 15, tzinfo=UTC)},
        {"platform_trade_id": "t1", "event_ts": datetime(2025, 6, 15, tzinfo=UTC)},  # dup
        {"platform_trade_id": "t3", "event_ts": datetime(2025, 6, 15, tzinfo=UTC)},
        {"platform_trade_id": "t2", "event_ts": datetime(2025, 6, 15, tzinfo=UTC)},  # dup
    ]


@pytest.fixture
def bad_timestamp_records() -> list[dict]:
    """Records with out-of-range and future timestamps."""
    now = datetime.now(UTC)
    expected = datetime(2025, 6, 15, tzinfo=UTC)
    return [
        {"event_ts": datetime(2025, 6, 15, 12, 0, tzinfo=UTC)},  # ok
        {"event_ts": datetime(2024, 1, 1, tzinfo=UTC)},  # way out of range
        {"event_ts": now + timedelta(hours=5)},  # future
        {"event_ts": datetime(2025, 6, 17, tzinfo=UTC)},  # just outside tolerance
    ]
