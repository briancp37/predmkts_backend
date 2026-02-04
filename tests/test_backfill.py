"""Backfill tests for the ingestion pipeline.

Validates that backfill capability works correctly:
- Running ingestion with a past date produces valid Bronze output
- Multiple backfill runs for the same date create unique run_ids (no overwrites)
- Backfill data lands in the correct S3 path with the specified date
- Manifests are created for each backfill run
- Date range iteration logic produces correct date lists
- Day boundary timestamp calculations are correct
- CLI backfill command validates inputs and orchestrates correctly
"""

from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from prediction_data.bronze.kalshi.ingest import (
    ingest_events as kalshi_ingest_events,
)
from prediction_data.bronze.kalshi.ingest import (
    ingest_trades as kalshi_ingest_trades,
)
from prediction_data.bronze.polymarket.ingest import (
    ingest_events as poly_ingest_events,
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

SAMPLE_POLY_EVENTS = [
    {"id": "e1", "slug": "us-election-2024", "title": "US Election 2024"},
    {"id": "e2", "slug": "fed-rate-decision", "title": "Fed Rate Decision"},
]

SAMPLE_KALSHI_EVENTS = [
    {"event_ticker": "KXELECTION", "title": "2024 Presidential Election", "category": "Politics"},
    {"event_ticker": "KXGDP", "title": "GDP Q4 2024", "category": "Economics"},
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


async def _run_poly_events_backfill(fake_s3: FakeS3Client, dt: str = PAST_DATE) -> str:
    """Run a Polymarket events backfill and return the run_id."""
    with (
        patch("prediction_data.bronze.polymarket.ingest.PolymarketClient") as MockClient,
        patch("prediction_data.bronze.polymarket.ingest.S3Client") as MockS3,
        patch("prediction_data.bronze.polymarket.ingest.get_settings") as mock_settings,
    ):
        mock_settings.return_value = MagicMock(bronze_bucket="test-bucket")
        client_instance = AsyncMock()
        client_instance.fetch_all_events.return_value = SAMPLE_POLY_EVENTS
        MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        MockS3.return_value = RealS3Client(bucket="test-bucket", s3_client=fake_s3)
        return await poly_ingest_events(dt=dt)


async def _run_kalshi_events_backfill(fake_s3: FakeS3Client, dt: str = PAST_DATE) -> str:
    """Run a Kalshi events backfill and return the run_id."""
    with (
        patch("prediction_data.bronze.kalshi.ingest.KalshiClient") as MockClient,
        patch("prediction_data.bronze.kalshi.ingest.S3Client") as MockS3,
        patch("prediction_data.bronze.kalshi.ingest.get_settings") as mock_settings,
        patch("prediction_data.bronze.kalshi.ingest.load_credentials_from_settings") as mock_creds,
    ):
        mock_settings.return_value = MagicMock(bronze_bucket="test-bucket")
        mock_creds.return_value = MagicMock()
        client_instance = AsyncMock()
        client_instance.fetch_all_events.return_value = SAMPLE_KALSHI_EVENTS
        MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        MockS3.return_value = RealS3Client(bucket="test-bucket", s3_client=fake_s3)
        return await kalshi_ingest_events(dt=dt)


class TestPolymarketEventsBackfill:
    """Backfill tests for Polymarket events ingestion."""

    @pytest.mark.asyncio
    async def test_backfill_past_date_produces_valid_output(self) -> None:
        """Backfill with a past date produces valid Bronze S3 output."""
        fake_s3 = FakeS3Client()
        run_id = await _run_poly_events_backfill(fake_s3)

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
        await _run_poly_events_backfill(fake_s3)

        data_key = [k for k in fake_s3.objects if k.endswith(".jsonl.gz")][0]
        assert "bronze/polymarket/events/" in data_key
        assert f"dt={PAST_DATE}/" in data_key
        assert "run_id=" in data_key

    @pytest.mark.asyncio
    async def test_backfill_manifest_created(self) -> None:
        """Backfill run produces a manifest with correct metadata."""
        fake_s3 = FakeS3Client()
        run_id = await _run_poly_events_backfill(fake_s3)

        manifest_key = [k for k in fake_s3.objects if k.endswith("manifest.json")][0]
        manifest = Manifest.from_json(fake_s3.objects[manifest_key].decode("utf-8"))

        assert manifest.run_id == run_id
        assert manifest.platform == "polymarket"
        assert manifest.entity == "events"
        assert manifest.dt == PAST_DATE
        assert manifest.row_count == len(SAMPLE_POLY_EVENTS)

    @pytest.mark.asyncio
    async def test_backfill_creates_new_run_id_no_overwrite(self) -> None:
        """Multiple backfills for the same date create separate run_ids."""
        run_ids = []
        all_keys: list[str] = []

        for _ in range(3):
            fake_s3 = FakeS3Client()
            run_id = await _run_poly_events_backfill(fake_s3)
            run_ids.append(run_id)
            all_keys.extend(fake_s3.objects.keys())

        assert len(set(run_ids)) == 3, f"Run IDs not unique: {run_ids}"
        assert len(set(all_keys)) == 6, f"S3 keys not unique: {all_keys}"


class TestKalshiEventsBackfill:
    """Backfill tests for Kalshi events ingestion."""

    @pytest.mark.asyncio
    async def test_backfill_past_date_produces_valid_output(self) -> None:
        """Backfill with a past date produces valid Bronze S3 output."""
        fake_s3 = FakeS3Client()
        run_id = await _run_kalshi_events_backfill(fake_s3)

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
        await _run_kalshi_events_backfill(fake_s3)

        data_key = [k for k in fake_s3.objects if k.endswith(".jsonl.gz")][0]
        assert "bronze/kalshi/events/" in data_key
        assert f"dt={PAST_DATE}/" in data_key
        assert "run_id=" in data_key

    @pytest.mark.asyncio
    async def test_backfill_manifest_created(self) -> None:
        """Backfill run produces a manifest with correct metadata."""
        fake_s3 = FakeS3Client()
        run_id = await _run_kalshi_events_backfill(fake_s3)

        manifest_key = [k for k in fake_s3.objects if k.endswith("manifest.json")][0]
        manifest = Manifest.from_json(fake_s3.objects[manifest_key].decode("utf-8"))

        assert manifest.run_id == run_id
        assert manifest.platform == "kalshi"
        assert manifest.entity == "events"
        assert manifest.dt == PAST_DATE
        assert manifest.row_count == len(SAMPLE_KALSHI_EVENTS)

    @pytest.mark.asyncio
    async def test_backfill_creates_new_run_id_no_overwrite(self) -> None:
        """Multiple backfills for the same date create separate run_ids."""
        run_ids = []
        all_keys: list[str] = []

        for _ in range(3):
            fake_s3 = FakeS3Client()
            run_id = await _run_kalshi_events_backfill(fake_s3)
            run_ids.append(run_id)
            all_keys.extend(fake_s3.objects.keys())

        assert len(set(run_ids)) == 3, f"Run IDs not unique: {run_ids}"
        assert len(set(all_keys)) == 6, f"S3 keys not unique: {all_keys}"


# ---------------------------------------------------------------------------
# Unit tests for backfill helper functions
# ---------------------------------------------------------------------------


class TestDateRange:
    """Tests for _date_range helper."""

    def test_single_day(self) -> None:
        from prediction_data.cli.main import _date_range

        result = _date_range(date(2025, 6, 15), date(2025, 6, 15))
        assert result == [date(2025, 6, 15)]

    def test_multi_day(self) -> None:
        from prediction_data.cli.main import _date_range

        result = _date_range(date(2025, 6, 13), date(2025, 6, 16))
        assert result == [
            date(2025, 6, 13),
            date(2025, 6, 14),
            date(2025, 6, 15),
            date(2025, 6, 16),
        ]

    def test_month_boundary(self) -> None:
        from prediction_data.cli.main import _date_range

        result = _date_range(date(2025, 1, 30), date(2025, 2, 2))
        assert result == [
            date(2025, 1, 30),
            date(2025, 1, 31),
            date(2025, 2, 1),
            date(2025, 2, 2),
        ]

    def test_start_after_end_returns_empty(self) -> None:
        from prediction_data.cli.main import _date_range

        result = _date_range(date(2025, 6, 20), date(2025, 6, 15))
        assert result == []


class TestDayBoundariesTs:
    """Tests for _day_boundaries_ts helper."""

    def test_returns_utc_boundaries(self) -> None:
        from prediction_data.cli.main import _day_boundaries_ts

        start_ts, end_ts = _day_boundaries_ts(date(2025, 6, 15))
        # 2025-06-15 00:00:00 UTC
        assert start_ts == 1749945600
        # 2025-06-15 23:59:59 UTC
        assert end_ts == 1750031999

    def test_boundaries_span_one_day(self) -> None:
        from prediction_data.cli.main import _day_boundaries_ts

        start_ts, end_ts = _day_boundaries_ts(date(2025, 1, 1))
        assert end_ts - start_ts == 86399  # 24h - 1s


class TestResolvePlatformsAndEntities:
    """Tests for _resolve_platforms and _resolve_entities."""

    def test_resolve_platforms_all(self) -> None:
        from prediction_data.cli.main import _resolve_platforms

        assert _resolve_platforms("all") == ["polymarket", "kalshi"]

    def test_resolve_platforms_single(self) -> None:
        from prediction_data.cli.main import _resolve_platforms

        assert _resolve_platforms("kalshi") == ["kalshi"]

    def test_resolve_entities_all(self) -> None:
        from prediction_data.cli.main import _resolve_entities

        assert _resolve_entities("all") == ["trades", "markets", "events", "order_filled"]

    def test_resolve_entities_single(self) -> None:
        from prediction_data.cli.main import _resolve_entities

        assert _resolve_entities("trades") == ["trades"]


# ---------------------------------------------------------------------------
# CLI command tests
# ---------------------------------------------------------------------------

runner = CliRunner()


class TestBackfillCLI:
    """Tests for the backfill run CLI command."""

    def _invoke(self, args: list[str], **extra_patches: Any) -> Any:
        """Invoke the CLI with configure_logging patched out."""
        from prediction_data.cli.main import app

        with patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")):
            return runner.invoke(app, ["backfill", "run"] + args)

    def test_invalid_date_format_exits_1(self) -> None:
        result = self._invoke(["--start-date", "not-a-date", "--end-date", "2025-06-15"])
        assert result.exit_code == 1

    def test_start_after_end_exits_1(self) -> None:
        result = self._invoke(["--start-date", "2025-06-20", "--end-date", "2025-06-15"])
        assert result.exit_code == 1

    def test_invalid_platform_exits_1(self) -> None:
        result = self._invoke([
            "--start-date", "2025-06-15",
            "--end-date", "2025-06-15",
            "--platform", "binance",
        ])
        assert result.exit_code == 1

    def test_invalid_entity_exits_1(self) -> None:
        result = self._invoke([
            "--start-date", "2025-06-15",
            "--end-date", "2025-06-15",
            "--entity", "orders",
        ])
        assert result.exit_code == 1

    def test_dry_run_prints_plan_without_executing(self) -> None:
        from prediction_data.cli.main import app

        with patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")):
            result = runner.invoke(
                app,
                [
                    "backfill", "run",
                    "--start-date", "2025-06-15",
                    "--end-date", "2025-06-16",
                    "--platform", "polymarket",
                    "--entity", "trades",
                    "--dry-run",
                ],
            )
        assert result.exit_code == 0
        assert "[dry-run]" in result.output
        assert "2025-06-15" in result.output
        assert "2025-06-16" in result.output

    def test_successful_single_day_backfill(self) -> None:
        from prediction_data.cli.main import app

        with (
            patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")),
            patch("prediction_data.cli.main._ingest_one", new_callable=AsyncMock) as mock_ingest,
        ):
            mock_ingest.return_value = "test-run-id-123"
            result = runner.invoke(
                app,
                [
                    "backfill", "run",
                    "--start-date", "2025-06-15",
                    "--end-date", "2025-06-15",
                    "--platform", "kalshi",
                    "--entity", "trades",
                ],
            )
        assert result.exit_code == 0
        assert "test-run-id-123" in result.output
        mock_ingest.assert_called_once()

    def test_multi_day_calls_ingest_per_day_for_trades(self) -> None:
        from prediction_data.cli.main import app

        with (
            patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")),
            patch("prediction_data.cli.main._ingest_one", new_callable=AsyncMock) as mock_ingest,
        ):
            mock_ingest.return_value = "run-id"
            result = runner.invoke(
                app,
                [
                    "backfill", "run",
                    "--start-date", "2025-06-13",
                    "--end-date", "2025-06-16",
                    "--platform", "polymarket",
                    "--entity", "trades",
                ],
            )
        assert result.exit_code == 0
        assert mock_ingest.call_count == 4

    def test_catalog_entity_runs_once(self) -> None:
        from prediction_data.cli.main import app

        with (
            patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")),
            patch("prediction_data.cli.main._ingest_one", new_callable=AsyncMock) as mock_ingest,
        ):
            mock_ingest.return_value = "run-id"
            result = runner.invoke(
                app,
                [
                    "backfill", "run",
                    "--start-date", "2025-06-13",
                    "--end-date", "2025-06-16",
                    "--platform", "polymarket",
                    "--entity", "events",
                ],
            )
        assert result.exit_code == 0
        assert mock_ingest.call_count == 1

    def test_failure_on_one_day_continues_and_exits_1(self) -> None:
        from prediction_data.cli.main import app

        call_count = 0

        async def _side_effect(**kwargs: Any) -> str:
            nonlocal call_count
            call_count += 1
            if kwargs.get("dt_str") == "2025-06-14":
                raise RuntimeError("API down")
            return "ok-run-id"

        with (
            patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")),
            patch("prediction_data.cli.main._ingest_one", side_effect=_side_effect),
        ):
            result = runner.invoke(
                app,
                [
                    "backfill", "run",
                    "--start-date", "2025-06-13",
                    "--end-date", "2025-06-15",
                    "--platform", "kalshi",
                    "--entity", "trades",
                ],
            )
        assert call_count == 3
        assert result.exit_code == 1
        assert "1 failure" in result.output


class TestCatchupCLI:
    """Tests for the backfill catchup CLI command."""

    def _invoke(self, args: list[str]) -> Any:
        from prediction_data.cli.main import app

        with patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")):
            return runner.invoke(app, ["backfill", "catchup"] + args)

    def test_invalid_platform_exits_1(self) -> None:
        result = self._invoke(["--platform", "binance"])
        assert result.exit_code == 1

    def test_invalid_entity_exits_1(self) -> None:
        result = self._invoke(["--entity", "orders"])
        assert result.exit_code == 1

    def test_no_bucket_env_exits_1(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = self._invoke(["--platform", "polymarket", "--entity", "trades"])
        assert result.exit_code == 1

    def test_dry_run_order_filled_incremental(self) -> None:
        """order_filled uses timestamp-incremental catchup via Goldsky."""
        from prediction_data.cli.main import app

        with (
            patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")),
            patch("prediction_data.storage.discovery.find_latest_manifest_source", new_callable=AsyncMock) as mock_src,
            patch("prediction_data.storage.S3Client"),
            patch("prediction_data.cli.main.date") as mock_date,
        ):
            mock_date.today.return_value = date(2025, 6, 20)
            mock_date.fromisoformat = date.fromisoformat
            mock_src.return_value = ("2025-06-20", 1750444800)
            result = runner.invoke(
                app,
                ["backfill", "catchup", "--platform", "polymarket", "--entity", "order_filled", "--dry-run", "--bucket", "test-bucket"],
            )
        assert result.exit_code == 0
        assert "[dry-run]" in result.output
        assert "since_timestamp=1750444800" in result.output

    def test_dry_run_order_filled_no_timestamp(self) -> None:
        """order_filled dry-run when manifest exists but has no timestamp."""
        from prediction_data.cli.main import app

        with (
            patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")),
            patch("prediction_data.storage.discovery.find_latest_manifest_source", new_callable=AsyncMock) as mock_src,
            patch("prediction_data.storage.S3Client"),
            patch("prediction_data.cli.main.date") as mock_date,
        ):
            mock_date.today.return_value = date(2025, 6, 20)
            mock_date.fromisoformat = date.fromisoformat
            mock_src.return_value = ("2025-06-20", None)
            result = runner.invoke(
                app,
                ["backfill", "catchup", "--platform", "polymarket", "--entity", "order_filled", "--dry-run", "--bucket", "test-bucket"],
            )
        assert result.exit_code == 0
        assert "[dry-run]" in result.output
        assert "no timestamp in latest manifest" in result.output

    def test_dry_run_trades_date_scoped(self) -> None:
        from prediction_data.cli.main import app

        with (
            patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")),
            patch("prediction_data.storage.discovery.find_latest_date", new_callable=AsyncMock) as mock_dt,
            patch("prediction_data.storage.S3Client"),
            patch("prediction_data.cli.main.date") as mock_date,
        ):
            mock_date.today.return_value = date(2025, 6, 20)
            mock_date.fromisoformat = date.fromisoformat
            mock_dt.return_value = "2025-06-17"
            result = runner.invoke(
                app,
                ["backfill", "catchup", "--platform", "kalshi", "--entity", "trades", "--dry-run", "--bucket", "test-bucket"],
            )
        assert result.exit_code == 0
        assert "[dry-run]" in result.output
        assert "3 day(s)" in result.output

    def test_skip_no_existing_data_order_filled(self) -> None:
        """order_filled skips when no existing data (no date partition found)."""
        from prediction_data.cli.main import app

        with (
            patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")),
            patch("prediction_data.storage.discovery.find_latest_manifest_source", new_callable=AsyncMock) as mock_src,
            patch("prediction_data.storage.S3Client"),
        ):
            mock_src.return_value = (None, None)
            result = runner.invoke(
                app,
                ["backfill", "catchup", "--platform", "polymarket", "--entity", "order_filled", "--bucket", "test-bucket"],
            )
        assert result.exit_code == 0
        assert "no existing data found" in result.output

    def test_skip_already_up_to_date_trades(self) -> None:
        from prediction_data.cli.main import app

        with (
            patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")),
            patch("prediction_data.storage.discovery.find_latest_date", new_callable=AsyncMock) as mock_dt,
            patch("prediction_data.storage.S3Client"),
            patch("prediction_data.cli.main.date") as mock_date,
        ):
            mock_date.today.return_value = date(2025, 6, 20)
            mock_date.fromisoformat = date.fromisoformat
            mock_dt.return_value = "2025-06-20"
            result = runner.invoke(
                app,
                ["backfill", "catchup", "--platform", "kalshi", "--entity", "trades", "--bucket", "test-bucket"],
            )
        assert result.exit_code == 0
        assert "already up to date" in result.output

    def test_skip_already_up_to_date_catalog(self) -> None:
        """Catalog with --full skips when today's snapshot exists."""
        from prediction_data.cli.main import app

        with (
            patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")),
            patch("prediction_data.storage.discovery.find_latest_date", new_callable=AsyncMock) as mock_dt,
            patch("prediction_data.storage.S3Client"),
            patch("prediction_data.cli.main.date") as mock_date,
        ):
            mock_date.today.return_value = date(2025, 6, 20)
            mock_date.fromisoformat = date.fromisoformat
            mock_dt.return_value = "2025-06-20"
            result = runner.invoke(
                app,
                ["backfill", "catchup", "--platform", "polymarket", "--entity", "markets", "--full", "--bucket", "test-bucket"],
            )
        assert result.exit_code == 0
        assert "already up to date" in result.output

    def test_order_filled_incremental_executes(self) -> None:
        """order_filled catchup uses timestamp-incremental ingest."""
        from prediction_data.cli.main import app

        with (
            patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")),
            patch("prediction_data.storage.discovery.find_latest_manifest_source", new_callable=AsyncMock) as mock_src,
            patch("prediction_data.storage.S3Client"),
            patch("prediction_data.bronze.polymarket.ingest.ingest_order_filled", new_callable=AsyncMock) as mock_ingest,
            patch("prediction_data.cli.main.date") as mock_date,
        ):
            mock_date.today.return_value = date(2025, 6, 20)
            mock_date.fromisoformat = date.fromisoformat
            mock_src.return_value = ("2025-06-20", 1750444800)
            mock_ingest.return_value = "test-run-id"
            result = runner.invoke(
                app,
                ["backfill", "catchup", "--platform", "polymarket", "--entity", "order_filled", "--bucket", "test-bucket"],
            )
        assert result.exit_code == 0
        # Should call ingest once with since_timestamp
        assert mock_ingest.call_count == 1
        mock_ingest.assert_called_once_with(
            "2025-06-20",
            bucket="test-bucket",
            since_timestamp=1750444800,
        )
        assert "OK" in result.output

    def test_failure_continues_to_next_entity(self) -> None:
        from prediction_data.cli.main import app

        with (
            patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")),
            patch("prediction_data.storage.discovery.find_latest_timestamp", new_callable=AsyncMock) as mock_ts,
            patch("prediction_data.storage.discovery.find_latest_date", new_callable=AsyncMock) as mock_dt,
            patch("prediction_data.storage.S3Client"),
        ):
            mock_ts.side_effect = RuntimeError("S3 error")
            mock_dt.return_value = None
            result = runner.invoke(
                app,
                ["backfill", "catchup", "--platform", "polymarket", "--entity", "all", "--bucket", "test-bucket"],
            )
        # Should have failures but still process all entities
        assert result.exit_code == 1
        assert "failure" in result.output

    def test_catalog_incremental_by_default_dry_run(self) -> None:
        """Catchup uses incremental mode for catalog entities by default."""
        from prediction_data.cli.main import app

        with (
            patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")),
            patch("prediction_data.storage.discovery.find_latest_manifest_source", new_callable=AsyncMock) as mock_src,
            patch("prediction_data.storage.S3Client"),
        ):
            mock_src.return_value = ("2026-01-30", 1769947200)  # epoch for 2026-02-01T12:00:00Z
            result = runner.invoke(
                app,
                ["backfill", "catchup", "--platform", "polymarket", "--entity", "markets", "--dry-run", "--bucket", "test-bucket"],
            )
        assert result.exit_code == 0
        assert "[dry-run]" in result.output
        assert "incrementally" in result.output
        assert "since_updated_at=" in result.output

    def test_catalog_full_flag_forces_snapshot_dry_run(self) -> None:
        """--full flag forces full snapshot mode for catalog entities."""
        from prediction_data.cli.main import app

        with (
            patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")),
            patch("prediction_data.storage.discovery.find_latest_date", new_callable=AsyncMock) as mock_dt,
            patch("prediction_data.storage.S3Client"),
        ):
            mock_dt.return_value = "2026-01-30"
            result = runner.invoke(
                app,
                ["backfill", "catchup", "--platform", "polymarket", "--entity", "markets", "--dry-run", "--full", "--bucket", "test-bucket"],
            )
        assert result.exit_code == 0
        assert "[dry-run]" in result.output
        assert "full catalog snapshot" in result.output

    def test_catalog_first_run_falls_back_to_full(self) -> None:
        """When no previous data exists, incremental falls back to full snapshot."""
        from prediction_data.cli.main import app

        with (
            patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")),
            patch("prediction_data.storage.discovery.find_latest_manifest_source", new_callable=AsyncMock) as mock_src,
            patch("prediction_data.storage.S3Client"),
        ):
            mock_src.return_value = (None, None)
            result = runner.invoke(
                app,
                ["backfill", "catchup", "--platform", "polymarket", "--entity", "markets", "--dry-run", "--bucket", "test-bucket"],
            )
        assert result.exit_code == 0
        assert "[dry-run]" in result.output
        assert "first run" in result.output

    def test_catalog_no_cursor_falls_back_to_full(self) -> None:
        """When manifest has no latest_timestamp, falls back to full snapshot."""
        from prediction_data.cli.main import app

        with (
            patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")),
            patch("prediction_data.storage.discovery.find_latest_manifest_source", new_callable=AsyncMock) as mock_src,
            patch("prediction_data.storage.S3Client"),
        ):
            mock_src.return_value = ("2026-01-30", None)
            result = runner.invoke(
                app,
                ["backfill", "catchup", "--platform", "polymarket", "--entity", "markets", "--dry-run", "--bucket", "test-bucket"],
            )
        assert result.exit_code == 0
        assert "no cursor" in result.output

    def test_catalog_incremental_executes(self) -> None:
        """Catchup incremental mode calls ingest with since_updated_at."""
        from prediction_data.cli.main import app

        with (
            patch("prediction_data.core.logging.get_settings", return_value=MagicMock(log_level="INFO")),
            patch("prediction_data.storage.discovery.find_latest_manifest_source", new_callable=AsyncMock) as mock_src,
            patch("prediction_data.storage.S3Client"),
            patch("prediction_data.bronze.polymarket.ingest.ingest_markets", new_callable=AsyncMock) as mock_ingest,
        ):
            mock_src.return_value = ("2026-01-30", 1769947200)
            mock_ingest.return_value = "test-run-id"
            result = runner.invoke(
                app,
                ["backfill", "catchup", "--platform", "polymarket", "--entity", "markets", "--bucket", "test-bucket"],
            )
        assert result.exit_code == 0
        assert "test-run-id" in result.output
        mock_ingest.assert_called_once()
        call_kwargs = mock_ingest.call_args
        assert call_kwargs.kwargs.get("since_updated_at") is not None
