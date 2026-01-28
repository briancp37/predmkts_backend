"""Backfill tests for the ingestion pipeline.

Validates that backfill capability works correctly:
- Running ingestion with a past date produces valid Bronze output
- Multiple backfill runs for the same date create unique run_ids (no overwrites)
- Backfill data lands in the correct S3 path with the specified date
- Manifests are created for each backfill run
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prediction_data.bronze.kalshi.ingest import (
    ingest_trades as kalshi_ingest_trades,
)
from prediction_data.bronze.polymarket.ingest import (
    ingest_trades as poly_ingest_trades,
)
from prediction_data.core.compression import decompress_jsonl
from prediction_data.storage.manifest import Manifest
from prediction_data.storage.s3 import S3Client as RealS3Client
from prediction_data.storage.s3 import validate_bronze_key

PAST_DATE = "2025-06-15"

SAMPLE_POLY_TRADES = [
    {"id": "t1", "side": "BUY", "size": "10", "price": "0.55", "condition_id": "0xabc"},
    {"id": "t2", "side": "SELL", "size": "5", "price": "0.45", "condition_id": "0xdef"},
]

SAMPLE_KALSHI_TRADES = [
    {"ticker": "KXBTC-24", "side": "yes", "count": 5, "yes_price": 60, "no_price": 40},
    {"ticker": "KXBTC-24", "side": "no", "count": 3, "yes_price": 55, "no_price": 45},
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


def _make_poly_mocks(fake_s3: FakeS3Client):
    """Return patch context managers for Polymarket trades ingestion."""
    return (
        patch("prediction_data.bronze.polymarket.ingest.PolymarketClient"),
        patch("prediction_data.bronze.polymarket.ingest.S3Client"),
        patch("prediction_data.bronze.polymarket.ingest.get_settings"),
    )


def _make_kalshi_mocks(fake_s3: FakeS3Client):
    """Return patch context managers for Kalshi trades ingestion."""
    return (
        patch("prediction_data.bronze.kalshi.ingest.KalshiClient"),
        patch("prediction_data.bronze.kalshi.ingest.S3Client"),
        patch("prediction_data.bronze.kalshi.ingest.get_settings"),
        patch("prediction_data.bronze.kalshi.ingest.load_credentials_from_settings"),
    )


async def _run_poly_backfill(fake_s3: FakeS3Client, dt: str = PAST_DATE) -> str:
    """Run a Polymarket trades backfill and return the run_id."""
    with (
        patch("prediction_data.bronze.polymarket.ingest.PolymarketClient") as MockClient,
        patch("prediction_data.bronze.polymarket.ingest.S3Client") as MockS3,
        patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
    ):
        mock_settings.return_value = MagicMock(bronze_bucket="test-bucket")
        client_instance = AsyncMock()
        client_instance.fetch_trades.return_value = (SAMPLE_POLY_TRADES, False)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        MockS3.return_value = RealS3Client(bucket="test-bucket", s3_client=fake_s3)
        return await poly_ingest_trades(dt=dt)


async def _run_kalshi_backfill(fake_s3: FakeS3Client, dt: str = PAST_DATE) -> str:
    """Run a Kalshi trades backfill and return the run_id."""
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
        return await kalshi_ingest_trades(dt=dt)


class TestPolymarketTradesBackfill:
    """Backfill tests for Polymarket trades ingestion."""

    @pytest.mark.asyncio
    async def test_backfill_past_date_produces_valid_output(self) -> None:
        """Backfill with a past date produces valid Bronze S3 output."""
        fake_s3 = FakeS3Client()
        run_id = await _run_poly_backfill(fake_s3)

        assert run_id
        keys = list(fake_s3.objects.keys())
        assert len(keys) == 2

        data_key = [k for k in keys if k.endswith(".jsonl.gz")][0]
        manifest_key = [k for k in keys if k.endswith("manifest.json")][0]

        assert validate_bronze_key(data_key)
        assert validate_bronze_key(manifest_key)

    @pytest.mark.asyncio
    async def test_backfill_lands_in_correct_s3_path(self) -> None:
        """Backfill data uses the specified past date in the S3 path."""
        fake_s3 = FakeS3Client()
        await _run_poly_backfill(fake_s3)

        data_key = [k for k in fake_s3.objects if k.endswith(".jsonl.gz")][0]
        assert f"bronze/polymarket/trades/" in data_key
        assert f"dt={PAST_DATE}/" in data_key
        assert "run_id=" in data_key

    @pytest.mark.asyncio
    async def test_backfill_manifest_created(self) -> None:
        """Backfill run produces a manifest with correct metadata."""
        fake_s3 = FakeS3Client()
        run_id = await _run_poly_backfill(fake_s3)

        manifest_key = [k for k in fake_s3.objects if k.endswith("manifest.json")][0]
        manifest = Manifest.from_json(fake_s3.objects[manifest_key].decode("utf-8"))

        assert manifest.run_id == run_id
        assert manifest.platform == "polymarket"
        assert manifest.entity == "trades"
        assert manifest.dt == PAST_DATE
        assert manifest.row_count == len(SAMPLE_POLY_TRADES)

    @pytest.mark.asyncio
    async def test_backfill_creates_new_run_id_no_overwrite(self) -> None:
        """Multiple backfills for the same date create separate run_ids."""
        run_ids = []
        all_keys: list[str] = []

        for _ in range(3):
            fake_s3 = FakeS3Client()
            run_id = await _run_poly_backfill(fake_s3)
            run_ids.append(run_id)
            all_keys.extend(fake_s3.objects.keys())

        # All run_ids must be unique
        assert len(set(run_ids)) == 3, f"Run IDs not unique: {run_ids}"

        # All S3 keys must be unique (different run_id in path)
        assert len(set(all_keys)) == 6, f"S3 keys not unique: {all_keys}"


class TestKalshiTradesBackfill:
    """Backfill tests for Kalshi trades ingestion."""

    @pytest.mark.asyncio
    async def test_backfill_past_date_produces_valid_output(self) -> None:
        """Backfill with a past date produces valid Bronze S3 output."""
        fake_s3 = FakeS3Client()
        run_id = await _run_kalshi_backfill(fake_s3)

        assert run_id
        keys = list(fake_s3.objects.keys())
        assert len(keys) == 2

        data_key = [k for k in keys if k.endswith(".jsonl.gz")][0]
        manifest_key = [k for k in keys if k.endswith("manifest.json")][0]

        assert validate_bronze_key(data_key)
        assert validate_bronze_key(manifest_key)

    @pytest.mark.asyncio
    async def test_backfill_lands_in_correct_s3_path(self) -> None:
        """Backfill data uses the specified past date in the S3 path."""
        fake_s3 = FakeS3Client()
        await _run_kalshi_backfill(fake_s3)

        data_key = [k for k in fake_s3.objects if k.endswith(".jsonl.gz")][0]
        assert "bronze/kalshi/trades/" in data_key
        assert f"dt={PAST_DATE}/" in data_key
        assert "run_id=" in data_key

    @pytest.mark.asyncio
    async def test_backfill_manifest_created(self) -> None:
        """Backfill run produces a manifest with correct metadata."""
        fake_s3 = FakeS3Client()
        run_id = await _run_kalshi_backfill(fake_s3)

        manifest_key = [k for k in fake_s3.objects if k.endswith("manifest.json")][0]
        manifest = Manifest.from_json(fake_s3.objects[manifest_key].decode("utf-8"))

        assert manifest.run_id == run_id
        assert manifest.platform == "kalshi"
        assert manifest.entity == "trades"
        assert manifest.dt == PAST_DATE
        assert manifest.row_count == len(SAMPLE_KALSHI_TRADES)

    @pytest.mark.asyncio
    async def test_backfill_creates_new_run_id_no_overwrite(self) -> None:
        """Multiple backfills for the same date create separate run_ids."""
        run_ids = []
        all_keys: list[str] = []

        for _ in range(3):
            fake_s3 = FakeS3Client()
            run_id = await _run_kalshi_backfill(fake_s3)
            run_ids.append(run_id)
            all_keys.extend(fake_s3.objects.keys())

        assert len(set(run_ids)) == 3, f"Run IDs not unique: {run_ids}"
        assert len(set(all_keys)) == 6, f"S3 keys not unique: {all_keys}"
