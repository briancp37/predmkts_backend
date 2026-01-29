"""Tests for order_filled ingestion and parquet-to-bronze conversion."""

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from prediction_data.bronze.polymarket.goldsky import GOLDSKY_API_BASE_URL
from prediction_data.bronze.polymarket.ingest import ingest_order_filled

SAMPLE_ORDER_FILLED_EVENTS: list[dict[str, Any]] = [
    {
        "id": "evt1",
        "transactionHash": "0xabc123",
        "orderHash": "0xdef456",
        "timestamp": "1700000000",
        "maker": "0xmaker1",
        "taker": "0xtaker1",
        "makerAssetId": "100",
        "takerAssetId": "200",
        "makerAmountFilled": "5000000",
        "takerAmountFilled": "3000000",
        "fee": "10000",
    },
    {
        "id": "evt2",
        "transactionHash": "0xabc456",
        "orderHash": "0xdef789",
        "timestamp": "1700000100",
        "maker": "0xmaker2",
        "taker": "0xtaker2",
        "makerAssetId": "300",
        "takerAssetId": "400",
        "makerAmountFilled": "7000000",
        "takerAmountFilled": "4000000",
        "fee": "20000",
    },
]


class TestIngestOrderFilled:
    """Tests for the ingest_order_filled function."""

    @pytest.mark.asyncio
    async def test_fetches_and_uploads(self) -> None:
        """Test that ingest_order_filled fetches events and uploads to S3."""
        with (
            patch(
                "prediction_data.bronze.polymarket.goldsky.GoldskyClient"
            ) as mock_client_class,
            patch("prediction_data.bronze.polymarket.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.bronze_bucket = "test-bucket"

            mock_client = AsyncMock()
            mock_client.fetch_all_order_filled_events.return_value = (
                SAMPLE_ORDER_FILLED_EVENTS
            )
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_s3 = AsyncMock()
            mock_s3.upload_jsonl.return_value = (
                "bronze/polymarket/order_filled/dt=2024-11-14/run_id=abc/part-000.jsonl.gz",
                2,
            )
            mock_s3.upload_manifest.return_value = (
                "bronze/polymarket/order_filled/dt=2024-11-14/run_id=abc/manifest.json"
            )
            mock_s3_class.return_value.__aenter__.return_value = mock_s3

            run_id = await ingest_order_filled(dt="2024-11-14")

            # Verify Goldsky client was called with day boundaries
            mock_client.fetch_all_order_filled_events.assert_called_once()
            call_kwargs = mock_client.fetch_all_order_filled_events.call_args.kwargs
            assert call_kwargs["timestamp_gte"] > 0
            assert call_kwargs["timestamp_lte"] > call_kwargs["timestamp_gte"]

            assert isinstance(run_id, str)
            assert len(run_id) > 0

    @pytest.mark.asyncio
    async def test_uploads_with_correct_platform_entity(self) -> None:
        """Test S3 upload uses platform=polymarket, entity=order_filled."""
        with (
            patch(
                "prediction_data.bronze.polymarket.goldsky.GoldskyClient"
            ) as mock_client_class,
            patch("prediction_data.bronze.polymarket.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.bronze_bucket = "test-bucket"

            mock_client = AsyncMock()
            mock_client.fetch_all_order_filled_events.return_value = (
                SAMPLE_ORDER_FILLED_EVENTS
            )
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_s3 = AsyncMock()
            mock_s3.upload_jsonl.return_value = (
                "bronze/polymarket/order_filled/dt=2024-11-14/run_id=x/part-000.jsonl.gz",
                2,
            )
            mock_s3.upload_manifest.return_value = "manifest.json"
            mock_s3_class.return_value.__aenter__.return_value = mock_s3

            await ingest_order_filled(dt="2024-11-14")

            upload_kwargs = mock_s3.upload_jsonl.call_args.kwargs
            assert upload_kwargs["platform"] == "polymarket"
            assert upload_kwargs["entity"] == "order_filled"
            assert upload_kwargs["dt"] == "2024-11-14"
            assert upload_kwargs["records"] == SAMPLE_ORDER_FILLED_EVENTS

    @pytest.mark.asyncio
    async def test_manifest_has_goldsky_api_url(self) -> None:
        """Test manifest includes Goldsky API base URL and cursor pagination."""
        with (
            patch(
                "prediction_data.bronze.polymarket.goldsky.GoldskyClient"
            ) as mock_client_class,
            patch("prediction_data.bronze.polymarket.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
            patch("prediction_data.bronze.polymarket.ingest.create_manifest") as mock_manifest,
        ):
            mock_settings.return_value.bronze_bucket = "test-bucket"

            mock_client = AsyncMock()
            mock_client.fetch_all_order_filled_events.return_value = (
                SAMPLE_ORDER_FILLED_EVENTS
            )
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_s3 = AsyncMock()
            mock_s3.upload_jsonl.return_value = ("key", 2)
            mock_s3.upload_manifest.return_value = "manifest.json"
            mock_s3_class.return_value.__aenter__.return_value = mock_s3

            mock_manifest.return_value = {"mocked": True}

            await ingest_order_filled(dt="2024-11-14")

            mock_manifest.assert_called_once()
            manifest_kwargs = mock_manifest.call_args.kwargs
            assert manifest_kwargs["api_base_url"] == GOLDSKY_API_BASE_URL
            assert manifest_kwargs["pagination"] == "cursor"
            assert manifest_kwargs["platform"] == "polymarket"
            assert manifest_kwargs["entity"] == "order_filled"

    @pytest.mark.asyncio
    async def test_custom_bucket(self) -> None:
        """Test that a custom bucket overrides settings."""
        with (
            patch(
                "prediction_data.bronze.polymarket.goldsky.GoldskyClient"
            ) as mock_client_class,
            patch("prediction_data.bronze.polymarket.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.bronze_bucket = "default-bucket"

            mock_client = AsyncMock()
            mock_client.fetch_all_order_filled_events.return_value = []
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_s3 = AsyncMock()
            mock_s3.upload_jsonl.return_value = ("key", 0)
            mock_s3.upload_manifest.return_value = "manifest.json"
            mock_s3_class.return_value.__aenter__.return_value = mock_s3

            await ingest_order_filled(dt="2024-11-14", bucket="custom-bucket")

            mock_s3_class.assert_called_once_with(bucket="custom-bucket")

    @pytest.mark.asyncio
    async def test_day_boundaries_are_correct(self) -> None:
        """Test that day boundaries are computed as start-of-day and end-of-day UTC."""
        with (
            patch(
                "prediction_data.bronze.polymarket.goldsky.GoldskyClient"
            ) as mock_client_class,
            patch("prediction_data.bronze.polymarket.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.bronze_bucket = "test-bucket"

            mock_client = AsyncMock()
            mock_client.fetch_all_order_filled_events.return_value = []
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_s3 = AsyncMock()
            mock_s3.upload_jsonl.return_value = ("key", 0)
            mock_s3.upload_manifest.return_value = "manifest.json"
            mock_s3_class.return_value.__aenter__.return_value = mock_s3

            await ingest_order_filled(dt="2024-11-14")

            call_kwargs = mock_client.fetch_all_order_filled_events.call_args.kwargs
            # 2024-11-14 00:00:00 UTC = 1731542400
            assert call_kwargs["timestamp_gte"] == 1731542400
            # 2024-11-14 23:59:59 UTC = 1731628799
            assert call_kwargs["timestamp_lte"] == 1731628799


class TestParquetConversion:
    """Tests for parquet-to-bronze field conversion logic."""

    def test_camel_case_rename(self) -> None:
        """Test snake_case fields are converted to camelCase."""
        from scripts.backfill_order_filled_from_parquet import _convert_record

        row = {
            "transaction_hash": "0xabc",
            "order_hash": "0xdef",
            "timestamp": 1700000000,
            "maker": "0xmaker",
            "taker": "0xtaker",
            "maker_asset_id": "123",
            "taker_asset_id": "456",
            "maker_amount_filled": 4.45,
            "taker_amount_filled": 2.0,
            "fee": 0.01,
        }

        result = _convert_record(row)

        assert "transactionHash" in result
        assert "orderHash" in result
        assert "makerAssetId" in result
        assert "takerAssetId" in result
        assert "makerAmountFilled" in result
        assert "takerAmountFilled" in result
        # No snake_case keys should remain
        for key in result:
            assert "_" not in key or key == "id"  # 'id' has no underscore

    def test_amount_scaling(self) -> None:
        """Test float amounts are scaled by 1e6 to match subgraph base units."""
        from scripts.backfill_order_filled_from_parquet import _convert_record

        row = {
            "transaction_hash": "0xabc",
            "timestamp": 1700000000,
            "maker": "0xmaker",
            "taker": "0xtaker",
            "maker_asset_id": "123",
            "taker_asset_id": "456",
            "maker_amount_filled": 4.45,
            "taker_amount_filled": 2.0,
            "fee": 0.01,
        }

        result = _convert_record(row)

        assert result["makerAmountFilled"] == 4450000
        assert result["takerAmountFilled"] == 2000000
        assert result["fee"] == 10000

    def test_timestamp_datetime_conversion(self) -> None:
        """Test datetime timestamps are converted to Unix epoch seconds."""
        from scripts.backfill_order_filled_from_parquet import _convert_record

        row = {
            "transaction_hash": "0xabc",
            "timestamp": datetime(2024, 1, 15, 12, 0, 0),
            "maker": "0xmaker",
            "taker": "0xtaker",
            "maker_asset_id": "123",
            "taker_asset_id": "456",
            "maker_amount_filled": 1.0,
            "taker_amount_filled": 1.0,
            "fee": 0.0,
        }

        result = _convert_record(row)

        assert isinstance(result["timestamp"], int)
        # 2024-01-15T12:00:00 UTC
        assert result["timestamp"] == 1705320000

    def test_timestamp_int_passthrough(self) -> None:
        """Test integer timestamps pass through unchanged."""
        from scripts.backfill_order_filled_from_parquet import _convert_record

        row = {
            "transaction_hash": "0xabc",
            "timestamp": 1700000000,
            "maker": "0xmaker",
            "taker": "0xtaker",
            "maker_asset_id": "123",
            "taker_asset_id": "456",
            "maker_amount_filled": 1.0,
            "taker_amount_filled": 1.0,
            "fee": 0.0,
        }

        result = _convert_record(row)
        assert result["timestamp"] == 1700000000

    def test_missing_fields_set_to_null(self) -> None:
        """Test that orderHash, fee, id are set to null when missing from source."""
        from scripts.backfill_order_filled_from_parquet import _convert_record

        # Simulate parquet row missing orderHash, fee
        row = {
            "transaction_hash": "0xabc",
            "timestamp": 1700000000,
            "maker": "0xmaker",
            "taker": "0xtaker",
            "maker_asset_id": "123",
            "taker_asset_id": "456",
            "maker_amount_filled": 1.0,
            "taker_amount_filled": 1.0,
        }

        result = _convert_record(row)

        assert result["orderHash"] is None
        assert result["fee"] is None
        assert result["id"] is None

    def test_none_values_preserved(self) -> None:
        """Test that None values in source are preserved as null."""
        from scripts.backfill_order_filled_from_parquet import _convert_record

        row = {
            "transaction_hash": None,
            "timestamp": 1700000000,
            "maker": "0xmaker",
            "taker": "0xtaker",
            "maker_asset_id": "123",
            "taker_asset_id": "456",
            "maker_amount_filled": 1.0,
            "taker_amount_filled": 1.0,
            "fee": 0.0,
        }

        result = _convert_record(row)
        assert result["transactionHash"] is None


class TestSchemaAlignment:
    """Validate that Goldsky-ingested and parquet-backfilled records share the same schema."""

    def test_goldsky_and_parquet_produce_same_keys(self) -> None:
        """Both sources should produce records with the same set of keys."""
        from scripts.backfill_order_filled_from_parquet import _convert_record

        # A Goldsky-sourced record (already camelCase)
        goldsky_record = {
            "id": "evt1",
            "transactionHash": "0xabc",
            "orderHash": "0xdef",
            "timestamp": "1700000000",
            "maker": "0xmaker",
            "taker": "0xtaker",
            "makerAssetId": "100",
            "takerAssetId": "200",
            "makerAmountFilled": "5000000",
            "takerAmountFilled": "3000000",
            "fee": "10000",
        }

        # A parquet-sourced record (converted)
        parquet_row = {
            "transaction_hash": "0xabc",
            "order_hash": "0xdef",
            "timestamp": 1700000000,
            "maker": "0xmaker",
            "taker": "0xtaker",
            "maker_asset_id": "100",
            "taker_asset_id": "200",
            "maker_amount_filled": 5.0,
            "taker_amount_filled": 3.0,
            "fee": 0.01,
        }
        parquet_record = _convert_record(parquet_row)

        goldsky_keys = set(goldsky_record.keys())
        parquet_keys = set(parquet_record.keys())
        assert goldsky_keys == parquet_keys, (
            f"Schema mismatch: goldsky has {goldsky_keys - parquet_keys}, "
            f"parquet has {parquet_keys - goldsky_keys}"
        )

    def test_parquet_missing_fields_documented(self) -> None:
        """Parquet source is missing orderHash, fee, id — these should be null."""
        from scripts.backfill_order_filled_from_parquet import _convert_record

        # Minimal parquet row (only fields actually present in parquet source)
        parquet_row = {
            "transaction_hash": "0xabc",
            "timestamp": 1700000000,
            "maker": "0xmaker",
            "taker": "0xtaker",
            "maker_asset_id": "100",
            "taker_asset_id": "200",
            "maker_amount_filled": 5.0,
            "taker_amount_filled": 3.0,
        }
        result = _convert_record(parquet_row)

        # These are the fields missing from parquet source
        assert result["orderHash"] is None
        assert result["fee"] is None
        assert result["id"] is None
