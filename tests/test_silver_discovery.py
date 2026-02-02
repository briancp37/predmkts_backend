"""Tests for Silver manifest discovery."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from prediction_data.silver.discovery import (
    DiscoveredManifest,
    discover_manifests,
    select_snapshot_and_deltas,
)
from prediction_data.storage.manifest import Manifest, FileReference, Source


def _make_manifest(
    platform: str = "polymarket",
    entity: str = "trades",
    dt: str = "2024-06-15",
    run_id: str = "run-001",
    row_count: int = 100,
    generated_at: datetime | None = None,
    snapshot_type: str = "snapshot",
) -> Manifest:
    """Create a test manifest."""
    if generated_at is None:
        generated_at = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
    return Manifest(
        run_id=run_id,
        platform=platform,
        entity=entity,
        dt=dt,
        generated_at=generated_at,
        files=[FileReference(bucket="test-bucket", key=f"bronze/{platform}/{entity}/dt={dt}/run_id={run_id}/part-000.jsonl.gz")],
        row_count=row_count,
        source=Source(api_base_url="https://example.com", pagination="cursor", snapshot_type=snapshot_type),
    )


def _mock_s3_client(
    date_prefixes: list[str],
    keys_by_prefix: dict[str, list[str]],
    manifests_by_key: dict[str, Manifest],
) -> AsyncMock:
    """Build a mock S3Client."""
    client = AsyncMock()
    client.list_prefixes = AsyncMock(return_value=date_prefixes)

    async def _list_keys(prefix: str) -> list[str]:
        return keys_by_prefix.get(prefix, [])

    client.list_keys = AsyncMock(side_effect=_list_keys)

    async def _download_manifest(key: str) -> Manifest:
        if key not in manifests_by_key:
            raise ValueError(f"Manifest not found: {key}")
        return manifests_by_key[key]

    client.download_manifest = AsyncMock(side_effect=_download_manifest)
    return client


class TestDiscoverManifests:
    @pytest.mark.asyncio
    async def test_no_partitions_returns_empty(self) -> None:
        client = _mock_s3_client([], {}, {})
        result = await discover_manifests(client, "polymarket", "trades")
        assert result == []

    @pytest.mark.asyncio
    async def test_discovers_single_manifest(self) -> None:
        manifest = _make_manifest()
        mk = "bronze/polymarket/trades/dt=2024-06-15/run_id=run-001/manifest.json"
        client = _mock_s3_client(
            date_prefixes=["bronze/polymarket/trades/dt=2024-06-15/"],
            keys_by_prefix={
                "bronze/polymarket/trades/dt=2024-06-15/": [
                    "bronze/polymarket/trades/dt=2024-06-15/run_id=run-001/part-000.jsonl.gz",
                    mk,
                ],
            },
            manifests_by_key={mk: manifest},
        )
        result = await discover_manifests(client, "polymarket", "trades")
        assert len(result) == 1
        assert result[0].manifest == manifest
        assert result[0].s3_key == mk
        assert result[0].dt == "2024-06-15"
        assert result[0].run_id == "run-001"
        assert result[0].row_count == 100

    @pytest.mark.asyncio
    async def test_filters_by_start_date(self) -> None:
        m1 = _make_manifest(dt="2024-06-10", run_id="r1")
        m2 = _make_manifest(dt="2024-06-15", run_id="r2")
        mk1 = "bronze/polymarket/trades/dt=2024-06-10/run_id=r1/manifest.json"
        mk2 = "bronze/polymarket/trades/dt=2024-06-15/run_id=r2/manifest.json"
        client = _mock_s3_client(
            date_prefixes=[
                "bronze/polymarket/trades/dt=2024-06-10/",
                "bronze/polymarket/trades/dt=2024-06-15/",
            ],
            keys_by_prefix={
                "bronze/polymarket/trades/dt=2024-06-10/": [mk1],
                "bronze/polymarket/trades/dt=2024-06-15/": [mk2],
            },
            manifests_by_key={mk1: m1, mk2: m2},
        )
        result = await discover_manifests(
            client, "polymarket", "trades", start_date="2024-06-12",
        )
        assert len(result) == 1
        assert result[0].dt == "2024-06-15"

    @pytest.mark.asyncio
    async def test_filters_by_end_date(self) -> None:
        m1 = _make_manifest(dt="2024-06-10", run_id="r1")
        m2 = _make_manifest(dt="2024-06-15", run_id="r2")
        mk1 = "bronze/polymarket/trades/dt=2024-06-10/run_id=r1/manifest.json"
        mk2 = "bronze/polymarket/trades/dt=2024-06-15/run_id=r2/manifest.json"
        client = _mock_s3_client(
            date_prefixes=[
                "bronze/polymarket/trades/dt=2024-06-10/",
                "bronze/polymarket/trades/dt=2024-06-15/",
            ],
            keys_by_prefix={
                "bronze/polymarket/trades/dt=2024-06-10/": [mk1],
                "bronze/polymarket/trades/dt=2024-06-15/": [mk2],
            },
            manifests_by_key={mk1: m1, mk2: m2},
        )
        result = await discover_manifests(
            client, "polymarket", "trades", end_date="2024-06-12",
        )
        assert len(result) == 1
        assert result[0].dt == "2024-06-10"

    @pytest.mark.asyncio
    async def test_filters_by_date_range(self) -> None:
        manifests = {}
        keys_by_prefix = {}
        date_prefixes = []
        for day in ["05", "10", "15", "20"]:
            dt = f"2024-06-{day}"
            rid = f"r-{day}"
            mk = f"bronze/polymarket/trades/dt={dt}/run_id={rid}/manifest.json"
            manifests[mk] = _make_manifest(dt=dt, run_id=rid)
            dp = f"bronze/polymarket/trades/dt={dt}/"
            date_prefixes.append(dp)
            keys_by_prefix[dp] = [mk]

        client = _mock_s3_client(date_prefixes, keys_by_prefix, manifests)
        result = await discover_manifests(
            client, "polymarket", "trades",
            start_date="2024-06-10", end_date="2024-06-15",
        )
        assert len(result) == 2
        assert result[0].dt == "2024-06-10"
        assert result[1].dt == "2024-06-15"

    @pytest.mark.asyncio
    async def test_multiple_runs_per_date_sorted_by_generated_at(self) -> None:
        m1 = _make_manifest(
            dt="2024-06-15", run_id="early",
            generated_at=datetime(2024, 6, 15, 8, 0, 0, tzinfo=UTC),
        )
        m2 = _make_manifest(
            dt="2024-06-15", run_id="late",
            generated_at=datetime(2024, 6, 15, 20, 0, 0, tzinfo=UTC),
        )
        mk1 = "bronze/polymarket/trades/dt=2024-06-15/run_id=early/manifest.json"
        mk2 = "bronze/polymarket/trades/dt=2024-06-15/run_id=late/manifest.json"
        client = _mock_s3_client(
            date_prefixes=["bronze/polymarket/trades/dt=2024-06-15/"],
            keys_by_prefix={
                "bronze/polymarket/trades/dt=2024-06-15/": [mk2, mk1],
            },
            manifests_by_key={mk1: m1, mk2: m2},
        )
        result = await discover_manifests(client, "polymarket", "trades")
        assert len(result) == 2
        assert result[0].run_id == "early"
        assert result[1].run_id == "late"

    @pytest.mark.asyncio
    async def test_malformed_manifest_skipped(self) -> None:
        good = _make_manifest(dt="2024-06-15", run_id="good")
        mk_good = "bronze/polymarket/trades/dt=2024-06-15/run_id=good/manifest.json"
        mk_bad = "bronze/polymarket/trades/dt=2024-06-15/run_id=bad/manifest.json"

        client = _mock_s3_client(
            date_prefixes=["bronze/polymarket/trades/dt=2024-06-15/"],
            keys_by_prefix={
                "bronze/polymarket/trades/dt=2024-06-15/": [mk_good, mk_bad],
            },
            manifests_by_key={mk_good: good},  # mk_bad will raise
        )
        result = await discover_manifests(client, "polymarket", "trades")
        assert len(result) == 1
        assert result[0].run_id == "good"

    @pytest.mark.asyncio
    async def test_no_dates_in_range_returns_empty(self) -> None:
        client = _mock_s3_client(
            date_prefixes=["bronze/polymarket/trades/dt=2024-01-01/"],
            keys_by_prefix={},
            manifests_by_key={},
        )
        result = await discover_manifests(
            client, "polymarket", "trades",
            start_date="2024-06-01", end_date="2024-06-30",
        )
        assert result == []


class TestDiscoveredManifest:
    def test_properties(self) -> None:
        manifest = _make_manifest(platform="kalshi", entity="markets", dt="2024-01-01", run_id="abc", row_count=50)
        mk = "bronze/kalshi/markets/dt=2024-01-01/run_id=abc/manifest.json"
        dm = DiscoveredManifest(manifest=manifest, s3_key=mk)
        assert dm.platform == "kalshi"
        assert dm.entity == "markets"
        assert dm.dt == "2024-01-01"
        assert dm.run_id == "abc"
        assert dm.row_count == 50

    def test_snapshot_type_property(self) -> None:
        manifest = _make_manifest(snapshot_type="delta")
        dm = DiscoveredManifest(manifest=manifest, s3_key="k")
        assert dm.snapshot_type == "delta"

    def test_snapshot_type_default(self) -> None:
        manifest = _make_manifest()
        dm = DiscoveredManifest(manifest=manifest, s3_key="k")
        assert dm.snapshot_type == "snapshot"


def _dm(manifest: Manifest) -> DiscoveredManifest:
    return DiscoveredManifest(manifest=manifest, s3_key="key")


class TestSelectSnapshotAndDeltas:
    def test_empty_list(self) -> None:
        assert select_snapshot_and_deltas([]) == []

    def test_single_snapshot(self) -> None:
        m = _dm(_make_manifest(run_id="s1", snapshot_type="snapshot"))
        result = select_snapshot_and_deltas([m])
        assert len(result) == 1
        assert result[0].run_id == "s1"

    def test_selects_latest_snapshot(self) -> None:
        s1 = _dm(_make_manifest(
            run_id="s1", dt="2024-06-10",
            generated_at=datetime(2024, 6, 10, 12, 0, 0, tzinfo=UTC),
        ))
        s2 = _dm(_make_manifest(
            run_id="s2", dt="2024-06-15",
            generated_at=datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
        ))
        result = select_snapshot_and_deltas([s1, s2])
        assert len(result) == 1
        assert result[0].run_id == "s2"

    def test_snapshot_plus_deltas(self) -> None:
        snap = _dm(_make_manifest(
            run_id="snap", dt="2024-06-10", snapshot_type="snapshot",
            generated_at=datetime(2024, 6, 10, 12, 0, 0, tzinfo=UTC),
        ))
        d1 = _dm(_make_manifest(
            run_id="d1", dt="2024-06-11", snapshot_type="delta",
            generated_at=datetime(2024, 6, 11, 12, 0, 0, tzinfo=UTC),
        ))
        d2 = _dm(_make_manifest(
            run_id="d2", dt="2024-06-12", snapshot_type="delta",
            generated_at=datetime(2024, 6, 12, 12, 0, 0, tzinfo=UTC),
        ))
        result = select_snapshot_and_deltas([snap, d1, d2])
        assert len(result) == 3
        assert result[0].run_id == "snap"
        assert result[1].run_id == "d1"
        assert result[2].run_id == "d2"

    def test_ignores_deltas_before_latest_snapshot(self) -> None:
        old_delta = _dm(_make_manifest(
            run_id="old-d", dt="2024-06-08", snapshot_type="delta",
            generated_at=datetime(2024, 6, 8, 12, 0, 0, tzinfo=UTC),
        ))
        snap = _dm(_make_manifest(
            run_id="snap", dt="2024-06-10", snapshot_type="snapshot",
            generated_at=datetime(2024, 6, 10, 12, 0, 0, tzinfo=UTC),
        ))
        new_delta = _dm(_make_manifest(
            run_id="new-d", dt="2024-06-11", snapshot_type="delta",
            generated_at=datetime(2024, 6, 11, 12, 0, 0, tzinfo=UTC),
        ))
        result = select_snapshot_and_deltas([old_delta, snap, new_delta])
        assert len(result) == 2
        assert result[0].run_id == "snap"
        assert result[1].run_id == "new-d"

    def test_all_snapshots_no_deltas(self) -> None:
        """Pre-sprint-11 data: all are snapshots, picks latest only."""
        s1 = _dm(_make_manifest(
            run_id="s1", dt="2024-06-10",
            generated_at=datetime(2024, 6, 10, 12, 0, 0, tzinfo=UTC),
        ))
        s2 = _dm(_make_manifest(
            run_id="s2", dt="2024-06-15",
            generated_at=datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
        ))
        result = select_snapshot_and_deltas([s1, s2])
        assert len(result) == 1
        assert result[0].run_id == "s2"
