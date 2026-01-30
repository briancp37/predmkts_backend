"""Tests for S3 data discovery utilities."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from prediction_data.storage.discovery import find_latest_date, find_latest_timestamp
from prediction_data.storage.manifest import FileReference, Manifest, Source


def _make_manifest(
    *,
    platform: str = "polymarket",
    entity: str = "order_filled",
    dt: str = "2024-06-15",
    run_id: str = "run-1",
    row_count: int = 100,
    generated_at: datetime | None = None,
    bucket: str = "test-bucket",
    data_key: str = "bronze/polymarket/order_filled/dt=2024-06-15/run_id=run-1/part-000.jsonl.gz",
) -> Manifest:
    """Create a test manifest."""
    source_data: dict = {
        "api_base_url": "https://api.goldsky.com/test",
        "pagination": "cursor",
        "cursor": None,
    }
    # We can't easily add extra fields to frozen Source model,
    # so latest_timestamp support is tested via model_dump patching
    return Manifest(
        run_id=run_id,
        platform=platform,
        entity=entity,
        dt=dt,
        generated_at=generated_at or datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
        files=[FileReference(bucket=bucket, key=data_key)],
        row_count=row_count,
        source=Source(**source_data),
    )


def _mock_s3_client(
    keys: list[str],
    manifests: dict[str, Manifest] | None = None,
    jsonl_data: dict[str, list[dict]] | None = None,
) -> AsyncMock:
    """Create a mock S3Client."""
    client = AsyncMock()
    client.list_keys = AsyncMock(return_value=keys)

    if manifests:
        async def _download_manifest(key: str) -> Manifest:
            return manifests[key]
        client.download_manifest = AsyncMock(side_effect=_download_manifest)

    if jsonl_data:
        async def _download_jsonl(key: str) -> list[dict]:
            return jsonl_data.get(key, [])
        client.download_jsonl = AsyncMock(side_effect=_download_jsonl)

    return client


class TestFindLatestTimestamp:
    """Tests for find_latest_timestamp()."""

    @pytest.mark.asyncio
    async def test_no_data_returns_none(self) -> None:
        """Returns None when no keys exist."""
        client = _mock_s3_client(keys=[])
        result = await find_latest_timestamp(client, "polymarket", "order_filled")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_date_partitions_returns_none(self) -> None:
        """Returns None when keys exist but no dt= partitions found."""
        client = _mock_s3_client(keys=["bronze/polymarket/order_filled/somefile.txt"])
        result = await find_latest_timestamp(client, "polymarket", "order_filled")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_manifests_returns_none(self) -> None:
        """Returns None when date partitions exist but no manifests."""
        keys = ["bronze/polymarket/order_filled/dt=2024-06-15/run_id=abc/part-000.jsonl.gz"]
        client = _mock_s3_client(keys=keys)
        result = await find_latest_timestamp(client, "polymarket", "order_filled")
        assert result is None

    @pytest.mark.asyncio
    async def test_fallback_data_scan(self) -> None:
        """Falls back to scanning data files when manifest has no latest_timestamp."""
        manifest_key = "bronze/polymarket/order_filled/dt=2024-06-15/run_id=run-1/manifest.json"
        data_key = "bronze/polymarket/order_filled/dt=2024-06-15/run_id=run-1/part-000.jsonl.gz"
        manifest = _make_manifest()
        keys = [manifest_key, data_key]
        jsonl_data = {
            data_key: [
                {"timestamp": 1718400000, "id": "1"},
                {"timestamp": 1718450000, "id": "2"},
                {"timestamp": 1718430000, "id": "3"},
            ]
        }
        client = _mock_s3_client(keys=keys, manifests={manifest_key: manifest}, jsonl_data=jsonl_data)
        result = await find_latest_timestamp(client, "polymarket", "order_filled")
        assert result == 1718450000

    @pytest.mark.asyncio
    async def test_multiple_dates_uses_latest(self) -> None:
        """Uses the latest date partition when multiple exist."""
        mk1 = "bronze/polymarket/order_filled/dt=2024-06-14/run_id=run-1/manifest.json"
        dk1 = "bronze/polymarket/order_filled/dt=2024-06-14/run_id=run-1/part-000.jsonl.gz"
        mk2 = "bronze/polymarket/order_filled/dt=2024-06-15/run_id=run-2/manifest.json"
        dk2 = "bronze/polymarket/order_filled/dt=2024-06-15/run_id=run-2/part-000.jsonl.gz"

        m1 = _make_manifest(dt="2024-06-14", run_id="run-1",
                            data_key=dk1,
                            generated_at=datetime(2024, 6, 14, 12, 0, 0, tzinfo=UTC))
        m2 = _make_manifest(dt="2024-06-15", run_id="run-2",
                            data_key=dk2,
                            generated_at=datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC))

        keys = [mk1, dk1, mk2, dk2]
        jsonl_data = {
            dk1: [{"timestamp": 1718300000}],
            dk2: [{"timestamp": 1718450000}],
        }
        client = _mock_s3_client(keys=keys, manifests={mk1: m1, mk2: m2}, jsonl_data=jsonl_data)
        result = await find_latest_timestamp(client, "polymarket", "order_filled")
        # Should use latest date (06-15), not 06-14
        assert result == 1718450000

    @pytest.mark.asyncio
    async def test_multiple_runs_uses_latest_generated_at(self) -> None:
        """When multiple runs exist for latest date, uses the one with latest generated_at."""
        mk1 = "bronze/polymarket/order_filled/dt=2024-06-15/run_id=run-1/manifest.json"
        dk1 = "bronze/polymarket/order_filled/dt=2024-06-15/run_id=run-1/part-000.jsonl.gz"
        mk2 = "bronze/polymarket/order_filled/dt=2024-06-15/run_id=run-2/manifest.json"
        dk2 = "bronze/polymarket/order_filled/dt=2024-06-15/run_id=run-2/part-000.jsonl.gz"

        m1 = _make_manifest(run_id="run-1", data_key=dk1,
                            generated_at=datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC))
        m2 = _make_manifest(run_id="run-2", data_key=dk2,
                            generated_at=datetime(2024, 6, 15, 14, 0, 0, tzinfo=UTC))

        keys = [mk1, dk1, mk2, dk2]
        jsonl_data = {
            dk1: [{"timestamp": 1718400000}],
            dk2: [{"timestamp": 1718500000}],
        }
        client = _mock_s3_client(keys=keys, manifests={mk1: m1, mk2: m2}, jsonl_data=jsonl_data)
        result = await find_latest_timestamp(client, "polymarket", "order_filled")
        # Should scan data from run-2 (later generated_at)
        assert result == 1718500000

    @pytest.mark.asyncio
    async def test_no_data_files_returns_none(self) -> None:
        """Returns None when manifest exists but no data files."""
        mk = "bronze/polymarket/order_filled/dt=2024-06-15/run_id=run-1/manifest.json"
        manifest = _make_manifest()
        client = _mock_s3_client(keys=[mk], manifests={mk: manifest})
        result = await find_latest_timestamp(client, "polymarket", "order_filled")
        assert result is None

    @pytest.mark.asyncio
    async def test_records_without_timestamp_field(self) -> None:
        """Returns None when data files have no timestamp field."""
        mk = "bronze/polymarket/order_filled/dt=2024-06-15/run_id=run-1/manifest.json"
        dk = "bronze/polymarket/order_filled/dt=2024-06-15/run_id=run-1/part-000.jsonl.gz"
        manifest = _make_manifest()
        jsonl_data = {dk: [{"id": "1", "value": "foo"}, {"id": "2", "value": "bar"}]}
        client = _mock_s3_client(keys=[mk, dk], manifests={mk: manifest}, jsonl_data=jsonl_data)
        result = await find_latest_timestamp(client, "polymarket", "order_filled")
        assert result is None


class TestFindLatestDate:
    """Tests for find_latest_date()."""

    @pytest.mark.asyncio
    async def test_no_data_returns_none(self) -> None:
        client = _mock_s3_client(keys=[])
        result = await find_latest_date(client, "polymarket", "trades")
        assert result is None

    @pytest.mark.asyncio
    async def test_single_date(self) -> None:
        keys = ["bronze/polymarket/trades/dt=2024-06-15/run_id=abc/part-000.jsonl.gz"]
        client = _mock_s3_client(keys=keys)
        result = await find_latest_date(client, "polymarket", "trades")
        assert result == "2024-06-15"

    @pytest.mark.asyncio
    async def test_multiple_dates_returns_latest(self) -> None:
        keys = [
            "bronze/polymarket/trades/dt=2024-06-13/run_id=a/part-000.jsonl.gz",
            "bronze/polymarket/trades/dt=2024-06-15/run_id=b/part-000.jsonl.gz",
            "bronze/polymarket/trades/dt=2024-06-14/run_id=c/part-000.jsonl.gz",
        ]
        client = _mock_s3_client(keys=keys)
        result = await find_latest_date(client, "polymarket", "trades")
        assert result == "2024-06-15"
