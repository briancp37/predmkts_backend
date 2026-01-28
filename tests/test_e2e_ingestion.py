"""End-to-end tests for the complete ingestion pipeline.

These tests validate that all 4 ingestion commands produce correct Bronze output:
- Polymarket trades: fetch → compress → upload JSONL + manifest to S3
- Polymarket markets: fetch → compress → upload JSONL + manifest to S3
- Kalshi trades: fetch → compress → upload JSONL + manifest to S3
- Kalshi markets: fetch → compress → upload JSONL + manifest to S3

Each test mocks the API client and S3 to validate the full pipeline flow
without requiring live API access or AWS credentials.
"""

import gzip
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prediction_data.bronze.kalshi.ingest import (
    ingest_markets as kalshi_ingest_markets,
)
from prediction_data.bronze.kalshi.ingest import (
    ingest_trades as kalshi_ingest_trades,
)
from prediction_data.bronze.polymarket.ingest import (
    ingest_markets as poly_ingest_markets,
)
from prediction_data.bronze.polymarket.ingest import (
    ingest_trades as poly_ingest_trades,
)
from prediction_data.core.compression import decompress_jsonl
from prediction_data.storage.manifest import Manifest
from prediction_data.storage.s3 import S3Client as RealS3Client
from prediction_data.storage.s3 import validate_bronze_key


# --- Fixtures ---

SAMPLE_POLY_TRADES = [
    {"id": "t1", "side": "BUY", "size": "10", "price": "0.55", "condition_id": "0xabc"},
    {"id": "t2", "side": "SELL", "size": "5", "price": "0.45", "condition_id": "0xdef"},
    {"id": "t3", "side": "BUY", "size": "20", "price": "0.70", "condition_id": "0xabc"},
]

SAMPLE_POLY_MARKETS = [
    {"id": "m1", "condition_id": "0xabc", "question": "Will X happen?", "slug": "will-x-happen"},
    {"id": "m2", "condition_id": "0xdef", "question": "Will Y happen?", "slug": "will-y-happen"},
]

SAMPLE_KALSHI_TRADES = [
    {"ticker": "KXBTC-24", "side": "yes", "count": 5, "yes_price": 60, "no_price": 40},
    {"ticker": "KXBTC-24", "side": "no", "count": 3, "yes_price": 55, "no_price": 45},
]

SAMPLE_KALSHI_MARKETS = [
    {"ticker": "KXBTC-24", "title": "Bitcoin above 50k?", "status": "open"},
    {"ticker": "KXETH-24", "title": "Ethereum above 3k?", "status": "open"},
    {"ticker": "KXSOL-24", "title": "Solana above 100?", "status": "closed"},
]


class FakeS3Client:
    """Captures all S3 put_object calls for validation."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, Bucket: str, Key: str, Body: bytes, **kwargs: Any) -> None:
        self.objects[Key] = Body

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        body = MagicMock()
        body.read.return_value = self.objects[Key]
        return {"Body": body}


def _validate_s3_output(
    fake_s3: FakeS3Client,
    platform: str,
    entity: str,
    dt: str,
    expected_row_count: int,
) -> None:
    """Validate that S3 contains correctly structured Bronze output."""
    keys = list(fake_s3.objects.keys())

    # Should have exactly 2 objects: data file + manifest
    assert len(keys) == 2, f"Expected 2 S3 objects, got {len(keys)}: {keys}"

    # Identify data and manifest keys
    data_keys = [k for k in keys if k.endswith(".jsonl.gz")]
    manifest_keys = [k for k in keys if k.endswith("manifest.json")]
    assert len(data_keys) == 1, f"Expected 1 data file, got {data_keys}"
    assert len(manifest_keys) == 1, f"Expected 1 manifest, got {manifest_keys}"

    data_key = data_keys[0]
    manifest_key = manifest_keys[0]

    # Validate key structure matches Bronze pattern
    assert validate_bronze_key(data_key), f"Data key doesn't match Bronze pattern: {data_key}"
    assert validate_bronze_key(manifest_key), f"Manifest key doesn't match Bronze pattern: {manifest_key}"

    # Validate key contains correct platform/entity/dt
    assert f"bronze/{platform}/{entity}/" in data_key
    assert f"dt={dt}/" in data_key
    assert "run_id=" in data_key
    assert data_key.endswith("part-000.jsonl.gz")

    # Validate data file: decompress and check JSONL content
    records = decompress_jsonl(fake_s3.objects[data_key])
    assert len(records) == expected_row_count, (
        f"Expected {expected_row_count} records, got {len(records)}"
    )
    for record in records:
        assert isinstance(record, dict)

    # Validate manifest
    manifest_json = fake_s3.objects[manifest_key].decode("utf-8")
    manifest = Manifest.from_json(manifest_json)
    assert manifest.platform == platform
    assert manifest.entity == entity
    assert manifest.dt == dt
    assert manifest.row_count == expected_row_count
    assert len(manifest.files) == 1
    assert manifest.files[0].key == data_key
    assert manifest.run_id  # non-empty
    assert manifest.generated_at is not None
    assert manifest.source.api_base_url  # non-empty
    assert manifest.source.pagination in ("cursor", "offset", "none")


# --- Polymarket E2E Tests ---


class TestPolymarketTradesE2E:
    """End-to-end test for Polymarket trades ingestion."""

    @pytest.mark.asyncio
    async def test_full_pipeline_produces_valid_bronze_output(self) -> None:
        fake_s3 = FakeS3Client()

        with (
            patch(
                "prediction_data.bronze.polymarket.ingest.PolymarketClient"
            ) as MockClient,
            patch(
                "prediction_data.bronze.polymarket.ingest.S3Client"
            ) as MockS3,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(bronze_bucket="test-bucket")

            # Mock the Polymarket client
            client_instance = AsyncMock()
            client_instance.fetch_trades.return_value = (SAMPLE_POLY_TRADES, False)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            MockS3.return_value = RealS3Client(bucket="test-bucket", s3_client=fake_s3)

            run_id = await poly_ingest_trades(dt="2026-01-28")

        assert run_id  # non-empty string
        _validate_s3_output(fake_s3, "polymarket", "trades", "2026-01-28", len(SAMPLE_POLY_TRADES))


class TestPolymarketMarketsE2E:
    """End-to-end test for Polymarket markets ingestion."""

    @pytest.mark.asyncio
    async def test_full_pipeline_produces_valid_bronze_output(self) -> None:
        fake_s3 = FakeS3Client()

        with (
            patch(
                "prediction_data.bronze.polymarket.ingest.PolymarketClient"
            ) as MockClient,
            patch(
                "prediction_data.bronze.polymarket.ingest.S3Client"
            ) as MockS3,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(bronze_bucket="test-bucket")

            client_instance = AsyncMock()
            client_instance.fetch_all_markets.return_value = SAMPLE_POLY_MARKETS
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            MockS3.return_value = RealS3Client(bucket="test-bucket", s3_client=fake_s3)

            run_id = await poly_ingest_markets(dt="2026-01-28")

        assert run_id
        _validate_s3_output(fake_s3, "polymarket", "markets", "2026-01-28", len(SAMPLE_POLY_MARKETS))


# --- Kalshi E2E Tests ---


class TestKalshiTradesE2E:
    """End-to-end test for Kalshi trades ingestion."""

    @pytest.mark.asyncio
    async def test_full_pipeline_produces_valid_bronze_output(self) -> None:
        fake_s3 = FakeS3Client()

        with (
            patch("prediction_data.bronze.kalshi.ingest.KalshiClient") as MockClient,
            patch("prediction_data.bronze.kalshi.ingest.S3Client") as MockS3,
            patch("prediction_data.bronze.kalshi.ingest.get_settings") as mock_settings,
            patch("prediction_data.bronze.kalshi.ingest.load_credentials_from_settings") as mock_creds,
        ):
            mock_settings.return_value = MagicMock(bronze_bucket="test-bucket")
            mock_creds.return_value = MagicMock()

            client_instance = AsyncMock()
            client_instance.fetch_all_trades.return_value = SAMPLE_KALSHI_TRADES
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            MockS3.return_value = RealS3Client(bucket="test-bucket", s3_client=fake_s3)

            run_id = await kalshi_ingest_trades(dt="2026-01-28")

        assert run_id
        _validate_s3_output(fake_s3, "kalshi", "trades", "2026-01-28", len(SAMPLE_KALSHI_TRADES))


class TestKalshiMarketsE2E:
    """End-to-end test for Kalshi markets ingestion."""

    @pytest.mark.asyncio
    async def test_full_pipeline_produces_valid_bronze_output(self) -> None:
        fake_s3 = FakeS3Client()

        with (
            patch("prediction_data.bronze.kalshi.ingest.KalshiClient") as MockClient,
            patch("prediction_data.bronze.kalshi.ingest.S3Client") as MockS3,
            patch("prediction_data.bronze.kalshi.ingest.get_settings") as mock_settings,
            patch("prediction_data.bronze.kalshi.ingest.load_credentials_from_settings") as mock_creds,
        ):
            mock_settings.return_value = MagicMock(bronze_bucket="test-bucket")
            mock_creds.return_value = MagicMock()

            client_instance = AsyncMock()
            client_instance.fetch_all_markets.return_value = SAMPLE_KALSHI_MARKETS
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            MockS3.return_value = RealS3Client(bucket="test-bucket", s3_client=fake_s3)

            run_id = await kalshi_ingest_markets(dt="2026-01-28")

        assert run_id
        _validate_s3_output(fake_s3, "kalshi", "markets", "2026-01-28", len(SAMPLE_KALSHI_MARKETS))


# --- Cross-cutting validation tests ---


class TestManifestAccuracy:
    """Validate manifests contain accurate metadata across all pipelines."""

    @pytest.mark.asyncio
    async def test_manifest_row_count_matches_data(self) -> None:
        """Manifest row_count must exactly match number of records in JSONL file."""
        fake_s3 = FakeS3Client()

        with (
            patch(
                "prediction_data.bronze.polymarket.ingest.PolymarketClient"
            ) as MockClient,
            patch(
                "prediction_data.bronze.polymarket.ingest.S3Client"
            ) as MockS3,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value = MagicMock(bronze_bucket="test-bucket")

            client_instance = AsyncMock()
            client_instance.fetch_trades.return_value = (SAMPLE_POLY_TRADES, False)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            MockS3.return_value = RealS3Client(bucket="test-bucket", s3_client=fake_s3)

            await poly_ingest_trades(dt="2026-01-28")

        # Get manifest and data independently
        manifest_key = [k for k in fake_s3.objects if k.endswith("manifest.json")][0]
        data_key = [k for k in fake_s3.objects if k.endswith(".jsonl.gz")][0]

        manifest = Manifest.from_json(fake_s3.objects[manifest_key].decode("utf-8"))
        records = decompress_jsonl(fake_s3.objects[data_key])

        assert manifest.row_count == len(records)

    @pytest.mark.asyncio
    async def test_unique_run_ids_across_runs(self) -> None:
        """Each ingestion run must produce a unique run_id."""
        run_ids: list[str] = []

        for _ in range(3):
            fake_s3 = FakeS3Client()
            with (
                patch(
                    "prediction_data.bronze.polymarket.ingest.PolymarketClient"
                ) as MockClient,
                patch(
                    "prediction_data.bronze.polymarket.ingest.S3Client"
                ) as MockS3,
                patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
            ):
                mock_settings.return_value = MagicMock(bronze_bucket="test-bucket")

                client_instance = AsyncMock()
                client_instance.fetch_all_markets.return_value = SAMPLE_POLY_MARKETS
                MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
                MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

                MockS3.return_value = RealS3Client(bucket="test-bucket", s3_client=fake_s3)

                run_id = await poly_ingest_markets(dt="2026-01-28")
                run_ids.append(run_id)

        assert len(set(run_ids)) == 3, f"Run IDs not unique: {run_ids}"
