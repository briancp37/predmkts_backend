"""Tests for Silver CLI commands (process, backfill, dry-run, state tracking)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from prediction_data.cli.silver import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeManifestInner:
    generated_at: datetime


@dataclass
class FakeDiscoveredManifest:
    run_id: str
    platform: str
    entity: str
    dt: str
    snapshot_type: str = "snapshot"
    row_count: int = 100
    manifest: FakeManifestInner | None = None

    def __post_init__(self) -> None:
        if self.manifest is None:
            self.manifest = FakeManifestInner(generated_at=datetime.now(UTC))


def _manifest(
    run_id: str = "run-1",
    platform: str = "polymarket",
    entity: str = "trades",
    dt: str = "2024-06-15",
    snapshot_type: str = "snapshot",
    generated_at: datetime | None = None,
) -> FakeDiscoveredManifest:
    inner = FakeManifestInner(generated_at=generated_at or datetime.now(UTC))
    return FakeDiscoveredManifest(
        run_id=run_id, platform=platform, entity=entity, dt=dt,
        snapshot_type=snapshot_type, manifest=inner,
    )


@dataclass
class FakeProcessingResult:
    rows_written: int = 10
    snapshot_id: int = 42
    duplicates_dropped: int = 0
    duration_seconds: float = 0.5


class FakeStateStore:
    """In-memory state store that tracks processed run_ids."""

    def __init__(self) -> None:
        self._processed: set[str] = set()

    async def load(self) -> None:
        pass

    def is_processed(self, run_id: str) -> bool:
        return run_id in self._processed

    async def mark_processed(self, *, run_id: str, platform: str, entity: str, dt: str) -> None:
        self._processed.add(run_id)


# Shared patch targets — these are imported inside _run_process via lazy imports,
# so we patch them at their source modules.
_DISCOVER = "prediction_data.silver.discovery.discover_manifests"
_PROCESS = "prediction_data.silver.processor.process_manifest"
_PROCESS_CHUNKED = "prediction_data.silver.processor.process_manifest_chunked"
_STATE = "prediction_data.silver.state.SilverStateStore"
_CATALOG = "prediction_data.silver.catalog.get_catalog"
_S3 = "prediction_data.storage.S3Client"
_LOGGING = "prediction_data.core.logging.configure_logging"
_LOAD_MARKETS_REF = "prediction_data.silver.polymarket.markets_reference.load_markets_reference"


def _fake_markets_lookup() -> MagicMock:
    """Return a mock MarketsReferenceLookup with non-zero length."""
    mock = MagicMock()
    mock.__len__ = MagicMock(return_value=100)
    mock.coverage_stats = {"lookup_entries": 100, "unique_markets": 50}
    return mock


def _base_env() -> dict[str, str]:
    return {"BRONZE_BUCKET": "test-bucket"}


# ---------------------------------------------------------------------------
# Test: single-day processing via CLI
# ---------------------------------------------------------------------------


class TestSingleDayProcessing:
    def test_single_day_processes_manifest(self) -> None:
        m = _manifest()
        fake_state = FakeStateStore()

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=[m]),
            patch(_STATE, return_value=fake_state),
            patch(_CATALOG, return_value=MagicMock()),
            patch(_LOAD_MARKETS_REF, new_callable=AsyncMock, return_value=_fake_markets_lookup()),
            patch(
                _PROCESS_CHUNKED,
                new_callable=AsyncMock,
                return_value=FakeProcessingResult(),
            ) as mock_process,
        ):
            result = runner.invoke(
                app,
                ["process", "--platform", "polymarket", "--entity", "trades", "--dt", "2024-06-15"],
                env=_base_env(),
            )

        assert result.exit_code == 0
        assert "10 rows" in result.output
        assert "All manifests processed successfully" in result.output
        mock_process.assert_awaited_once()

    def test_no_manifests_found(self) -> None:
        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=[]),
        ):
            result = runner.invoke(
                app,
                ["process", "--platform", "polymarket", "--entity", "trades", "--dt", "2024-06-15"],
                env=_base_env(),
            )

        assert "No manifests found" in result.output


# ---------------------------------------------------------------------------
# Test: date range backfill
# ---------------------------------------------------------------------------


class TestDateRangeBackfill:
    def test_date_range_processes_multiple_days(self) -> None:
        manifests = [
            _manifest(run_id="run-1", dt="2024-06-15"),
            _manifest(run_id="run-2", dt="2024-06-16"),
            _manifest(run_id="run-3", dt="2024-06-17"),
        ]
        fake_state = FakeStateStore()

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=manifests),
            patch(_STATE, return_value=fake_state),
            patch(_CATALOG, return_value=MagicMock()),
            patch(_LOAD_MARKETS_REF, new_callable=AsyncMock, return_value=_fake_markets_lookup()),
            patch(
                _PROCESS_CHUNKED,
                new_callable=AsyncMock,
                return_value=FakeProcessingResult(),
            ) as mock_process,
        ):
            result = runner.invoke(
                app,
                [
                    "process",
                    "--platform", "polymarket",
                    "--entity", "trades",
                    "--start-date", "2024-06-15",
                    "--end-date", "2024-06-17",
                ],
                env=_base_env(),
            )

        assert result.exit_code == 0
        assert mock_process.await_count == 3
        assert "Processed: 3/3" in result.output

    def test_continues_on_per_day_failure(self) -> None:
        from prediction_data.silver.processor import ProcessingError

        manifests = [
            _manifest(run_id="run-1", dt="2024-06-15"),
            _manifest(run_id="run-2", dt="2024-06-16"),
        ]
        fake_state = FakeStateStore()

        async def process_side_effect(m: object, s3: object, catalog: object, **kwargs: object) -> FakeProcessingResult:
            if getattr(m, "run_id") == "run-1":
                raise ProcessingError("boom")
            return FakeProcessingResult()

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=manifests),
            patch(_STATE, return_value=fake_state),
            patch(_CATALOG, return_value=MagicMock()),
            patch(_LOAD_MARKETS_REF, new_callable=AsyncMock, return_value=_fake_markets_lookup()),
            patch(_PROCESS_CHUNKED, new_callable=AsyncMock, side_effect=process_side_effect),
        ):
            result = runner.invoke(
                app,
                [
                    "process",
                    "--platform", "polymarket",
                    "--entity", "trades",
                    "--start-date", "2024-06-15",
                    "--end-date", "2024-06-16",
                ],
                env=_base_env(),
            )

        # Exit code 1 due to failures, but both days attempted
        assert result.exit_code == 1
        assert "Processed: 1/2" in result.output
        assert "FAILED" in result.output


# ---------------------------------------------------------------------------
# Test: dry-run mode (no writes)
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_does_not_process(self) -> None:
        manifests = [
            _manifest(run_id="run-1", dt="2024-06-15"),
            _manifest(run_id="run-2", dt="2024-06-16"),
        ]
        fake_state = FakeStateStore()

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=manifests),
            patch(_STATE, return_value=fake_state),
            patch(_PROCESS_CHUNKED, new_callable=AsyncMock) as mock_process,
        ):
            result = runner.invoke(
                app,
                [
                    "process",
                    "--platform", "polymarket",
                    "--entity", "trades",
                    "--start-date", "2024-06-15",
                    "--end-date", "2024-06-16",
                    "--dry-run",
                ],
                env=_base_env(),
            )

        assert result.exit_code == 0
        mock_process.assert_not_awaited()
        assert "Dry run" in result.output
        assert "run-1" in result.output
        assert "run-2" in result.output


# ---------------------------------------------------------------------------
# Test: state tracking prevents reprocessing
# ---------------------------------------------------------------------------


class TestStateTracking:
    def test_already_processed_manifests_skipped(self) -> None:
        manifests = [
            _manifest(run_id="run-1", dt="2024-06-15"),
            _manifest(run_id="run-2", dt="2024-06-15"),
        ]
        fake_state = FakeStateStore()
        fake_state._processed.add("run-1")  # pre-mark as processed

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=manifests),
            patch(_STATE, return_value=fake_state),
            patch(_CATALOG, return_value=MagicMock()),
            patch(_LOAD_MARKETS_REF, new_callable=AsyncMock, return_value=_fake_markets_lookup()),
            patch(
                _PROCESS_CHUNKED,
                new_callable=AsyncMock,
                return_value=FakeProcessingResult(),
            ) as mock_process,
        ):
            result = runner.invoke(
                app,
                ["process", "--platform", "polymarket", "--entity", "trades", "--dt", "2024-06-15"],
                env=_base_env(),
            )

        assert result.exit_code == 0
        assert "Skipping 1 already-processed" in result.output
        # Only run-2 should be processed
        mock_process.assert_awaited_once()

    def test_all_processed_skips_gracefully(self) -> None:
        manifests = [_manifest(run_id="run-1", dt="2024-06-15")]
        fake_state = FakeStateStore()
        fake_state._processed.add("run-1")

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=manifests),
            patch(_STATE, return_value=fake_state),
        ):
            result = runner.invoke(
                app,
                ["process", "--platform", "polymarket", "--entity", "trades", "--dt", "2024-06-15"],
                env=_base_env(),
            )

        assert result.exit_code == 0
        assert "No unprocessed manifests remaining" in result.output


# ---------------------------------------------------------------------------
# Test: force-reprocess flag overrides state
# ---------------------------------------------------------------------------


class TestForceReprocess:
    def test_force_reprocess_ignores_state(self) -> None:
        manifests = [_manifest(run_id="run-1", dt="2024-06-15")]
        fake_state = FakeStateStore()
        fake_state._processed.add("run-1")  # already processed

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=manifests),
            patch(_STATE, return_value=fake_state),
            patch(_CATALOG, return_value=MagicMock()),
            patch(_LOAD_MARKETS_REF, new_callable=AsyncMock, return_value=_fake_markets_lookup()),
            patch(
                _PROCESS_CHUNKED,
                new_callable=AsyncMock,
                return_value=FakeProcessingResult(),
            ) as mock_process,
        ):
            result = runner.invoke(
                app,
                [
                    "process",
                    "--platform", "polymarket",
                    "--entity", "trades",
                    "--dt", "2024-06-15",
                    "--force-reprocess",
                ],
                env=_base_env(),
            )

        assert result.exit_code == 0
        # Should NOT see "Skipping" message
        assert "Skipping" not in result.output
        mock_process.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test: cross-run dedup — snapshot supersedes prior deltas
# ---------------------------------------------------------------------------


class TestCrossRunDedup:
    def test_snapshot_supersedes_prior_deltas_for_catalog_entity(self) -> None:
        """For catalog entities, snapshot supersedes prior deltas."""
        t0 = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        manifests = [
            _manifest(run_id="delta-1", dt="2024-06-15", entity="markets", snapshot_type="delta", generated_at=t0),
            _manifest(run_id="snap-1", dt="2024-06-15", entity="markets", snapshot_type="snapshot", generated_at=t0 + timedelta(hours=1)),
            _manifest(run_id="delta-2", dt="2024-06-15", entity="markets", snapshot_type="delta", generated_at=t0 + timedelta(hours=2)),
        ]
        fake_state = FakeStateStore()

        processed_run_ids: list[str] = []

        async def track_process(m: object, s3: object, catalog: object, **kwargs: object) -> FakeProcessingResult:
            processed_run_ids.append(getattr(m, "run_id"))
            return FakeProcessingResult()

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=manifests),
            patch(_STATE, return_value=fake_state),
            patch(_CATALOG, return_value=MagicMock()),
            patch(_PROCESS, new_callable=AsyncMock, side_effect=track_process),
        ):
            result = runner.invoke(
                app,
                ["process", "--platform", "polymarket", "--entity", "markets", "--dt", "2024-06-15"],
                env=_base_env(),
            )

        assert result.exit_code == 0
        # delta-1 should be skipped (precedes snapshot), snap-1 and delta-2 processed
        assert "delta-1" not in processed_run_ids
        assert "snap-1" in processed_run_ids
        assert "delta-2" in processed_run_ids
        assert "superseded by snapshot" in result.output

    def test_catalog_entity_keeps_only_latest_snapshot(self) -> None:
        """Multiple snapshots for same day on catalog entity — only latest is processed."""
        t0 = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        manifests = [
            _manifest(run_id="snap-1", dt="2024-06-15", entity="markets", snapshot_type="snapshot", generated_at=t0),
            _manifest(run_id="snap-2", dt="2024-06-15", entity="markets", snapshot_type="snapshot", generated_at=t0 + timedelta(hours=1)),
        ]
        fake_state = FakeStateStore()

        processed_run_ids: list[str] = []

        async def track_process(m: object, s3: object, catalog: object, **kwargs: object) -> FakeProcessingResult:
            processed_run_ids.append(getattr(m, "run_id"))
            return FakeProcessingResult()

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=manifests),
            patch(_STATE, return_value=fake_state),
            patch(_CATALOG, return_value=MagicMock()),
            patch(_PROCESS, new_callable=AsyncMock, side_effect=track_process),
        ):
            result = runner.invoke(
                app,
                ["process", "--platform", "polymarket", "--entity", "markets", "--dt", "2024-06-15"],
                env=_base_env(),
            )

        assert result.exit_code == 0
        # select_manifests_for_day uses snapshot-supersedes-delta for catalog entities
        assert processed_run_ids == ["snap-2"]

    def test_stream_entity_processes_all_manifests(self) -> None:
        """Multiple manifests for same day on stream entity — all are processed."""
        t0 = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        manifests = [
            _manifest(run_id="run-1", dt="2024-06-15", entity="trades", snapshot_type="snapshot", generated_at=t0),
            _manifest(run_id="run-2", dt="2024-06-15", entity="trades", snapshot_type="snapshot", generated_at=t0 + timedelta(hours=1)),
        ]
        fake_state = FakeStateStore()

        processed_run_ids: list[str] = []

        async def track_process(m: object, s3: object, catalog: object, **kwargs: object) -> FakeProcessingResult:
            processed_run_ids.append(getattr(m, "run_id"))
            return FakeProcessingResult()

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=manifests),
            patch(_STATE, return_value=fake_state),
            patch(_CATALOG, return_value=MagicMock()),
            patch(_LOAD_MARKETS_REF, new_callable=AsyncMock, return_value=_fake_markets_lookup()),
            patch(_PROCESS_CHUNKED, new_callable=AsyncMock, side_effect=track_process),
        ):
            result = runner.invoke(
                app,
                ["process", "--platform", "polymarket", "--entity", "trades", "--dt", "2024-06-15"],
                env=_base_env(),
            )

        assert result.exit_code == 0
        # Stream entities process all manifests — each is an independent batch
        assert processed_run_ids == ["run-1", "run-2"]

    def test_reprocessing_same_manifest_is_idempotent(self) -> None:
        """Processing the same manifest twice is prevented by state tracking."""
        manifests = [_manifest(run_id="run-1", dt="2024-06-15")]
        fake_state = FakeStateStore()

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=manifests),
            patch(_STATE, return_value=fake_state),
            patch(_CATALOG, return_value=MagicMock()),
            patch(_LOAD_MARKETS_REF, new_callable=AsyncMock, return_value=_fake_markets_lookup()),
            patch(
                _PROCESS_CHUNKED,
                new_callable=AsyncMock,
                return_value=FakeProcessingResult(),
            ),
        ):
            # First run
            result1 = runner.invoke(
                app,
                ["process", "--platform", "polymarket", "--entity", "trades", "--dt", "2024-06-15"],
                env=_base_env(),
            )

        assert result1.exit_code == 0
        assert fake_state.is_processed("run-1")

        # Second run — same manifests discovered but already processed
        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=manifests),
            patch(_STATE, return_value=fake_state),
            patch(_PROCESS_CHUNKED, new_callable=AsyncMock) as mock_process,
        ):
            result2 = runner.invoke(
                app,
                ["process", "--platform", "polymarket", "--entity", "trades", "--dt", "2024-06-15"],
                env=_base_env(),
            )

        assert result2.exit_code == 0
        assert "No unprocessed manifests remaining" in result2.output
        mock_process.assert_not_awaited()

    def test_dry_run_shows_snapshot_selection_for_catalog_entity(self) -> None:
        """Dry run output reflects snapshot/delta selection for catalog entities."""
        t0 = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        manifests = [
            _manifest(run_id="delta-1", dt="2024-06-15", entity="markets", snapshot_type="delta", generated_at=t0),
            _manifest(run_id="snap-1", dt="2024-06-15", entity="markets", snapshot_type="snapshot", generated_at=t0 + timedelta(hours=1)),
        ]
        fake_state = FakeStateStore()

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=manifests),
            patch(_STATE, return_value=fake_state),
        ):
            result = runner.invoke(
                app,
                [
                    "process",
                    "--platform", "polymarket",
                    "--entity", "markets",
                    "--dt", "2024-06-15",
                    "--dry-run",
                ],
                env=_base_env(),
            )

        assert result.exit_code == 0
        assert "1 superseded by snapshot" in result.output
        assert "snap-1" in result.output
        assert "[snapshot]" in result.output


# ---------------------------------------------------------------------------
# Test: --closed-days-only flag
# ---------------------------------------------------------------------------


class TestClosedDaysOnly:
    def test_closed_days_only_clamps_end_date_to_yesterday(self) -> None:
        """--closed-days-only clamps end date so today is excluded."""
        from datetime import date as dt_date

        today = dt_date.today().isoformat()
        yesterday = (dt_date.today() - timedelta(days=1)).isoformat()

        m = _manifest(run_id="run-1", dt=yesterday)
        fake_state = FakeStateStore()

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(
                _DISCOVER, new_callable=AsyncMock, return_value=[m]
            ) as mock_discover,
            patch(_STATE, return_value=fake_state),
            patch(_CATALOG, return_value=MagicMock()),
            patch(_LOAD_MARKETS_REF, new_callable=AsyncMock, return_value=_fake_markets_lookup()),
            patch(
                _PROCESS_CHUNKED,
                new_callable=AsyncMock,
                return_value=FakeProcessingResult(),
            ),
        ):
            result = runner.invoke(
                app,
                [
                    "process",
                    "--platform", "polymarket",
                    "--entity", "trades",
                    "--start-date", yesterday,
                    "--end-date", today,
                    "--closed-days-only",
                ],
                env=_base_env(),
            )

        assert result.exit_code == 0
        # discover_manifests should be called with clamped end_date
        call_kwargs = mock_discover.call_args
        assert call_kwargs.kwargs["end_date"] == yesterday
        assert "Clamping end date" in result.output

    def test_closed_days_only_skips_when_start_is_today(self) -> None:
        """--closed-days-only with --dt today produces no processing."""
        from datetime import date as dt_date

        today = dt_date.today().isoformat()

        with patch(_LOGGING):
            result = runner.invoke(
                app,
                [
                    "process",
                    "--platform", "polymarket",
                    "--entity", "trades",
                    "--dt", today,
                    "--closed-days-only",
                ],
                env=_base_env(),
            )

        assert result.exit_code == 0
        assert "No closed days to process" in result.output

    def test_closed_days_only_processes_past_dates_normally(self) -> None:
        """--closed-days-only with all-past dates processes normally."""
        m = _manifest(run_id="run-1", dt="2024-06-15")
        fake_state = FakeStateStore()

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=[m]),
            patch(_STATE, return_value=fake_state),
            patch(_CATALOG, return_value=MagicMock()),
            patch(_LOAD_MARKETS_REF, new_callable=AsyncMock, return_value=_fake_markets_lookup()),
            patch(
                _PROCESS_CHUNKED,
                new_callable=AsyncMock,
                return_value=FakeProcessingResult(),
            ) as mock_process,
        ):
            result = runner.invoke(
                app,
                [
                    "process",
                    "--platform", "polymarket",
                    "--entity", "trades",
                    "--dt", "2024-06-15",
                    "--closed-days-only",
                ],
                env=_base_env(),
            )

        assert result.exit_code == 0
        mock_process.assert_awaited_once()
        assert "Clamping" not in result.output
        assert "No closed days" not in result.output

    def test_closed_days_only_with_future_start_date(self) -> None:
        """--closed-days-only with a future start date skips entirely."""
        with patch(_LOGGING):
            result = runner.invoke(
                app,
                [
                    "process",
                    "--platform", "polymarket",
                    "--entity", "trades",
                    "--dt", "2099-12-31",
                    "--closed-days-only",
                ],
                env=_base_env(),
            )

        assert result.exit_code == 0
        assert "No closed days to process" in result.output


# ---------------------------------------------------------------------------
# Test: silver catchup command
# ---------------------------------------------------------------------------


class FakeStateStoreWithDates(FakeStateStore):
    """FakeStateStore that also tracks dates for catchup tests."""

    def __init__(self, latest_date: str | None = None) -> None:
        super().__init__()
        self._latest_date = latest_date

    def latest_processed_date(self) -> str | None:
        return self._latest_date


class TestCatchup:
    def test_catchup_auto_detects_latest_date(self) -> None:
        """Catchup discovers manifests from latest processed date."""
        manifests = [_manifest(run_id="run-new", dt="2024-06-16")]
        fake_state = FakeStateStoreWithDates(latest_date="2024-06-15")

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(
                _DISCOVER, new_callable=AsyncMock, return_value=manifests,
            ) as mock_discover,
            patch(_STATE, return_value=fake_state),
            patch(_CATALOG, return_value=MagicMock()),
            patch(_LOAD_MARKETS_REF, new_callable=AsyncMock, return_value=_fake_markets_lookup()),
            patch(
                _PROCESS_CHUNKED,
                new_callable=AsyncMock,
                return_value=FakeProcessingResult(),
            ) as mock_process,
        ):
            result = runner.invoke(
                app,
                ["catchup", "--platform", "polymarket", "--entity", "trades"],
                env=_base_env(),
            )

        assert result.exit_code == 0
        assert "Latest processed date: 2024-06-15" in result.output
        # discover_manifests should start from the latest date
        call_kwargs = mock_discover.call_args.kwargs
        assert call_kwargs["start_date"] == "2024-06-15"
        mock_process.assert_awaited_once()

    def test_catchup_no_prior_state_starts_from_beginning(self) -> None:
        """Catchup with no prior state starts from 2022-01-01."""
        fake_state = FakeStateStoreWithDates(latest_date=None)

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(
                _DISCOVER, new_callable=AsyncMock, return_value=[],
            ) as mock_discover,
            patch(_STATE, return_value=fake_state),
        ):
            result = runner.invoke(
                app,
                ["catchup", "--platform", "polymarket", "--entity", "trades"],
                env=_base_env(),
            )

        assert result.exit_code == 0
        assert "starting from 2022-01-01" in result.output
        call_kwargs = mock_discover.call_args.kwargs
        assert call_kwargs["start_date"] == "2022-01-01"

    def test_catchup_from_date_override(self) -> None:
        """--from-date overrides auto-detection."""
        fake_state = FakeStateStoreWithDates(latest_date="2024-06-15")

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(
                _DISCOVER, new_callable=AsyncMock, return_value=[],
            ) as mock_discover,
            patch(_STATE, return_value=fake_state),
        ):
            result = runner.invoke(
                app,
                [
                    "catchup",
                    "--platform", "polymarket",
                    "--entity", "trades",
                    "--from-date", "2024-01-01",
                ],
                env=_base_env(),
            )

        assert result.exit_code == 0
        assert "Using override start date: 2024-01-01" in result.output
        call_kwargs = mock_discover.call_args.kwargs
        assert call_kwargs["start_date"] == "2024-01-01"

    def test_catchup_all_processed_shows_up_to_date(self) -> None:
        """Catchup with all manifests already processed shows up-to-date message."""
        manifests = [_manifest(run_id="run-1", dt="2024-06-15")]
        fake_state = FakeStateStoreWithDates(latest_date="2024-06-15")
        fake_state._processed.add("run-1")

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=manifests),
            patch(_STATE, return_value=fake_state),
        ):
            result = runner.invoke(
                app,
                ["catchup", "--platform", "polymarket", "--entity", "trades"],
                env=_base_env(),
            )

        assert result.exit_code == 0
        assert "up to date" in result.output

    def test_catchup_dry_run(self) -> None:
        """Catchup --dry-run shows manifests without processing."""
        manifests = [
            _manifest(run_id="run-1", dt="2024-06-15"),
            _manifest(run_id="run-2", dt="2024-06-16"),
        ]
        fake_state = FakeStateStoreWithDates(latest_date="2024-06-14")

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=manifests),
            patch(_STATE, return_value=fake_state),
            patch(_PROCESS_CHUNKED, new_callable=AsyncMock) as mock_process,
        ):
            result = runner.invoke(
                app,
                [
                    "catchup",
                    "--platform", "polymarket",
                    "--entity", "trades",
                    "--dry-run",
                ],
                env=_base_env(),
            )

        assert result.exit_code == 0
        assert "Dry run" in result.output
        assert "run-1" in result.output
        assert "run-2" in result.output
        mock_process.assert_not_awaited()

    def test_catchup_uses_chunked_for_trades(self) -> None:
        """Catchup uses chunked processing for stream entities."""
        manifests = [_manifest(run_id="run-1", dt="2024-06-15")]
        fake_state = FakeStateStoreWithDates(latest_date="2024-06-14")

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=manifests),
            patch(_STATE, return_value=fake_state),
            patch(_CATALOG, return_value=MagicMock()),
            patch(_LOAD_MARKETS_REF, new_callable=AsyncMock, return_value=_fake_markets_lookup()),
            patch(
                _PROCESS_CHUNKED,
                new_callable=AsyncMock,
                return_value=FakeProcessingResult(),
            ) as mock_chunked,
            patch(_PROCESS, new_callable=AsyncMock) as mock_batch,
        ):
            result = runner.invoke(
                app,
                ["catchup", "--platform", "polymarket", "--entity", "trades"],
                env=_base_env(),
            )

        assert result.exit_code == 0
        mock_chunked.assert_awaited_once()
        mock_batch.assert_not_awaited()

    def test_catchup_uses_batch_for_catalog_entities(self) -> None:
        """Catchup uses batch processing for catalog entities (markets)."""
        manifests = [_manifest(run_id="run-1", dt="2024-06-15", entity="markets")]
        fake_state = FakeStateStoreWithDates(latest_date="2024-06-14")

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=manifests),
            patch(_STATE, return_value=fake_state),
            patch(_CATALOG, return_value=MagicMock()),
            patch(
                _PROCESS,
                new_callable=AsyncMock,
                return_value=FakeProcessingResult(),
            ) as mock_batch,
            patch(_PROCESS_CHUNKED, new_callable=AsyncMock) as mock_chunked,
        ):
            result = runner.invoke(
                app,
                ["catchup", "--platform", "polymarket", "--entity", "markets"],
                env=_base_env(),
            )

        assert result.exit_code == 0
        mock_batch.assert_awaited_once()
        mock_chunked.assert_not_awaited()
