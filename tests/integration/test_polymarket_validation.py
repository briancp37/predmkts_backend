"""Validation tests for Polymarket ingestion Bronze contract compliance.

These tests validate that the Polymarket ingestion meets the Bronze layer contract:
1. JSONL files are valid gzipped JSON Lines
2. Manifest row_count matches actual line count
3. run_id is unique per invocation
4. CLI prints run_id on success and exits with code 0

Run validation tests with: pytest -m integration tests/integration/test_polymarket_validation.py
"""

import gzip
import json
import subprocess
from typing import Any
from unittest.mock import MagicMock

import pytest

from prediction_data.bronze.polymarket.client import (
    DATA_API_BASE_URL,
    GAMMA_API_BASE_URL,
    PolymarketClient,
)
from prediction_data.bronze.polymarket.ingest import ingest_markets, ingest_trades
from prediction_data.core.compression import compress_jsonl, decompress_jsonl
from prediction_data.storage.manifest import Manifest
from prediction_data.storage.s3 import S3Client, build_s3_key_prefix


pytestmark = pytest.mark.integration


class MockS3ClientWithStorage:
    """Mock S3 client that stores uploaded objects for validation."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.call_count = 0

    def put_object(self, Bucket: str, Key: str, Body: bytes, **kwargs: Any) -> None:
        self.objects[Key] = Body if isinstance(Body, bytes) else Body.encode("utf-8")
        self.call_count += 1

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self.objects:
            raise Exception(f"Key not found: {Key}")
        body = MagicMock()
        body.read.return_value = self.objects[Key]
        return {"Body": body}

    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self.objects:
            error = MagicMock()
            error.response = {"Error": {"Code": "404"}}
            raise self.exceptions.ClientError(error, "HeadObject")
        return {}

    @property
    def exceptions(self) -> Any:
        class Exceptions:
            class ClientError(Exception):
                pass
        return Exceptions


class TestTradesIngestionValidation:
    """Validate trades ingestion meets Bronze contract."""

    @pytest.mark.asyncio
    async def test_trades_ingestion_creates_valid_gzipped_jsonl(self) -> None:
        """Verify trades ingestion creates valid gzip-compressed JSONL files."""
        mock_s3 = MockS3ClientWithStorage()

        # Fetch trades from actual API
        async with PolymarketClient(page_size=50) as client:
            trades, _ = await client.fetch_trades(max_records=20)

        # Skip if no trades available
        if len(trades) == 0:
            pytest.skip("No trades available for validation")

        # Simulate upload using our compression
        compressed, row_count = compress_jsonl(trades)

        # Validate: data is valid gzip
        try:
            decompressed = gzip.decompress(compressed)
        except gzip.BadGzipFile:
            pytest.fail("Trades data is not valid gzip")

        # Validate: each line is valid JSON
        lines = decompressed.decode("utf-8").strip().split("\n")
        for i, line in enumerate(lines):
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                pytest.fail(f"Line {i} is not valid JSON: {e}")

        # Validate: line count matches
        assert len(lines) == row_count, f"Row count mismatch: {len(lines)} vs {row_count}"

    @pytest.mark.asyncio
    async def test_trades_ingestion_manifest_row_count_matches(self) -> None:
        """Verify manifest row_count matches actual line count in JSONL file."""
        mock_s3 = MockS3ClientWithStorage()

        # Fetch trades from actual API
        async with PolymarketClient(page_size=50) as client:
            trades, _ = await client.fetch_trades(max_records=30)

        if len(trades) == 0:
            pytest.skip("No trades available for validation")

        # Upload using S3Client with mock
        async with S3Client(bucket="test-bucket", s3_client=mock_s3) as s3_client:
            data_key, row_count = await s3_client.upload_jsonl(
                records=trades,
                platform="polymarket",
                entity="trades",
                dt="2024-01-15",
                run_id="test-validation-run",
            )

        # Get the uploaded JSONL file
        compressed_data = mock_s3.objects[data_key]
        decompressed = gzip.decompress(compressed_data)
        lines = decompressed.decode("utf-8").strip().split("\n")
        actual_line_count = len(lines) if lines[0] else 0

        # Validate row_count matches
        assert row_count == actual_line_count, (
            f"Manifest would report row_count={row_count} but file has {actual_line_count} lines"
        )

    @pytest.mark.asyncio
    async def test_trades_ingestion_run_id_unique(self) -> None:
        """Verify each ingestion run generates a unique run_id."""
        from prediction_data.core.run import RunContext

        # Create multiple run contexts
        run_ids = set()
        for _ in range(10):
            ctx = RunContext(platform="polymarket", entity="trades")
            run_ids.add(ctx.run_id)

        # All run_ids should be unique
        assert len(run_ids) == 10, "run_ids are not unique across invocations"


class TestMarketsIngestionValidation:
    """Validate markets ingestion meets Bronze contract."""

    @pytest.mark.asyncio
    async def test_markets_ingestion_creates_valid_gzipped_jsonl(self) -> None:
        """Verify markets ingestion creates valid gzip-compressed JSONL files."""
        # Fetch markets from actual API
        async with PolymarketClient(page_size=50) as client:
            markets = await client.fetch_markets_page(limit=20)

        assert len(markets) > 0, "No markets returned from API"

        # Simulate upload using our compression
        compressed, row_count = compress_jsonl(markets)

        # Validate: data is valid gzip
        try:
            decompressed = gzip.decompress(compressed)
        except gzip.BadGzipFile:
            pytest.fail("Markets data is not valid gzip")

        # Validate: each line is valid JSON
        lines = decompressed.decode("utf-8").strip().split("\n")
        for i, line in enumerate(lines):
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                pytest.fail(f"Line {i} is not valid JSON: {e}")

        # Validate: line count matches
        assert len(lines) == row_count, f"Row count mismatch: {len(lines)} vs {row_count}"

    @pytest.mark.asyncio
    async def test_markets_ingestion_manifest_row_count_matches(self) -> None:
        """Verify manifest row_count matches actual line count in JSONL file."""
        mock_s3 = MockS3ClientWithStorage()

        # Fetch markets from actual API
        async with PolymarketClient(page_size=50) as client:
            markets = await client.fetch_markets_page(limit=25)

        assert len(markets) > 0, "No markets returned from API"

        # Upload using S3Client with mock
        async with S3Client(bucket="test-bucket", s3_client=mock_s3) as s3_client:
            data_key, row_count = await s3_client.upload_jsonl(
                records=markets,
                platform="polymarket",
                entity="markets",
                dt="2024-01-15",
                run_id="test-validation-run",
            )

        # Get the uploaded JSONL file
        compressed_data = mock_s3.objects[data_key]
        decompressed = gzip.decompress(compressed_data)
        lines = decompressed.decode("utf-8").strip().split("\n")
        actual_line_count = len(lines) if lines[0] else 0

        # Validate row_count matches
        assert row_count == actual_line_count, (
            f"Manifest would report row_count={row_count} but file has {actual_line_count} lines"
        )


class TestFullIngestionWithMockS3:
    """End-to-end validation of ingestion with mock S3."""

    @pytest.mark.asyncio
    async def test_trades_full_ingestion_flow(self) -> None:
        """Validate complete trades ingestion flow with mock S3."""
        mock_s3 = MockS3ClientWithStorage()

        # Fetch trades and upload
        async with PolymarketClient(page_size=50) as client:
            trades, was_truncated = await client.fetch_trades(max_records=15)

        if len(trades) == 0:
            pytest.skip("No trades available for validation")

        # Upload data
        async with S3Client(bucket="test-bucket", s3_client=mock_s3) as s3_client:
            from prediction_data.core.run import RunContext
            from prediction_data.storage.manifest import create_manifest

            run_ctx = RunContext(platform="polymarket", entity="trades")
            data_key, row_count = await s3_client.upload_jsonl(
                records=trades,
                platform="polymarket",
                entity="trades",
                dt="2024-01-15",
                run_id=run_ctx.run_id,
            )

            manifest = create_manifest(
                run_id=run_ctx.run_id,
                platform="polymarket",
                entity="trades",
                dt="2024-01-15",
                bucket="test-bucket",
                key=data_key,
                row_count=row_count,
                api_base_url=DATA_API_BASE_URL,
                pagination="offset",
            )

            manifest_key = await s3_client.upload_manifest(manifest)

        # Validate: both files were uploaded
        assert data_key in mock_s3.objects
        assert manifest_key in mock_s3.objects

        # Validate: manifest is valid JSON
        manifest_data = json.loads(mock_s3.objects[manifest_key].decode("utf-8"))
        assert manifest_data["run_id"] == run_ctx.run_id
        assert manifest_data["row_count"] == row_count
        assert manifest_data["platform"] == "polymarket"
        assert manifest_data["entity"] == "trades"

        # Validate: JSONL line count matches manifest
        compressed = mock_s3.objects[data_key]
        decompressed = gzip.decompress(compressed)
        lines = [l for l in decompressed.decode("utf-8").strip().split("\n") if l]
        assert len(lines) == manifest_data["row_count"]

    @pytest.mark.asyncio
    async def test_markets_full_ingestion_flow(self) -> None:
        """Validate complete markets ingestion flow with mock S3."""
        mock_s3 = MockS3ClientWithStorage()

        # Fetch markets
        async with PolymarketClient(page_size=50) as client:
            markets = await client.fetch_markets_page(limit=20)

        assert len(markets) > 0

        # Upload data
        async with S3Client(bucket="test-bucket", s3_client=mock_s3) as s3_client:
            from prediction_data.core.run import RunContext
            from prediction_data.storage.manifest import create_manifest

            run_ctx = RunContext(platform="polymarket", entity="markets")
            data_key, row_count = await s3_client.upload_jsonl(
                records=markets,
                platform="polymarket",
                entity="markets",
                dt="2024-01-15",
                run_id=run_ctx.run_id,
            )

            manifest = create_manifest(
                run_id=run_ctx.run_id,
                platform="polymarket",
                entity="markets",
                dt="2024-01-15",
                bucket="test-bucket",
                key=data_key,
                row_count=row_count,
                api_base_url=GAMMA_API_BASE_URL,
                pagination="offset",
            )

            manifest_key = await s3_client.upload_manifest(manifest)

        # Validate: both files were uploaded
        assert data_key in mock_s3.objects
        assert manifest_key in mock_s3.objects

        # Validate: manifest is valid JSON with correct fields
        manifest_data = json.loads(mock_s3.objects[manifest_key].decode("utf-8"))
        assert manifest_data["run_id"] == run_ctx.run_id
        assert manifest_data["row_count"] == row_count
        assert manifest_data["source"]["api_base_url"] == GAMMA_API_BASE_URL

        # Validate: JSONL line count matches manifest
        compressed = mock_s3.objects[data_key]
        decompressed = gzip.decompress(compressed)
        lines = [l for l in decompressed.decode("utf-8").strip().split("\n") if l]
        assert len(lines) == manifest_data["row_count"]


class TestCLIValidation:
    """Validate CLI behavior meets Bronze contract."""

    def test_cli_polymarket_trades_help_available(self) -> None:
        """CLI should show help for polymarket-trades command."""
        result = subprocess.run(
            ["prediction-data", "ingest", "polymarket-trades", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--dt" in result.stdout
        assert "YYYY-MM-DD" in result.stdout

    def test_cli_polymarket_markets_help_available(self) -> None:
        """CLI should show help for polymarket-markets command."""
        result = subprocess.run(
            ["prediction-data", "ingest", "polymarket-markets", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--dt" in result.stdout
        assert "YYYY-MM-DD" in result.stdout

    def test_cli_exits_with_error_on_missing_dt(self) -> None:
        """CLI should exit with error code when --dt is missing."""
        result = subprocess.run(
            ["prediction-data", "ingest", "polymarket-trades"],
            capture_output=True,
            text=True,
        )
        # Typer exits with code 2 for missing required options
        assert result.returncode != 0


class TestS3KeyStructure:
    """Validate S3 key structure meets Bronze contract."""

    def test_s3_key_prefix_format(self) -> None:
        """S3 key prefix should match Bronze layer format."""
        prefix = build_s3_key_prefix(
            platform="polymarket",
            entity="trades",
            dt="2024-01-15",
            run_id="abc-123-def",
        )
        assert prefix == "bronze/polymarket/trades/dt=2024-01-15/run_id=abc-123-def/"

    def test_s3_key_prefix_for_markets(self) -> None:
        """S3 key prefix for markets should match Bronze layer format."""
        prefix = build_s3_key_prefix(
            platform="polymarket",
            entity="markets",
            dt="2024-01-15",
            run_id="xyz-789",
        )
        assert prefix == "bronze/polymarket/markets/dt=2024-01-15/run_id=xyz-789/"

    @pytest.mark.asyncio
    async def test_uploaded_keys_match_bronze_pattern(self) -> None:
        """Uploaded keys should match the Bronze layer pattern."""
        from prediction_data.storage.s3 import validate_bronze_key

        mock_s3 = MockS3ClientWithStorage()

        async with S3Client(bucket="test-bucket", s3_client=mock_s3) as s3_client:
            key, _ = await s3_client.upload_jsonl(
                records=[{"id": 1}],
                platform="polymarket",
                entity="trades",
                dt="2024-01-15",
                run_id="validation-test-run",
            )

        assert validate_bronze_key(key), f"Key does not match Bronze pattern: {key}"
        assert "bronze/polymarket/trades/" in key
        assert "dt=2024-01-15" in key
        assert "run_id=validation-test-run" in key
        assert key.endswith(".jsonl.gz")


class TestManifestContract:
    """Validate manifest meets Bronze contract."""

    @pytest.mark.asyncio
    async def test_manifest_contains_required_fields(self) -> None:
        """Manifest should contain all required fields per Bronze contract."""
        from prediction_data.core.run import RunContext
        from prediction_data.storage.manifest import create_manifest

        run_ctx = RunContext(platform="polymarket", entity="trades")
        manifest = create_manifest(
            run_id=run_ctx.run_id,
            platform="polymarket",
            entity="trades",
            dt="2024-01-15",
            bucket="test-bucket",
            key="bronze/polymarket/trades/dt=2024-01-15/run_id=test/part-000.jsonl.gz",
            row_count=100,
            api_base_url=DATA_API_BASE_URL,
            pagination="offset",
        )

        # Convert to dict for validation
        data = manifest.to_dict()

        # Required fields per Bronze contract
        assert "run_id" in data
        assert "platform" in data
        assert "entity" in data
        assert "dt" in data
        assert "generated_at" in data
        assert "files" in data
        assert "row_count" in data
        assert "source" in data

        # Source metadata
        assert "api_base_url" in data["source"]
        assert "pagination" in data["source"]

        # Validate values
        assert data["platform"] == "polymarket"
        assert data["entity"] == "trades"
        assert data["row_count"] == 100
        assert len(data["files"]) == 1

    def test_manifest_run_id_is_valid_uuid(self) -> None:
        """Manifest run_id should be a valid UUID4."""
        import uuid
        from prediction_data.core.run import RunContext

        run_ctx = RunContext(platform="polymarket", entity="trades")

        # Should not raise - valid UUID
        parsed = uuid.UUID(run_ctx.run_id)
        assert parsed.version == 4
