"""Tests for S3 storage layer."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from prediction_data.core.compression import decompress_jsonl
from prediction_data.storage.manifest import Manifest, FileReference, Source
from prediction_data.storage.s3 import (
    BRONZE_KEY_PATTERN,
    BRONZE_KEY_PREFIX_PATTERN,
    S3Client,
    build_s3_key_prefix,
    validate_bronze_key,
    validate_bronze_key_prefix,
)


class TestBuildS3KeyPrefix:
    """Tests for build_s3_key_prefix function."""

    def test_builds_correct_prefix(self) -> None:
        """Key prefix follows Bronze layout format."""
        prefix = build_s3_key_prefix(
            platform="polymarket",
            entity="markets",
            dt="2024-01-15",
            run_id="abc-123-def",
        )
        assert prefix == "bronze/polymarket/markets/dt=2024-01-15/run_id=abc-123-def/"

    def test_different_platforms(self) -> None:
        """Different platforms produce different prefixes."""
        polymarket = build_s3_key_prefix("polymarket", "markets", "2024-01-15", "run-1")
        kalshi = build_s3_key_prefix("kalshi", "markets", "2024-01-15", "run-1")
        assert polymarket != kalshi
        assert "polymarket" in polymarket
        assert "kalshi" in kalshi

    def test_different_entities(self) -> None:
        """Different entities produce different prefixes."""
        markets = build_s3_key_prefix("polymarket", "markets", "2024-01-15", "run-1")
        trades = build_s3_key_prefix("polymarket", "trades", "2024-01-15", "run-1")
        assert markets != trades
        assert "/markets/" in markets
        assert "/trades/" in trades

    def test_date_in_prefix(self) -> None:
        """Date is included in partition format."""
        prefix = build_s3_key_prefix("polymarket", "markets", "2024-03-20", "run-1")
        assert "dt=2024-03-20" in prefix


class TestValidateBronzeKeyPrefix:
    """Tests for validate_bronze_key_prefix function."""

    def test_valid_prefix(self) -> None:
        """Valid prefixes pass validation."""
        valid_prefixes = [
            "bronze/polymarket/markets/dt=2024-01-15/run_id=abc-def-123/",
            "bronze/kalshi/trades/dt=2023-12-31/run_id=a1b2c3d4-e5f6-7890-abcd-ef1234567890/",
            "bronze/platform_1/entity-2/dt=2024-06-01/run_id=123-456/",
        ]
        for prefix in valid_prefixes:
            assert validate_bronze_key_prefix(prefix), f"Should be valid: {prefix}"

    def test_invalid_prefix_missing_bronze(self) -> None:
        """Prefix must start with bronze/."""
        assert not validate_bronze_key_prefix("silver/polymarket/markets/dt=2024-01-15/run_id=abc/")

    def test_invalid_prefix_missing_trailing_slash(self) -> None:
        """Prefix must end with trailing slash."""
        assert not validate_bronze_key_prefix("bronze/polymarket/markets/dt=2024-01-15/run_id=abc")

    def test_invalid_prefix_bad_date_format(self) -> None:
        """Date must be in YYYY-MM-DD format."""
        assert not validate_bronze_key_prefix("bronze/polymarket/markets/dt=2024-1-15/run_id=abc/")
        assert not validate_bronze_key_prefix("bronze/polymarket/markets/dt=24-01-15/run_id=abc/")

    def test_invalid_prefix_uppercase(self) -> None:
        """Platform/entity must be lowercase."""
        assert not validate_bronze_key_prefix("bronze/Polymarket/markets/dt=2024-01-15/run_id=abc/")


class TestValidateBronzeKey:
    """Tests for validate_bronze_key function."""

    def test_valid_keys(self) -> None:
        """Valid full keys pass validation."""
        valid_keys = [
            "bronze/polymarket/markets/dt=2024-01-15/run_id=abc-def/part-000.jsonl.gz",
            "bronze/kalshi/trades/dt=2023-12-31/run_id=123-456/manifest.json",
            "bronze/platform/entity/dt=2024-06-01/run_id=a1b2c3/data.csv",
        ]
        for key in valid_keys:
            assert validate_bronze_key(key), f"Should be valid: {key}"

    def test_invalid_key_with_trailing_slash(self) -> None:
        """Full keys must not end with slash."""
        assert not validate_bronze_key("bronze/polymarket/markets/dt=2024-01-15/run_id=abc/")

    def test_invalid_key_extra_directories(self) -> None:
        """Keys should not have extra directories after run_id."""
        assert not validate_bronze_key(
            "bronze/polymarket/markets/dt=2024-01-15/run_id=abc/extra/file.json"
        )


class TestBronzeKeyPatterns:
    """Tests for the regex patterns."""

    def test_prefix_pattern_matches_valid(self) -> None:
        """Prefix pattern matches valid prefixes."""
        assert BRONZE_KEY_PREFIX_PATTERN.match(
            "bronze/polymarket/markets/dt=2024-01-15/run_id=abc-123/"
        )

    def test_key_pattern_matches_valid(self) -> None:
        """Key pattern matches valid keys."""
        assert BRONZE_KEY_PATTERN.match(
            "bronze/polymarket/markets/dt=2024-01-15/run_id=abc-123/part-000.jsonl.gz"
        )


class TestS3Client:
    """Tests for S3Client class."""

    @pytest.fixture
    def mock_s3(self) -> MagicMock:
        """Create a mock S3 client."""
        mock = MagicMock()
        mock.exceptions = MagicMock()
        mock.exceptions.ClientError = Exception
        return mock

    @pytest.fixture
    def s3_client(self, mock_s3: MagicMock) -> S3Client:
        """Create an S3Client with mock boto3 client."""
        return S3Client(bucket="test-bucket", s3_client=mock_s3)

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_s3: MagicMock) -> None:
        """S3Client works as async context manager."""
        async with S3Client(bucket="test-bucket", s3_client=mock_s3) as client:
            assert client.bucket == "test-bucket"

    @pytest.mark.asyncio
    async def test_upload_jsonl_basic(
        self, s3_client: S3Client, mock_s3: MagicMock
    ) -> None:
        """upload_jsonl uploads compressed JSONL to correct key."""
        records = [{"id": 1, "name": "test"}, {"id": 2, "name": "test2"}]

        key, row_count = await s3_client.upload_jsonl(
            records,
            platform="polymarket",
            entity="markets",
            dt="2024-01-15",
            run_id="abc-123",
        )

        assert key == "bronze/polymarket/markets/dt=2024-01-15/run_id=abc-123/part-000.jsonl.gz"
        assert row_count == 2

        # Verify put_object was called
        mock_s3.put_object.assert_called_once()
        call_args = mock_s3.put_object.call_args
        assert call_args.kwargs["Bucket"] == "test-bucket"
        assert call_args.kwargs["Key"] == key
        assert call_args.kwargs["ContentType"] == "application/gzip"

        # Verify the data can be decompressed
        uploaded_data = call_args.kwargs["Body"]
        decompressed = decompress_jsonl(uploaded_data)
        assert decompressed == records

    @pytest.mark.asyncio
    async def test_upload_jsonl_with_part_number(
        self, s3_client: S3Client, mock_s3: MagicMock
    ) -> None:
        """upload_jsonl respects part_number parameter."""
        key, _ = await s3_client.upload_jsonl(
            [{"id": 1}],
            platform="polymarket",
            entity="markets",
            dt="2024-01-15",
            run_id="abc-123",
            part_number=5,
        )

        assert "part-005.jsonl.gz" in key

    @pytest.mark.asyncio
    async def test_upload_jsonl_empty_records(
        self, s3_client: S3Client, mock_s3: MagicMock
    ) -> None:
        """upload_jsonl handles empty records."""
        key, row_count = await s3_client.upload_jsonl(
            [],
            platform="polymarket",
            entity="markets",
            dt="2024-01-15",
            run_id="abc-123",
        )

        assert row_count == 0
        mock_s3.put_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_jsonl_invalid_platform(self, s3_client: S3Client) -> None:
        """upload_jsonl rejects invalid platform names."""
        with pytest.raises(ValueError, match="Invalid Bronze key"):
            await s3_client.upload_jsonl(
                [{"id": 1}],
                platform="INVALID",  # uppercase not allowed
                entity="markets",
                dt="2024-01-15",
                run_id="abc-123",
            )

    @pytest.mark.asyncio
    async def test_upload_manifest_basic(
        self, s3_client: S3Client, mock_s3: MagicMock
    ) -> None:
        """upload_manifest uploads manifest to correct key."""
        manifest = Manifest(
            run_id="abc-123",
            platform="polymarket",
            entity="markets",
            dt="2024-01-15",
            generated_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            files=[FileReference(bucket="test-bucket", key="bronze/polymarket/markets/dt=2024-01-15/run_id=abc-123/part-000.jsonl.gz")],
            row_count=100,
            source=Source(api_base_url="https://api.example.com", pagination="cursor"),
        )

        key = await s3_client.upload_manifest(manifest)

        assert key == "bronze/polymarket/markets/dt=2024-01-15/run_id=abc-123/manifest.json"

        # Verify put_object was called
        mock_s3.put_object.assert_called_once()
        call_args = mock_s3.put_object.call_args
        assert call_args.kwargs["Bucket"] == "test-bucket"
        assert call_args.kwargs["Key"] == key
        assert call_args.kwargs["ContentType"] == "application/json"

        # Verify the manifest content
        uploaded_data = call_args.kwargs["Body"]
        parsed = json.loads(uploaded_data.decode("utf-8"))
        assert parsed["run_id"] == "abc-123"
        assert parsed["row_count"] == 100

    @pytest.mark.asyncio
    async def test_download_manifest(
        self, s3_client: S3Client, mock_s3: MagicMock
    ) -> None:
        """download_manifest retrieves and parses manifest."""
        manifest_data = {
            "run_id": "abc-123",
            "platform": "polymarket",
            "entity": "markets",
            "dt": "2024-01-15",
            "generated_at": "2024-01-15T12:00:00+00:00",
            "files": [{"bucket": "test-bucket", "key": "test-key"}],
            "row_count": 50,
            "source": {"api_base_url": "https://api.example.com", "pagination": "none"},
        }

        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(manifest_data).encode("utf-8")
        mock_s3.get_object.return_value = {"Body": mock_body}

        manifest = await s3_client.download_manifest("some/key/manifest.json")

        assert manifest.run_id == "abc-123"
        assert manifest.platform == "polymarket"
        assert manifest.row_count == 50
        mock_s3.get_object.assert_called_once_with(
            Bucket="test-bucket", Key="some/key/manifest.json"
        )

    @pytest.mark.asyncio
    async def test_download_jsonl(
        self, s3_client: S3Client, mock_s3: MagicMock
    ) -> None:
        """download_jsonl retrieves and decompresses JSONL."""
        from prediction_data.core.compression import compress_jsonl

        original_records = [{"id": 1}, {"id": 2}, {"id": 3}]
        compressed_data, _ = compress_jsonl(original_records)

        mock_body = MagicMock()
        mock_body.read.return_value = compressed_data
        mock_s3.get_object.return_value = {"Body": mock_body}

        records = await s3_client.download_jsonl("some/key/data.jsonl.gz")

        assert records == original_records
        mock_s3.get_object.assert_called_once_with(
            Bucket="test-bucket", Key="some/key/data.jsonl.gz"
        )

    @pytest.mark.asyncio
    async def test_list_keys(self, s3_client: S3Client, mock_s3: MagicMock) -> None:
        """list_keys returns all keys under prefix."""
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"Contents": [{"Key": "prefix/file1.json"}, {"Key": "prefix/file2.json"}]},
            {"Contents": [{"Key": "prefix/file3.json"}]},
        ]
        mock_s3.get_paginator.return_value = mock_paginator

        keys = await s3_client.list_keys("prefix/")

        assert keys == ["prefix/file1.json", "prefix/file2.json", "prefix/file3.json"]
        mock_s3.get_paginator.assert_called_once_with("list_objects_v2")
        mock_paginator.paginate.assert_called_once_with(Bucket="test-bucket", Prefix="prefix/")

    @pytest.mark.asyncio
    async def test_list_keys_empty(self, s3_client: S3Client, mock_s3: MagicMock) -> None:
        """list_keys handles empty results."""
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{}]  # No Contents key
        mock_s3.get_paginator.return_value = mock_paginator

        keys = await s3_client.list_keys("prefix/")

        assert keys == []

    @pytest.mark.asyncio
    async def test_key_exists_true(
        self, s3_client: S3Client, mock_s3: MagicMock
    ) -> None:
        """key_exists returns True when key exists."""
        mock_s3.head_object.return_value = {"ContentLength": 100}

        exists = await s3_client.key_exists("some/key")

        assert exists is True
        mock_s3.head_object.assert_called_once_with(Bucket="test-bucket", Key="some/key")

    @pytest.mark.asyncio
    async def test_key_exists_false(
        self, s3_client: S3Client, mock_s3: MagicMock
    ) -> None:
        """key_exists returns False when key doesn't exist."""
        mock_s3.head_object.side_effect = mock_s3.exceptions.ClientError

        exists = await s3_client.key_exists("some/key")

        assert exists is False

    @pytest.mark.asyncio
    async def test_bucket_property(self, s3_client: S3Client) -> None:
        """bucket property returns the bucket name."""
        assert s3_client.bucket == "test-bucket"


class TestS3ClientInitialization:
    """Tests for S3Client initialization."""

    def test_init_with_bucket(self) -> None:
        """S3Client can be created with just bucket name."""
        client = S3Client(bucket="my-bucket")
        assert client.bucket == "my-bucket"

    def test_init_with_region(self) -> None:
        """S3Client can be created with region name."""
        client = S3Client(bucket="my-bucket", region_name="us-west-2")
        assert client.bucket == "my-bucket"

    @pytest.mark.asyncio
    async def test_creates_boto3_client_on_entry(self) -> None:
        """S3Client creates boto3 client when entering context."""
        with patch("prediction_data.storage.s3.boto3") as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.client.return_value = mock_client

            async with S3Client(bucket="my-bucket", region_name="us-east-1") as client:
                # Client should be created
                mock_boto3.client.assert_called_once_with("s3", region_name="us-east-1")

    @pytest.mark.asyncio
    async def test_uses_provided_client(self) -> None:
        """S3Client uses provided boto3 client instead of creating new one."""
        provided_client = MagicMock()

        with patch("prediction_data.storage.s3.boto3") as mock_boto3:
            async with S3Client(bucket="my-bucket", s3_client=provided_client):
                # Should not create a new client
                mock_boto3.client.assert_not_called()


class TestS3ClientIntegration:
    """Integration-style tests for S3Client workflows."""

    @pytest.fixture
    def mock_s3(self) -> MagicMock:
        """Create a mock S3 client with full functionality."""
        mock = MagicMock()
        mock.exceptions = MagicMock()
        mock.exceptions.ClientError = Exception
        return mock

    @pytest.mark.asyncio
    async def test_full_upload_workflow(self, mock_s3: MagicMock) -> None:
        """Test complete upload workflow: records then manifest."""
        async with S3Client(bucket="data-lake", s3_client=mock_s3) as client:
            # Upload records
            records = [
                {"market_id": "1", "title": "Election 2024"},
                {"market_id": "2", "title": "Fed Rate Decision"},
            ]

            data_key, row_count = await client.upload_jsonl(
                records,
                platform="polymarket",
                entity="markets",
                dt="2024-01-15",
                run_id="run-abc-123",
            )

            assert row_count == 2
            assert data_key.endswith("part-000.jsonl.gz")

            # Create and upload manifest
            manifest = Manifest(
                run_id="run-abc-123",
                platform="polymarket",
                entity="markets",
                dt="2024-01-15",
                generated_at=datetime.now(timezone.utc),
                files=[FileReference(bucket="data-lake", key=data_key)],
                row_count=row_count,
                source=Source(
                    api_base_url="https://gamma-api.polymarket.com",
                    pagination="cursor",
                    cursor="final-cursor-value",
                ),
            )

            manifest_key = await client.upload_manifest(manifest)

            assert manifest_key.endswith("manifest.json")
            assert mock_s3.put_object.call_count == 2

    @pytest.mark.asyncio
    async def test_multiple_parts_upload(self, mock_s3: MagicMock) -> None:
        """Test uploading multiple parts."""
        async with S3Client(bucket="data-lake", s3_client=mock_s3) as client:
            keys = []
            total_rows = 0

            for part_num in range(3):
                records = [{"id": i, "part": part_num} for i in range(10)]
                key, row_count = await client.upload_jsonl(
                    records,
                    platform="polymarket",
                    entity="trades",
                    dt="2024-01-15",
                    run_id="run-xyz",
                    part_number=part_num,
                )
                keys.append(key)
                total_rows += row_count

            assert len(keys) == 3
            assert total_rows == 30
            assert "part-000" in keys[0]
            assert "part-001" in keys[1]
            assert "part-002" in keys[2]
