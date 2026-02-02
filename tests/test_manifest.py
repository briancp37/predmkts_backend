"""Tests for manifest schema and serialization."""

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from prediction_data.storage.manifest import (
    FileReference,
    Manifest,
    Source,
    create_manifest,
)


class TestFileReference:
    """Tests for FileReference model."""

    def test_creates_with_required_fields(self) -> None:
        """FileReference should be created with bucket and key."""
        ref = FileReference(bucket="my-bucket", key="path/to/file.jsonl.gz")
        assert ref.bucket == "my-bucket"
        assert ref.key == "path/to/file.jsonl.gz"

    def test_is_immutable(self) -> None:
        """FileReference should be immutable (frozen)."""
        ref = FileReference(bucket="my-bucket", key="path/to/file.jsonl.gz")
        with pytest.raises(ValidationError):
            ref.bucket = "other-bucket"  # type: ignore[misc]

    def test_rejects_empty_bucket(self) -> None:
        """FileReference should reject empty bucket."""
        with pytest.raises(ValidationError) as exc_info:
            FileReference(bucket="", key="path/to/file.jsonl.gz")
        assert "bucket" in str(exc_info.value)

    def test_rejects_empty_key(self) -> None:
        """FileReference should reject empty key."""
        with pytest.raises(ValidationError) as exc_info:
            FileReference(bucket="my-bucket", key="")
        assert "key" in str(exc_info.value)


class TestSource:
    """Tests for Source model."""

    def test_creates_with_required_fields(self) -> None:
        """Source should be created with api_base_url and pagination."""
        source = Source(api_base_url="https://api.example.com", pagination="cursor")
        assert source.api_base_url == "https://api.example.com"
        assert source.pagination == "cursor"
        assert source.cursor is None

    def test_creates_with_cursor(self) -> None:
        """Source should accept optional cursor."""
        source = Source(
            api_base_url="https://api.example.com",
            pagination="cursor",
            cursor="abc123",
        )
        assert source.cursor == "abc123"

    def test_snapshot_type_defaults_to_snapshot(self) -> None:
        """Source should default snapshot_type to 'snapshot'."""
        source = Source(api_base_url="https://api.example.com", pagination="offset")
        assert source.snapshot_type == "snapshot"

    def test_snapshot_type_delta(self) -> None:
        """Source should accept snapshot_type='delta'."""
        source = Source(
            api_base_url="https://api.example.com",
            pagination="offset",
            snapshot_type="delta",
        )
        assert source.snapshot_type == "delta"

    def test_snapshot_type_rejects_invalid(self) -> None:
        """Source should reject invalid snapshot_type values."""
        with pytest.raises(ValidationError):
            Source(
                api_base_url="https://api.example.com",
                pagination="offset",
                snapshot_type="invalid",  # type: ignore[arg-type]
            )

    def test_snapshot_type_backwards_compat_from_dict(self) -> None:
        """Source without snapshot_type in dict should default to 'snapshot'."""
        data = {"api_base_url": "https://api.example.com", "pagination": "offset"}
        source = Source.model_validate(data)
        assert source.snapshot_type == "snapshot"

    def test_is_immutable(self) -> None:
        """Source should be immutable (frozen)."""
        source = Source(api_base_url="https://api.example.com", pagination="cursor")
        with pytest.raises(ValidationError):
            source.pagination = "offset"  # type: ignore[misc]

    def test_rejects_empty_api_base_url(self) -> None:
        """Source should reject empty api_base_url."""
        with pytest.raises(ValidationError) as exc_info:
            Source(api_base_url="", pagination="cursor")
        assert "api_base_url" in str(exc_info.value)


class TestManifest:
    """Tests for Manifest model."""

    @pytest.fixture
    def valid_manifest_data(self) -> dict:
        """Create valid manifest data for testing."""
        return {
            "run_id": "abc-123-def-456",
            "platform": "polymarket",
            "entity": "markets",
            "dt": "2024-01-15",
            "generated_at": datetime(2024, 1, 15, 12, 30, 45, tzinfo=timezone.utc),
            "files": [
                {"bucket": "my-bucket", "key": "bronze/polymarket/markets/part-000.jsonl.gz"}
            ],
            "row_count": 1500,
            "source": {
                "api_base_url": "https://clob.polymarket.com",
                "pagination": "cursor",
                "cursor": "final-cursor-value",
            },
        }

    def test_creates_with_all_fields(self, valid_manifest_data: dict) -> None:
        """Manifest should be created with all required fields."""
        manifest = Manifest(**valid_manifest_data)
        assert manifest.run_id == "abc-123-def-456"
        assert manifest.platform == "polymarket"
        assert manifest.entity == "markets"
        assert manifest.dt == "2024-01-15"
        assert manifest.row_count == 1500
        assert len(manifest.files) == 1
        assert manifest.files[0].bucket == "my-bucket"
        assert manifest.source.api_base_url == "https://clob.polymarket.com"
        assert manifest.source.cursor == "final-cursor-value"

    def test_is_immutable(self, valid_manifest_data: dict) -> None:
        """Manifest should be immutable (frozen)."""
        manifest = Manifest(**valid_manifest_data)
        with pytest.raises(ValidationError):
            manifest.row_count = 2000  # type: ignore[misc]

    def test_rejects_invalid_dt_format(self, valid_manifest_data: dict) -> None:
        """Manifest should reject invalid date format."""
        valid_manifest_data["dt"] = "01-15-2024"  # Wrong format
        with pytest.raises(ValidationError) as exc_info:
            Manifest(**valid_manifest_data)
        assert "dt" in str(exc_info.value)

    def test_rejects_negative_row_count(self, valid_manifest_data: dict) -> None:
        """Manifest should reject negative row_count."""
        valid_manifest_data["row_count"] = -1
        with pytest.raises(ValidationError) as exc_info:
            Manifest(**valid_manifest_data)
        assert "row_count" in str(exc_info.value)

    def test_accepts_zero_row_count(self, valid_manifest_data: dict) -> None:
        """Manifest should accept zero row_count (empty ingestion)."""
        valid_manifest_data["row_count"] = 0
        manifest = Manifest(**valid_manifest_data)
        assert manifest.row_count == 0

    def test_rejects_empty_run_id(self, valid_manifest_data: dict) -> None:
        """Manifest should reject empty run_id."""
        valid_manifest_data["run_id"] = ""
        with pytest.raises(ValidationError) as exc_info:
            Manifest(**valid_manifest_data)
        assert "run_id" in str(exc_info.value)


class TestManifestTimezones:
    """Tests for manifest timezone handling."""

    def test_parses_iso8601_string(self) -> None:
        """Manifest should parse ISO-8601 datetime strings."""
        manifest = Manifest(
            run_id="test-run",
            platform="polymarket",
            entity="markets",
            dt="2024-01-15",
            generated_at="2024-01-15T12:30:45+00:00",
            files=[FileReference(bucket="bucket", key="key")],
            row_count=100,
            source=Source(api_base_url="https://api.example.com", pagination="none"),
        )
        assert manifest.generated_at == datetime(2024, 1, 15, 12, 30, 45, tzinfo=timezone.utc)

    def test_parses_z_suffix(self) -> None:
        """Manifest should parse Z suffix for UTC."""
        manifest = Manifest(
            run_id="test-run",
            platform="polymarket",
            entity="markets",
            dt="2024-01-15",
            generated_at="2024-01-15T12:30:45Z",
            files=[FileReference(bucket="bucket", key="key")],
            row_count=100,
            source=Source(api_base_url="https://api.example.com", pagination="none"),
        )
        assert manifest.generated_at.tzinfo is not None

    def test_adds_utc_to_naive_datetime(self) -> None:
        """Manifest should add UTC timezone to naive datetime."""
        naive_dt = datetime(2024, 1, 15, 12, 30, 45)
        manifest = Manifest(
            run_id="test-run",
            platform="polymarket",
            entity="markets",
            dt="2024-01-15",
            generated_at=naive_dt,
            files=[FileReference(bucket="bucket", key="key")],
            row_count=100,
            source=Source(api_base_url="https://api.example.com", pagination="none"),
        )
        assert manifest.generated_at.tzinfo == timezone.utc


class TestManifestSerialization:
    """Tests for manifest JSON serialization."""

    @pytest.fixture
    def manifest(self) -> Manifest:
        """Create a manifest for serialization tests."""
        return Manifest(
            run_id="abc-123-def-456",
            platform="polymarket",
            entity="markets",
            dt="2024-01-15",
            generated_at=datetime(2024, 1, 15, 12, 30, 45, tzinfo=timezone.utc),
            files=[
                FileReference(bucket="my-bucket", key="bronze/polymarket/markets/part-000.jsonl.gz")
            ],
            row_count=1500,
            source=Source(
                api_base_url="https://clob.polymarket.com",
                pagination="cursor",
                cursor="final-cursor-value",
            ),
        )

    def test_to_json_produces_valid_json(self, manifest: Manifest) -> None:
        """to_json should produce valid JSON."""
        json_str = manifest.to_json()
        data = json.loads(json_str)
        assert data["run_id"] == "abc-123-def-456"
        assert data["platform"] == "polymarket"

    def test_to_json_uses_iso8601_timestamps(self, manifest: Manifest) -> None:
        """to_json should format timestamps as ISO-8601."""
        json_str = manifest.to_json()
        data = json.loads(json_str)
        # Should be ISO-8601 format with timezone
        assert "2024-01-15T12:30:45" in data["generated_at"]

    def test_to_dict_returns_serializable_dict(self, manifest: Manifest) -> None:
        """to_dict should return a JSON-serializable dictionary."""
        data = manifest.to_dict()
        # Should not raise
        json.dumps(data)
        assert data["run_id"] == "abc-123-def-456"

    def test_from_json_parses_valid_json(self, manifest: Manifest) -> None:
        """from_json should parse valid JSON."""
        json_str = manifest.to_json()
        loaded = Manifest.from_json(json_str)
        assert loaded.run_id == manifest.run_id
        assert loaded.platform == manifest.platform
        assert loaded.generated_at == manifest.generated_at

    def test_from_json_rejects_invalid_json(self) -> None:
        """from_json should reject invalid JSON."""
        with pytest.raises(ValidationError):
            Manifest.from_json('{"invalid": "manifest"}')

    def test_from_dict_validates_data(self) -> None:
        """from_dict should validate input data."""
        data = {
            "run_id": "test-run",
            "platform": "polymarket",
            "entity": "markets",
            "dt": "2024-01-15",
            "generated_at": "2024-01-15T12:30:45Z",
            "files": [{"bucket": "bucket", "key": "key"}],
            "row_count": 100,
            "source": {"api_base_url": "https://api.example.com", "pagination": "none"},
        }
        manifest = Manifest.from_dict(data)
        assert manifest.run_id == "test-run"

    def test_roundtrip_serialization(self, manifest: Manifest) -> None:
        """Manifest should survive JSON roundtrip."""
        json_str = manifest.to_json()
        loaded = Manifest.from_json(json_str)
        assert loaded.run_id == manifest.run_id
        assert loaded.platform == manifest.platform
        assert loaded.entity == manifest.entity
        assert loaded.dt == manifest.dt
        assert loaded.generated_at == manifest.generated_at
        assert loaded.row_count == manifest.row_count
        assert loaded.files == manifest.files
        assert loaded.source == manifest.source


class TestCreateManifest:
    """Tests for create_manifest helper function."""

    def test_creates_manifest_with_single_file(self) -> None:
        """create_manifest should create manifest with single file."""
        manifest = create_manifest(
            run_id="test-run-123",
            platform="kalshi",
            entity="trades",
            dt="2024-06-30",
            bucket="data-bucket",
            key="bronze/kalshi/trades/part-000.jsonl.gz",
            row_count=5000,
            api_base_url="https://api.kalshi.com",
            pagination="offset",
        )
        assert manifest.run_id == "test-run-123"
        assert manifest.platform == "kalshi"
        assert manifest.entity == "trades"
        assert manifest.dt == "2024-06-30"
        assert manifest.row_count == 5000
        assert len(manifest.files) == 1
        assert manifest.files[0].bucket == "data-bucket"
        assert manifest.files[0].key == "bronze/kalshi/trades/part-000.jsonl.gz"
        assert manifest.source.api_base_url == "https://api.kalshi.com"
        assert manifest.source.pagination == "offset"
        assert manifest.source.cursor is None

    def test_creates_manifest_with_cursor(self) -> None:
        """create_manifest should accept cursor parameter."""
        manifest = create_manifest(
            run_id="test-run-456",
            platform="polymarket",
            entity="markets",
            dt="2024-01-15",
            bucket="data-bucket",
            key="bronze/polymarket/markets/part-000.jsonl.gz",
            row_count=1500,
            api_base_url="https://clob.polymarket.com",
            pagination="cursor",
            cursor="final-cursor-xyz",
        )
        assert manifest.source.cursor == "final-cursor-xyz"

    def test_auto_generates_timestamp(self) -> None:
        """create_manifest should auto-generate generated_at timestamp."""
        before = datetime.now(timezone.utc)
        manifest = create_manifest(
            run_id="test-run",
            platform="polymarket",
            entity="markets",
            dt="2024-01-15",
            bucket="bucket",
            key="key",
            row_count=100,
            api_base_url="https://api.example.com",
        )
        after = datetime.now(timezone.utc)
        assert before <= manifest.generated_at <= after

    def test_accepts_custom_timestamp(self) -> None:
        """create_manifest should accept custom generated_at timestamp."""
        custom_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        manifest = create_manifest(
            run_id="test-run",
            platform="polymarket",
            entity="markets",
            dt="2024-01-15",
            bucket="bucket",
            key="key",
            row_count=100,
            api_base_url="https://api.example.com",
            generated_at=custom_time,
        )
        assert manifest.generated_at == custom_time

    def test_creates_manifest_with_snapshot_type_delta(self) -> None:
        """create_manifest should accept snapshot_type='delta'."""
        manifest = create_manifest(
            run_id="test-run-delta",
            platform="polymarket",
            entity="markets",
            dt="2024-01-15",
            bucket="bucket",
            key="key",
            row_count=50,
            api_base_url="https://gamma-api.polymarket.com",
            pagination="offset",
            snapshot_type="delta",
        )
        assert manifest.source.snapshot_type == "delta"

    def test_creates_manifest_defaults_snapshot_type_to_snapshot(self) -> None:
        """create_manifest should default snapshot_type to 'snapshot'."""
        manifest = create_manifest(
            run_id="test-run",
            platform="polymarket",
            entity="markets",
            dt="2024-01-15",
            bucket="bucket",
            key="key",
            row_count=100,
            api_base_url="https://api.example.com",
        )
        assert manifest.source.snapshot_type == "snapshot"

    def test_defaults_pagination_to_none(self) -> None:
        """create_manifest should default pagination to 'none'."""
        manifest = create_manifest(
            run_id="test-run",
            platform="polymarket",
            entity="markets",
            dt="2024-01-15",
            bucket="bucket",
            key="key",
            row_count=100,
            api_base_url="https://api.example.com",
        )
        assert manifest.source.pagination == "none"


class TestManifestMultipleFiles:
    """Tests for manifests with multiple files."""

    def test_accepts_multiple_files(self) -> None:
        """Manifest should accept multiple file references."""
        manifest = Manifest(
            run_id="test-run",
            platform="polymarket",
            entity="markets",
            dt="2024-01-15",
            generated_at=datetime.now(timezone.utc),
            files=[
                FileReference(bucket="bucket", key="part-000.jsonl.gz"),
                FileReference(bucket="bucket", key="part-001.jsonl.gz"),
                FileReference(bucket="bucket", key="part-002.jsonl.gz"),
            ],
            row_count=15000,
            source=Source(api_base_url="https://api.example.com", pagination="none"),
        )
        assert len(manifest.files) == 3

    def test_accepts_empty_files_list(self) -> None:
        """Manifest should accept empty files list (for failed runs)."""
        manifest = Manifest(
            run_id="test-run",
            platform="polymarket",
            entity="markets",
            dt="2024-01-15",
            generated_at=datetime.now(timezone.utc),
            files=[],
            row_count=0,
            source=Source(api_base_url="https://api.example.com", pagination="none"),
        )
        assert len(manifest.files) == 0
        assert manifest.row_count == 0
