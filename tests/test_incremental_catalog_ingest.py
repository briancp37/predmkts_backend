"""Tests for incremental catalog ingestion (markets and events)."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from prediction_data.bronze.polymarket.ingest import (
    _epoch_to_iso,
    _iso_to_epoch,
    ingest_events,
    ingest_markets,
)

SAMPLE_MARKETS: list[dict[str, Any]] = [
    {
        "id": "m1",
        "condition_id": "0xabc",
        "question": "Will X happen?",
        "slug": "will-x-happen",
        "updatedAt": "2026-02-01T15:00:00Z",
    },
    {
        "id": "m2",
        "condition_id": "0xdef",
        "question": "Will Y happen?",
        "slug": "will-y-happen",
        "updatedAt": "2026-02-01T12:00:00Z",
    },
]

SAMPLE_EVENTS: list[dict[str, Any]] = [
    {
        "id": "e1",
        "title": "Event X",
        "slug": "event-x",
        "updatedAt": "2026-02-01T18:00:00Z",
    },
    {
        "id": "e2",
        "title": "Event Y",
        "slug": "event-y",
        "updatedAt": "2026-02-01T10:00:00Z",
    },
]


class TestIsoEpochConversion:
    """Tests for ISO 8601 <-> epoch conversion helpers."""

    def test_iso_to_epoch(self) -> None:
        assert _iso_to_epoch("2026-02-01T12:00:00Z") == 1769947200

    def test_epoch_to_iso(self) -> None:
        assert _epoch_to_iso(1769947200) == "2026-02-01T12:00:00Z"

    def test_roundtrip(self) -> None:
        iso = "2026-02-01T15:30:45Z"
        assert _epoch_to_iso(_iso_to_epoch(iso)) == "2026-02-01T15:30:45Z"


def _setup_mocks(
    mock_s3_class: Any,
    mock_settings: Any,
    platform: str = "polymarket",
    entity: str = "markets",
) -> AsyncMock:
    """Configure common mocks and return the mock S3 client."""
    mock_settings.return_value.bronze_bucket = "test-bucket"
    mock_s3 = AsyncMock()
    mock_s3.upload_jsonl.return_value = (
        f"bronze/{platform}/{entity}/dt=2026-02-02/run_id=abc/part-000.jsonl.gz",
        2,
    )
    mock_s3.upload_manifest.return_value = (
        f"bronze/{platform}/{entity}/dt=2026-02-02/run_id=abc/manifest.json"
    )
    mock_s3_class.return_value.__aenter__.return_value = mock_s3
    return mock_s3


class TestIngestMarketsIncremental:
    """Tests for incremental markets ingestion."""

    @pytest.mark.asyncio
    async def test_incremental_calls_fetch_incremental(self) -> None:
        """Incremental mode calls fetch_markets_incremental with correct cutoff."""
        with (
            patch("prediction_data.bronze.polymarket.ingest.PolymarketClient") as mock_client_class,
            patch("prediction_data.bronze.polymarket.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
            patch("prediction_data.bronze.polymarket.ingest.create_manifest") as mock_manifest,
        ):
            _setup_mocks(mock_s3_class, mock_settings)
            mock_manifest.return_value = AsyncMock()

            mock_client = AsyncMock()
            mock_client.fetch_markets_incremental.return_value = (
                SAMPLE_MARKETS,
                "2026-02-01T15:00:00Z",
            )
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await ingest_markets(
                dt="2026-02-02",
                since_updated_at="2026-01-31T00:00:00Z",
            )

            mock_client.fetch_markets_incremental.assert_called_once_with(
                since_updated_at="2026-01-31T00:00:00Z",
                include_closed=True,
            )
            # Should NOT call fetch_all_markets
            mock_client.fetch_all_markets.assert_not_called()

    @pytest.mark.asyncio
    async def test_incremental_writes_delta_manifest(self) -> None:
        """Incremental mode writes manifest with snapshot_type='delta' and latest_timestamp."""
        with (
            patch("prediction_data.bronze.polymarket.ingest.PolymarketClient") as mock_client_class,
            patch("prediction_data.bronze.polymarket.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
            patch("prediction_data.bronze.polymarket.ingest.create_manifest") as mock_manifest,
        ):
            _setup_mocks(mock_s3_class, mock_settings)
            mock_manifest.return_value = AsyncMock()

            mock_client = AsyncMock()
            mock_client.fetch_markets_incremental.return_value = (
                SAMPLE_MARKETS,
                "2026-02-01T15:00:00Z",
            )
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await ingest_markets(
                dt="2026-02-02",
                since_updated_at="2026-01-31T00:00:00Z",
            )

            manifest_kwargs = mock_manifest.call_args.kwargs
            assert manifest_kwargs["snapshot_type"] == "delta"
            assert manifest_kwargs["latest_timestamp"] == _iso_to_epoch("2026-02-01T15:00:00Z")

    @pytest.mark.asyncio
    async def test_full_snapshot_calls_fetch_all(self) -> None:
        """Without since_updated_at, uses full snapshot mode."""
        with (
            patch("prediction_data.bronze.polymarket.ingest.PolymarketClient") as mock_client_class,
            patch("prediction_data.bronze.polymarket.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
            patch("prediction_data.bronze.polymarket.ingest.create_manifest") as mock_manifest,
        ):
            _setup_mocks(mock_s3_class, mock_settings)
            mock_manifest.return_value = AsyncMock()

            mock_client = AsyncMock()
            mock_client.fetch_all_markets.return_value = SAMPLE_MARKETS
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await ingest_markets(dt="2026-02-02")

            mock_client.fetch_all_markets.assert_called_once_with(include_closed=True)
            mock_client.fetch_markets_incremental.assert_not_called()

    @pytest.mark.asyncio
    async def test_full_snapshot_writes_snapshot_manifest(self) -> None:
        """Full snapshot writes manifest with snapshot_type='snapshot' and latest_timestamp from records."""
        with (
            patch("prediction_data.bronze.polymarket.ingest.PolymarketClient") as mock_client_class,
            patch("prediction_data.bronze.polymarket.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
            patch("prediction_data.bronze.polymarket.ingest.create_manifest") as mock_manifest,
        ):
            _setup_mocks(mock_s3_class, mock_settings)
            mock_manifest.return_value = AsyncMock()

            mock_client = AsyncMock()
            mock_client.fetch_all_markets.return_value = SAMPLE_MARKETS
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await ingest_markets(dt="2026-02-02")

            manifest_kwargs = mock_manifest.call_args.kwargs
            assert manifest_kwargs["snapshot_type"] == "snapshot"
            # Full snapshots now extract max updatedAt for cursor tracking
            assert manifest_kwargs["latest_timestamp"] == _iso_to_epoch("2026-02-01T15:00:00Z")

    @pytest.mark.asyncio
    async def test_zero_change_incremental_preserves_cursor(self) -> None:
        """When incremental fetch returns no records, latest_timestamp preserves the cursor."""
        with (
            patch("prediction_data.bronze.polymarket.ingest.PolymarketClient") as mock_client_class,
            patch("prediction_data.bronze.polymarket.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
            patch("prediction_data.bronze.polymarket.ingest.create_manifest") as mock_manifest,
        ):
            _setup_mocks(mock_s3_class, mock_settings)
            mock_manifest.return_value = AsyncMock()

            cutoff = "2026-02-01T00:00:00Z"
            mock_client = AsyncMock()
            # No new records: max_updated_at == since_updated_at
            mock_client.fetch_markets_incremental.return_value = ([], cutoff)
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await ingest_markets(dt="2026-02-02", since_updated_at=cutoff)

            manifest_kwargs = mock_manifest.call_args.kwargs
            assert manifest_kwargs["snapshot_type"] == "delta"
            assert manifest_kwargs["latest_timestamp"] == _iso_to_epoch(cutoff)


class TestIngestEventsIncremental:
    """Tests for incremental events ingestion."""

    @pytest.mark.asyncio
    async def test_incremental_calls_fetch_incremental(self) -> None:
        """Incremental mode calls fetch_events_incremental."""
        with (
            patch("prediction_data.bronze.polymarket.ingest.PolymarketClient") as mock_client_class,
            patch("prediction_data.bronze.polymarket.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
            patch("prediction_data.bronze.polymarket.ingest.create_manifest") as mock_manifest,
        ):
            _setup_mocks(mock_s3_class, mock_settings, entity="events")
            mock_manifest.return_value = AsyncMock()

            mock_client = AsyncMock()
            mock_client.fetch_events_incremental.return_value = (
                SAMPLE_EVENTS,
                "2026-02-01T18:00:00Z",
            )
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await ingest_events(
                dt="2026-02-02",
                since_updated_at="2026-01-31T00:00:00Z",
            )

            mock_client.fetch_events_incremental.assert_called_once_with(
                since_updated_at="2026-01-31T00:00:00Z",
                include_closed=True,
            )
            mock_client.fetch_all_events.assert_not_called()

    @pytest.mark.asyncio
    async def test_incremental_writes_delta_manifest(self) -> None:
        """Incremental events writes delta manifest with latest_timestamp."""
        with (
            patch("prediction_data.bronze.polymarket.ingest.PolymarketClient") as mock_client_class,
            patch("prediction_data.bronze.polymarket.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
            patch("prediction_data.bronze.polymarket.ingest.create_manifest") as mock_manifest,
        ):
            _setup_mocks(mock_s3_class, mock_settings, entity="events")
            mock_manifest.return_value = AsyncMock()

            mock_client = AsyncMock()
            mock_client.fetch_events_incremental.return_value = (
                SAMPLE_EVENTS,
                "2026-02-01T18:00:00Z",
            )
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await ingest_events(
                dt="2026-02-02",
                since_updated_at="2026-01-31T00:00:00Z",
            )

            manifest_kwargs = mock_manifest.call_args.kwargs
            assert manifest_kwargs["snapshot_type"] == "delta"
            assert manifest_kwargs["latest_timestamp"] == _iso_to_epoch("2026-02-01T18:00:00Z")

    @pytest.mark.asyncio
    async def test_full_snapshot_writes_latest_timestamp(self) -> None:
        """Full snapshot events writes manifest with latest_timestamp from records."""
        with (
            patch("prediction_data.bronze.polymarket.ingest.PolymarketClient") as mock_client_class,
            patch("prediction_data.bronze.polymarket.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
            patch("prediction_data.bronze.polymarket.ingest.create_manifest") as mock_manifest,
        ):
            _setup_mocks(mock_s3_class, mock_settings, entity="events")
            mock_manifest.return_value = AsyncMock()

            mock_client = AsyncMock()
            mock_client.fetch_all_events.return_value = SAMPLE_EVENTS
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await ingest_events(dt="2026-02-02")

            manifest_kwargs = mock_manifest.call_args.kwargs
            assert manifest_kwargs["snapshot_type"] == "snapshot"
            # Full snapshots now extract max updatedAt for cursor tracking
            assert manifest_kwargs["latest_timestamp"] == _iso_to_epoch("2026-02-01T18:00:00Z")

    @pytest.mark.asyncio
    async def test_zero_change_incremental_writes_empty_delta(self) -> None:
        """Zero-change incremental run writes empty delta with preserved cursor."""
        with (
            patch("prediction_data.bronze.polymarket.ingest.PolymarketClient") as mock_client_class,
            patch("prediction_data.bronze.polymarket.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
            patch("prediction_data.bronze.polymarket.ingest.create_manifest") as mock_manifest,
        ):
            mock_s3 = _setup_mocks(mock_s3_class, mock_settings, entity="events")
            mock_s3.upload_jsonl.return_value = (
                "bronze/polymarket/events/dt=2026-02-02/run_id=abc/part-000.jsonl.gz",
                0,
            )
            mock_manifest.return_value = AsyncMock()

            cutoff = "2026-02-01T00:00:00Z"
            mock_client = AsyncMock()
            mock_client.fetch_events_incremental.return_value = ([], cutoff)
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await ingest_events(dt="2026-02-02", since_updated_at=cutoff)

            manifest_kwargs = mock_manifest.call_args.kwargs
            assert manifest_kwargs["snapshot_type"] == "delta"
            assert manifest_kwargs["row_count"] == 0
            assert manifest_kwargs["latest_timestamp"] == _iso_to_epoch(cutoff)


class TestFindLatestManifestSource:
    """Tests for find_latest_manifest_source discovery helper."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_partitions(self) -> None:
        from prediction_data.storage.discovery import find_latest_manifest_source

        mock_s3 = AsyncMock()
        mock_s3.list_prefixes.return_value = []

        date, ts = await find_latest_manifest_source(mock_s3, "polymarket", "markets")
        assert date is None
        assert ts is None

    @pytest.mark.asyncio
    async def test_returns_latest_timestamp_from_manifest(self) -> None:
        from prediction_data.storage.discovery import find_latest_manifest_source
        from prediction_data.storage.manifest import FileReference, Manifest, Source

        mock_s3 = AsyncMock()
        mock_s3.list_prefixes.return_value = [
            "bronze/polymarket/markets/dt=2026-02-01/",
        ]
        mock_s3.list_keys.return_value = [
            "bronze/polymarket/markets/dt=2026-02-01/run_id=abc/manifest.json",
        ]

        manifest = Manifest(
            run_id="abc",
            platform="polymarket",
            entity="markets",
            dt="2026-02-01",
            generated_at="2026-02-01T12:00:00Z",
            row_count=100,
            files=[FileReference(bucket="b", key="k")],
            source=Source(
                api_base_url="https://example.com",
                pagination="offset",
                latest_timestamp=1769947200,
                snapshot_type="delta",
            ),
        )
        mock_s3.download_manifest.return_value = manifest

        date, ts = await find_latest_manifest_source(mock_s3, "polymarket", "markets")
        assert date == "2026-02-01"
        assert ts == 1769947200

    @pytest.mark.asyncio
    async def test_returns_none_timestamp_when_not_in_manifest(self) -> None:
        from prediction_data.storage.discovery import find_latest_manifest_source
        from prediction_data.storage.manifest import FileReference, Manifest, Source

        mock_s3 = AsyncMock()
        mock_s3.list_prefixes.return_value = [
            "bronze/polymarket/markets/dt=2026-02-01/",
        ]
        mock_s3.list_keys.return_value = [
            "bronze/polymarket/markets/dt=2026-02-01/run_id=abc/manifest.json",
        ]

        manifest = Manifest(
            run_id="abc",
            platform="polymarket",
            entity="markets",
            dt="2026-02-01",
            generated_at="2026-02-01T12:00:00Z",
            row_count=100,
            files=[FileReference(bucket="b", key="k")],
            source=Source(
                api_base_url="https://example.com",
                pagination="offset",
            ),
        )
        mock_s3.download_manifest.return_value = manifest

        date, ts = await find_latest_manifest_source(mock_s3, "polymarket", "markets")
        assert date == "2026-02-01"
        assert ts is None
