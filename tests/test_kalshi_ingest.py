"""Tests for Kalshi data ingestion functions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prediction_data.bronze.kalshi.ingest import ingest_trades, run_ingest_trades


@pytest.fixture
def mock_credentials() -> MagicMock:
    """Create mock Kalshi credentials."""
    credentials = MagicMock()
    credentials.api_key_id = "test-key-id"
    return credentials


@pytest.fixture
def sample_trades() -> list[dict]:
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
    ]


class TestIngestTrades:
    """Tests for the ingest_trades function."""

    @pytest.mark.asyncio
    async def test_ingest_trades_fetches_and_uploads(
        self,
        mock_credentials: MagicMock,
        sample_trades: list[dict],
    ) -> None:
        """Test that ingest_trades fetches trades and uploads to S3."""
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
            # Configure mock settings
            mock_settings.return_value.bronze_bucket = "test-bucket"

            # Configure mock Kalshi client
            mock_client = AsyncMock()
            mock_client.fetch_all_trades.return_value = sample_trades
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Configure mock S3 client
            mock_s3 = AsyncMock()
            mock_s3.upload_jsonl.return_value = (
                "bronze/kalshi/trades/dt=2024-01-15/run_id=abc123/part-000.jsonl.gz",
                2,
            )
            mock_s3.upload_manifest.return_value = (
                "bronze/kalshi/trades/dt=2024-01-15/run_id=abc123/manifest.json"
            )
            mock_s3_class.return_value.__aenter__.return_value = mock_s3

            # Run ingestion
            run_id = await ingest_trades(dt="2024-01-15")

            # Verify trades were fetched
            mock_client.fetch_all_trades.assert_called_once_with(
                ticker=None,
                min_ts=None,
                max_ts=None,
            )

            # Verify data was uploaded to S3
            mock_s3.upload_jsonl.assert_called_once()
            call_kwargs = mock_s3.upload_jsonl.call_args.kwargs
            assert call_kwargs["records"] == sample_trades
            assert call_kwargs["platform"] == "kalshi"
            assert call_kwargs["entity"] == "trades"
            assert call_kwargs["dt"] == "2024-01-15"

            # Verify manifest was uploaded
            mock_s3.upload_manifest.assert_called_once()

            # Verify run_id is returned
            assert isinstance(run_id, str)
            assert len(run_id) > 0

    @pytest.mark.asyncio
    async def test_ingest_trades_with_ticker_filter(
        self,
        mock_credentials: MagicMock,
        sample_trades: list[dict],
    ) -> None:
        """Test that ingest_trades passes ticker filter to client."""
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
            mock_s3.upload_jsonl.return_value = ("key", 2)
            mock_s3.upload_manifest.return_value = "manifest_key"
            mock_s3_class.return_value.__aenter__.return_value = mock_s3

            await ingest_trades(dt="2024-01-15", ticker="PRES-2024-R-DEM")

            mock_client.fetch_all_trades.assert_called_once_with(
                ticker="PRES-2024-R-DEM",
                min_ts=None,
                max_ts=None,
            )

    @pytest.mark.asyncio
    async def test_ingest_trades_with_timestamp_filters(
        self,
        mock_credentials: MagicMock,
        sample_trades: list[dict],
    ) -> None:
        """Test that ingest_trades passes timestamp filters to client."""
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
            mock_s3.upload_jsonl.return_value = ("key", 2)
            mock_s3.upload_manifest.return_value = "manifest_key"
            mock_s3_class.return_value.__aenter__.return_value = mock_s3

            await ingest_trades(
                dt="2024-01-15",
                min_ts=1705320000,
                max_ts=1705406400,
            )

            mock_client.fetch_all_trades.assert_called_once_with(
                ticker=None,
                min_ts=1705320000,
                max_ts=1705406400,
            )

    @pytest.mark.asyncio
    async def test_ingest_trades_with_custom_bucket(
        self,
        mock_credentials: MagicMock,
        sample_trades: list[dict],
    ) -> None:
        """Test that ingest_trades uses custom bucket when provided."""
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
            mock_settings.return_value.bronze_bucket = "default-bucket"

            mock_client = AsyncMock()
            mock_client.fetch_all_trades.return_value = sample_trades
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_s3 = AsyncMock()
            mock_s3.upload_jsonl.return_value = ("key", 2)
            mock_s3.upload_manifest.return_value = "manifest_key"
            mock_s3_class.return_value.__aenter__.return_value = mock_s3

            await ingest_trades(dt="2024-01-15", bucket="custom-bucket")

            # Verify S3 client was created with custom bucket
            mock_s3_class.assert_called_once_with(bucket="custom-bucket")

    @pytest.mark.asyncio
    async def test_ingest_trades_manifest_has_correct_metadata(
        self,
        mock_credentials: MagicMock,
        sample_trades: list[dict],
    ) -> None:
        """Test that the manifest contains correct metadata."""
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
            mock_s3.upload_jsonl.return_value = (
                "bronze/kalshi/trades/dt=2024-01-15/run_id=abc123/part-000.jsonl.gz",
                2,
            )
            mock_s3.upload_manifest.return_value = "manifest_key"
            mock_s3_class.return_value.__aenter__.return_value = mock_s3

            await ingest_trades(dt="2024-01-15")

            # Get the manifest that was uploaded
            manifest = mock_s3.upload_manifest.call_args.args[0]

            assert manifest.platform == "kalshi"
            assert manifest.entity == "trades"
            assert manifest.dt == "2024-01-15"
            assert manifest.row_count == 2
            assert manifest.source.pagination == "cursor"
            assert "kalshi" in manifest.source.api_base_url.lower()


class TestRunIngestTrades:
    """Tests for the synchronous wrapper function."""

    def test_run_ingest_trades_calls_async_version(
        self,
        mock_credentials: MagicMock,
        sample_trades: list[dict],
    ) -> None:
        """Test that run_ingest_trades wraps the async function correctly."""
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
            mock_s3.upload_jsonl.return_value = ("key", 2)
            mock_s3.upload_manifest.return_value = "manifest_key"
            mock_s3_class.return_value.__aenter__.return_value = mock_s3

            run_id = run_ingest_trades(
                dt="2024-01-15",
                bucket="test-bucket",
                ticker="PRES-2024",
                min_ts=1705320000,
                max_ts=1705406400,
            )

            assert isinstance(run_id, str)
            mock_client.fetch_all_trades.assert_called_once_with(
                ticker="PRES-2024",
                min_ts=1705320000,
                max_ts=1705406400,
            )
