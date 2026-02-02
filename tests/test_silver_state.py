"""Tests for Silver processing state management."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from prediction_data.silver.state import SilverStateStore, _state_key


class FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


def _make_s3_client(
    existing_data: str | None = None,
) -> MagicMock:
    """Build a mock S3Client with an in-memory store."""
    store: dict[str, bytes] = {}
    if existing_data is not None:
        store[_state_key("polymarket", "trades")] = existing_data.encode()

    mock = MagicMock()
    mock.bucket = "test-bucket"

    boto_client = MagicMock()

    def get_object(Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in store:
            exc_cls = type("NoSuchKey", (Exception,), {})
            raise exc_cls(f"Key not found: {Key}")
        return {"Body": FakeBody(store[Key])}

    def put_object(Bucket: str, Key: str, Body: bytes, **kwargs: Any) -> None:
        store[Key] = Body

    boto_client.get_object = get_object
    boto_client.put_object = put_object
    boto_client.exceptions = MagicMock()
    boto_client.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})

    mock._get_client.return_value = boto_client
    mock._store = store  # expose for assertions

    return mock


@pytest.mark.asyncio
async def test_load_empty_state() -> None:
    s3 = _make_s3_client()
    store = SilverStateStore(s3, "polymarket", "trades")
    await store.load()
    assert not store.is_processed("some-run-id")


@pytest.mark.asyncio
async def test_load_existing_state() -> None:
    existing = (
        '{"run_id":"run-1","platform":"polymarket","entity":"trades","dt":"2024-01-01","processed_at":"2024-01-02T00:00:00"}\n'
        '{"run_id":"run-2","platform":"polymarket","entity":"trades","dt":"2024-01-02","processed_at":"2024-01-03T00:00:00"}\n'
    )
    s3 = _make_s3_client(existing_data=existing)
    store = SilverStateStore(s3, "polymarket", "trades")
    await store.load()
    assert store.is_processed("run-1")
    assert store.is_processed("run-2")
    assert not store.is_processed("run-3")


@pytest.mark.asyncio
async def test_mark_processed_appends() -> None:
    s3 = _make_s3_client()
    store = SilverStateStore(s3, "polymarket", "trades")
    await store.load()

    await store.mark_processed("run-1", "polymarket", "trades", "2024-01-01")
    assert store.is_processed("run-1")

    # Verify persisted to S3
    key = _state_key("polymarket", "trades")
    data = s3._store[key].decode()
    lines = [l for l in data.strip().splitlines() if l.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["run_id"] == "run-1"
    assert entry["dt"] == "2024-01-01"


@pytest.mark.asyncio
async def test_mark_processed_appends_to_existing() -> None:
    existing = '{"run_id":"run-1","platform":"polymarket","entity":"trades","dt":"2024-01-01","processed_at":"2024-01-02T00:00:00"}\n'
    s3 = _make_s3_client(existing_data=existing)
    store = SilverStateStore(s3, "polymarket", "trades")
    await store.load()

    await store.mark_processed("run-2", "polymarket", "trades", "2024-01-02")

    key = _state_key("polymarket", "trades")
    data = s3._store[key].decode()
    lines = [l for l in data.strip().splitlines() if l.strip()]
    assert len(lines) == 2


@pytest.mark.asyncio
async def test_is_processed_raises_if_not_loaded() -> None:
    s3 = _make_s3_client()
    store = SilverStateStore(s3, "polymarket", "trades")
    with pytest.raises(RuntimeError, match="not loaded"):
        store.is_processed("run-1")


def test_state_key() -> None:
    assert _state_key("polymarket", "trades") == "silver/_state/polymarket/trades/processed.jsonl"
