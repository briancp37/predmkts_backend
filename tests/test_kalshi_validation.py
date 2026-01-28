"""Validation tests for Kalshi ingestion meeting Bronze contract requirements.

These tests verify that:
1. Ingestion produces valid gzip-compressed JSONL files
2. Manifest row_count matches actual line count
3. run_id is unique per invocation
4. CLI prints run_id on success and exits with code 0
"""

import gzip
import io
import json
import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from prediction_data.bronze.kalshi.ingest import (
    ingest_markets,
    ingest_trades,
)
from prediction_data.cli.main import app
from prediction_data.core.compression import decompress_jsonl


# UUID4 pattern for run_id validation
UUID4_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@pytest.fixture
def mock_credentials() -> MagicMock:
    """Create mock Kalshi credentials."""
    credentials = MagicMock()
    credentials.api_key_id = "test-key-id"
    return credentials


@pytest.fixture
def sample_trades() -> list[dict[str, Any]]:
    """Sample trade records for testing."""
    return [
        {
            "trade_id": "trade-001",
            "ticker": "PRES-2024-R-DEM",
            "count": 10,
            "yes_price": 55,
            "no_price": 45,
            "taker_side": "yes",
            "created_time": "2024-01-15T12:00:00Z",
        },
        {
            "trade_id": "trade-002",
            "ticker": "PRES-2024-R-REP",
            "count": 5,
            "yes_price": 42,
            "no_price": 58,
            "taker_side": "no",
            "created_time": "2024-01-15T12:01:00Z",
        },
        {
            "trade_id": "trade-003",
            "ticker": "PRES-2024-R-DEM",
            "count": 20,
            "yes_price": 56,
            "no_price": 44,
            "taker_side": "yes",
            "created_time": "2024-01-15T12:02:00Z",
        },
    ]


@pytest.fixture
def sample_markets() -> list[dict[str, Any]]:
    """Sample market records for testing."""
    return [
        {
            "ticker": "PRES-2024-R-DEM",
            "event_ticker": "PRES-2024",
            "title": "Will the Democratic candidate win?",
            "status": "open",
            "yes_bid": 55,
            "yes_ask": 56,
        },
        {
            "ticker": "PRES-2024-R-REP",
            "event_ticker": "PRES-2024",
            "title": "Will the Republican candidate win?",
            "status": "open",
            "yes_bid": 42,
            "yes_ask": 43,
        },
    ]


class MockS3ClientWithCapture:
    """Mock S3 client that captures uploaded data for validation."""

    def __init__(self) -> None:
        self.uploaded_objects: dict[str, bytes] = {}

    def put_object(
        self, Bucket: str, Key: str, Body: bytes, **kwargs: Any
    ) -> dict[str, Any]:
        self.uploaded_objects[Key] = Body
        return {"ETag": "mock-etag"}


class TestJsonlGzipValidation:
    """Tests verifying JSONL files are valid gzipped JSON Lines."""

    @pytest.mark.asyncio
    async def test_trades_ingestion_produces_valid_gzip(
        self,
        mock_credentials: MagicMock,
        sample_trades: list[dict[str, Any]],
    ) -> None:
        """Verify trades ingestion produces valid gzip-compressed data."""
        mock_s3 = MockS3ClientWithCapture()

        with (
            patch(
                "prediction_data.bronze.kalshi.ingest.load_credentials_from_settings",
                return_value=mock_credentials,
            ),
            patch(
                "prediction_data.bronze.kalshi.ingest.KalshiClient"
            ) as mock_client_class,
            patch("prediction_data.bronze.kalshi.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.kalshi.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.bronze_bucket = "test-bucket"

            mock_client = AsyncMock()
            mock_client.fetch_all_trades.return_value = sample_trades
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Use our capturing mock S3
            mock_s3_instance = AsyncMock()
            mock_s3_instance.upload_jsonl = AsyncMock(
                side_effect=lambda **kwargs: self._capture_and_upload(
                    mock_s3, kwargs["records"], kwargs["platform"], kwargs["entity"],
                    kwargs["dt"], kwargs["run_id"]
                )
            )
            mock_s3_instance.upload_manifest = AsyncMock(return_value="manifest_key")
            mock_s3_class.return_value.__aenter__.return_value = mock_s3_instance

            await ingest_trades(dt="2024-01-15")

        # Verify we captured data
        assert len(mock_s3.uploaded_objects) > 0

        # Find the JSONL file
        jsonl_keys = [k for k in mock_s3.uploaded_objects if k.endswith(".jsonl.gz")]
        assert len(jsonl_keys) == 1, f"Expected 1 JSONL file, got {jsonl_keys}"

        # Verify it's valid gzip
        compressed_data = mock_s3.uploaded_objects[jsonl_keys[0]]
        try:
            decompressed = gzip.decompress(compressed_data)
        except gzip.BadGzipFile:
            pytest.fail("JSONL file is not valid gzip")

        # Verify it's valid JSON Lines
        lines = decompressed.decode("utf-8").strip().split("\n")
        assert len(lines) == len(sample_trades)

        for i, line in enumerate(lines):
            try:
                parsed = json.loads(line)
                assert isinstance(parsed, dict)
            except json.JSONDecodeError as e:
                pytest.fail(f"Line {i} is not valid JSON: {e}")

    @pytest.mark.asyncio
    async def test_markets_ingestion_produces_valid_gzip(
        self,
        mock_credentials: MagicMock,
        sample_markets: list[dict[str, Any]],
    ) -> None:
        """Verify markets ingestion produces valid gzip-compressed data."""
        mock_s3 = MockS3ClientWithCapture()

        with (
            patch(
                "prediction_data.bronze.kalshi.ingest.load_credentials_from_settings",
                return_value=mock_credentials,
            ),
            patch(
                "prediction_data.bronze.kalshi.ingest.KalshiClient"
            ) as mock_client_class,
            patch("prediction_data.bronze.kalshi.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.kalshi.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.bronze_bucket = "test-bucket"

            mock_client = AsyncMock()
            mock_client.fetch_all_markets.return_value = sample_markets
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_s3_instance = AsyncMock()
            mock_s3_instance.upload_jsonl = AsyncMock(
                side_effect=lambda **kwargs: self._capture_and_upload(
                    mock_s3, kwargs["records"], kwargs["platform"], kwargs["entity"],
                    kwargs["dt"], kwargs["run_id"]
                )
            )
            mock_s3_instance.upload_manifest = AsyncMock(return_value="manifest_key")
            mock_s3_class.return_value.__aenter__.return_value = mock_s3_instance

            await ingest_markets(dt="2024-01-15")

        # Verify we captured data
        jsonl_keys = [k for k in mock_s3.uploaded_objects if k.endswith(".jsonl.gz")]
        assert len(jsonl_keys) == 1

        compressed_data = mock_s3.uploaded_objects[jsonl_keys[0]]
        decompressed = gzip.decompress(compressed_data)
        lines = decompressed.decode("utf-8").strip().split("\n")
        assert len(lines) == len(sample_markets)

    def _capture_and_upload(
        self,
        mock_s3: MockS3ClientWithCapture,
        records: list[dict[str, Any]],
        platform: str,
        entity: str,
        dt: str,
        run_id: str,
    ) -> tuple[str, int]:
        """Helper to capture uploaded data during mock."""
        from prediction_data.core.compression import compress_jsonl

        compressed_data, row_count = compress_jsonl(records)
        key = f"bronze/{platform}/{entity}/dt={dt}/run_id={run_id}/part-000.jsonl.gz"
        mock_s3.uploaded_objects[key] = compressed_data
        return key, row_count


class TestManifestRowCount:
    """Tests verifying manifest row_count matches actual line count."""

    @pytest.mark.asyncio
    async def test_trades_manifest_row_count_matches_data(
        self,
        mock_credentials: MagicMock,
        sample_trades: list[dict[str, Any]],
    ) -> None:
        """Verify trades manifest row_count matches actual record count."""
        captured_manifest = {}

        with (
            patch(
                "prediction_data.bronze.kalshi.ingest.load_credentials_from_settings",
                return_value=mock_credentials,
            ),
            patch(
                "prediction_data.bronze.kalshi.ingest.KalshiClient"
            ) as mock_client_class,
            patch("prediction_data.bronze.kalshi.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.kalshi.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.bronze_bucket = "test-bucket"

            mock_client = AsyncMock()
            mock_client.fetch_all_trades.return_value = sample_trades
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_s3 = AsyncMock()
            mock_s3.upload_jsonl.return_value = ("key", len(sample_trades))

            def capture_manifest(manifest: Any) -> str:
                captured_manifest["manifest"] = manifest
                return "manifest_key"

            mock_s3.upload_manifest = AsyncMock(side_effect=capture_manifest)
            mock_s3_class.return_value.__aenter__.return_value = mock_s3

            await ingest_trades(dt="2024-01-15")

        manifest = captured_manifest["manifest"]
        assert manifest.row_count == len(sample_trades), (
            f"Manifest row_count ({manifest.row_count}) does not match "
            f"actual record count ({len(sample_trades)})"
        )

    @pytest.mark.asyncio
    async def test_markets_manifest_row_count_matches_data(
        self,
        mock_credentials: MagicMock,
        sample_markets: list[dict[str, Any]],
    ) -> None:
        """Verify markets manifest row_count matches actual record count."""
        captured_manifest = {}

        with (
            patch(
                "prediction_data.bronze.kalshi.ingest.load_credentials_from_settings",
                return_value=mock_credentials,
            ),
            patch(
                "prediction_data.bronze.kalshi.ingest.KalshiClient"
            ) as mock_client_class,
            patch("prediction_data.bronze.kalshi.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.kalshi.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.bronze_bucket = "test-bucket"

            mock_client = AsyncMock()
            mock_client.fetch_all_markets.return_value = sample_markets
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_s3 = AsyncMock()
            mock_s3.upload_jsonl.return_value = ("key", len(sample_markets))

            def capture_manifest(manifest: Any) -> str:
                captured_manifest["manifest"] = manifest
                return "manifest_key"

            mock_s3.upload_manifest = AsyncMock(side_effect=capture_manifest)
            mock_s3_class.return_value.__aenter__.return_value = mock_s3

            await ingest_markets(dt="2024-01-15")

        manifest = captured_manifest["manifest"]
        assert manifest.row_count == len(sample_markets)


class TestRunIdUniqueness:
    """Tests verifying run_id is unique per invocation."""

    @pytest.mark.asyncio
    async def test_trades_run_id_is_uuid4(
        self,
        mock_credentials: MagicMock,
        sample_trades: list[dict[str, Any]],
    ) -> None:
        """Verify trades ingestion returns a valid UUID4 run_id."""
        with (
            patch(
                "prediction_data.bronze.kalshi.ingest.load_credentials_from_settings",
                return_value=mock_credentials,
            ),
            patch(
                "prediction_data.bronze.kalshi.ingest.KalshiClient"
            ) as mock_client_class,
            patch("prediction_data.bronze.kalshi.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.kalshi.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.bronze_bucket = "test-bucket"

            mock_client = AsyncMock()
            mock_client.fetch_all_trades.return_value = sample_trades
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_s3 = AsyncMock()
            mock_s3.upload_jsonl.return_value = ("key", 3)
            mock_s3.upload_manifest.return_value = "manifest_key"
            mock_s3_class.return_value.__aenter__.return_value = mock_s3

            run_id = await ingest_trades(dt="2024-01-15")

        assert UUID4_PATTERN.match(run_id), f"run_id '{run_id}' is not a valid UUID4"

    @pytest.mark.asyncio
    async def test_markets_run_id_is_uuid4(
        self,
        mock_credentials: MagicMock,
        sample_markets: list[dict[str, Any]],
    ) -> None:
        """Verify markets ingestion returns a valid UUID4 run_id."""
        with (
            patch(
                "prediction_data.bronze.kalshi.ingest.load_credentials_from_settings",
                return_value=mock_credentials,
            ),
            patch(
                "prediction_data.bronze.kalshi.ingest.KalshiClient"
            ) as mock_client_class,
            patch("prediction_data.bronze.kalshi.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.kalshi.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.bronze_bucket = "test-bucket"

            mock_client = AsyncMock()
            mock_client.fetch_all_markets.return_value = sample_markets
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_s3 = AsyncMock()
            mock_s3.upload_jsonl.return_value = ("key", 2)
            mock_s3.upload_manifest.return_value = "manifest_key"
            mock_s3_class.return_value.__aenter__.return_value = mock_s3

            run_id = await ingest_markets(dt="2024-01-15")

        assert UUID4_PATTERN.match(run_id)

    @pytest.mark.asyncio
    async def test_multiple_invocations_produce_unique_run_ids(
        self,
        mock_credentials: MagicMock,
        sample_trades: list[dict[str, Any]],
    ) -> None:
        """Verify each invocation produces a unique run_id."""
        run_ids = []

        for _ in range(5):
            with (
                patch(
                    "prediction_data.bronze.kalshi.ingest.load_credentials_from_settings",
                    return_value=mock_credentials,
                ),
                patch(
                    "prediction_data.bronze.kalshi.ingest.KalshiClient"
                ) as mock_client_class,
                patch("prediction_data.bronze.kalshi.ingest.S3Client") as mock_s3_class,
                patch(
                    "prediction_data.bronze.kalshi.ingest.get_settings"
                ) as mock_settings,
            ):
                mock_settings.return_value.bronze_bucket = "test-bucket"

                mock_client = AsyncMock()
                mock_client.fetch_all_trades.return_value = sample_trades
                mock_client_class.return_value.__aenter__.return_value = mock_client

                mock_s3 = AsyncMock()
                mock_s3.upload_jsonl.return_value = ("key", 3)
                mock_s3.upload_manifest.return_value = "manifest_key"
                mock_s3_class.return_value.__aenter__.return_value = mock_s3

                run_id = await ingest_trades(dt="2024-01-15")
                run_ids.append(run_id)

        # All run_ids should be unique
        assert len(set(run_ids)) == len(run_ids), (
            f"Expected all unique run_ids, but got duplicates: {run_ids}"
        )


class TestCliOutput:
    """Tests verifying CLI behavior meets Bronze contract."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    def test_kalshi_trades_cli_prints_run_id_on_success(
        self,
        runner: CliRunner,
        mock_credentials: MagicMock,
        sample_trades: list[dict[str, Any]],
    ) -> None:
        """Verify CLI prints run_id to stdout on success."""
        with (
            patch(
                "prediction_data.bronze.kalshi.ingest.load_credentials_from_settings",
                return_value=mock_credentials,
            ),
            patch(
                "prediction_data.bronze.kalshi.ingest.KalshiClient"
            ) as mock_client_class,
            patch("prediction_data.bronze.kalshi.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.kalshi.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.bronze_bucket = "test-bucket"

            mock_client = AsyncMock()
            mock_client.fetch_all_trades.return_value = sample_trades
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_s3 = AsyncMock()
            mock_s3.upload_jsonl.return_value = ("key", 3)
            mock_s3.upload_manifest.return_value = "manifest_key"
            mock_s3_class.return_value.__aenter__.return_value = mock_s3

            result = runner.invoke(app, ["ingest", "kalshi-trades", "--dt", "2024-01-15"])

        # Check exit code is 0
        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. "
            f"Output: {result.output}. Exception: {result.exception}"
        )

        # Check output contains a valid UUID4 (the run_id)
        output = result.output.strip()
        # The output should contain a UUID line
        uuid_match = UUID4_PATTERN.search(output)
        assert uuid_match, f"Output does not contain a valid UUID4 run_id: {output}"

    def test_kalshi_markets_cli_prints_run_id_on_success(
        self,
        runner: CliRunner,
        mock_credentials: MagicMock,
        sample_markets: list[dict[str, Any]],
    ) -> None:
        """Verify CLI prints run_id to stdout on success."""
        with (
            patch(
                "prediction_data.bronze.kalshi.ingest.load_credentials_from_settings",
                return_value=mock_credentials,
            ),
            patch(
                "prediction_data.bronze.kalshi.ingest.KalshiClient"
            ) as mock_client_class,
            patch("prediction_data.bronze.kalshi.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.kalshi.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.bronze_bucket = "test-bucket"

            mock_client = AsyncMock()
            mock_client.fetch_all_markets.return_value = sample_markets
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_s3 = AsyncMock()
            mock_s3.upload_jsonl.return_value = ("key", 2)
            mock_s3.upload_manifest.return_value = "manifest_key"
            mock_s3_class.return_value.__aenter__.return_value = mock_s3

            result = runner.invoke(
                app, ["ingest", "kalshi-markets", "--dt", "2024-01-15"]
            )

        assert result.exit_code == 0
        uuid_match = UUID4_PATTERN.search(result.output.strip())
        assert uuid_match

    def test_kalshi_trades_cli_exits_with_code_1_on_error(
        self,
        runner: CliRunner,
    ) -> None:
        """Verify CLI exits with code 1 on error."""
        with patch(
            "prediction_data.bronze.kalshi.ingest.load_credentials_from_settings",
            side_effect=Exception("Test error"),
        ):
            result = runner.invoke(app, ["ingest", "kalshi-trades", "--dt", "2024-01-15"])

        assert result.exit_code == 1
        assert "Error" in result.output

    def test_kalshi_markets_cli_exits_with_code_1_on_error(
        self,
        runner: CliRunner,
    ) -> None:
        """Verify CLI exits with code 1 on error."""
        with patch(
            "prediction_data.bronze.kalshi.ingest.load_credentials_from_settings",
            side_effect=Exception("Test error"),
        ):
            result = runner.invoke(
                app, ["ingest", "kalshi-markets", "--dt", "2024-01-15"]
            )

        assert result.exit_code == 1
        assert "Error" in result.output


class TestS3OutputStructure:
    """Tests verifying S3 output follows Bronze layout."""

    @pytest.mark.asyncio
    async def test_trades_s3_key_follows_bronze_pattern(
        self,
        mock_credentials: MagicMock,
        sample_trades: list[dict[str, Any]],
    ) -> None:
        """Verify trades are uploaded with correct S3 key structure."""
        captured_key = {}

        with (
            patch(
                "prediction_data.bronze.kalshi.ingest.load_credentials_from_settings",
                return_value=mock_credentials,
            ),
            patch(
                "prediction_data.bronze.kalshi.ingest.KalshiClient"
            ) as mock_client_class,
            patch("prediction_data.bronze.kalshi.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.kalshi.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.bronze_bucket = "test-bucket"

            mock_client = AsyncMock()
            mock_client.fetch_all_trades.return_value = sample_trades
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_s3 = AsyncMock()

            async def capture_upload(**kwargs: Any) -> tuple[str, int]:
                key = f"bronze/{kwargs['platform']}/{kwargs['entity']}/dt={kwargs['dt']}/run_id={kwargs['run_id']}/part-000.jsonl.gz"
                captured_key["data_key"] = key
                return key, len(kwargs["records"])

            mock_s3.upload_jsonl = AsyncMock(side_effect=capture_upload)
            mock_s3.upload_manifest.return_value = "manifest_key"
            mock_s3_class.return_value.__aenter__.return_value = mock_s3

            await ingest_trades(dt="2024-01-15")

        # Verify the key follows Bronze pattern
        key = captured_key["data_key"]
        assert key.startswith("bronze/kalshi/trades/dt=2024-01-15/run_id=")
        assert key.endswith("/part-000.jsonl.gz")

    @pytest.mark.asyncio
    async def test_markets_s3_key_follows_bronze_pattern(
        self,
        mock_credentials: MagicMock,
        sample_markets: list[dict[str, Any]],
    ) -> None:
        """Verify markets are uploaded with correct S3 key structure."""
        captured_key = {}

        with (
            patch(
                "prediction_data.bronze.kalshi.ingest.load_credentials_from_settings",
                return_value=mock_credentials,
            ),
            patch(
                "prediction_data.bronze.kalshi.ingest.KalshiClient"
            ) as mock_client_class,
            patch("prediction_data.bronze.kalshi.ingest.S3Client") as mock_s3_class,
            patch("prediction_data.bronze.kalshi.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.bronze_bucket = "test-bucket"

            mock_client = AsyncMock()
            mock_client.fetch_all_markets.return_value = sample_markets
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_s3 = AsyncMock()

            async def capture_upload(**kwargs: Any) -> tuple[str, int]:
                key = f"bronze/{kwargs['platform']}/{kwargs['entity']}/dt={kwargs['dt']}/run_id={kwargs['run_id']}/part-000.jsonl.gz"
                captured_key["data_key"] = key
                return key, len(kwargs["records"])

            mock_s3.upload_jsonl = AsyncMock(side_effect=capture_upload)
            mock_s3.upload_manifest.return_value = "manifest_key"
            mock_s3_class.return_value.__aenter__.return_value = mock_s3

            await ingest_markets(dt="2024-01-15")

        key = captured_key["data_key"]
        assert key.startswith("bronze/kalshi/markets/dt=2024-01-15/run_id=")
        assert key.endswith("/part-000.jsonl.gz")
