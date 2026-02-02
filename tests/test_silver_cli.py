"""Tests for Silver CLI commands (process, backfill, dry-run, state tracking)."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from prediction_data.cli.silver import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeDiscoveredManifest:
    run_id: str
    platform: str
    entity: str
    dt: str


def _manifest(
    run_id: str = "run-1",
    platform: str = "polymarket",
    entity: str = "trades",
    dt: str = "2024-06-15",
) -> FakeDiscoveredManifest:
    return FakeDiscoveredManifest(run_id=run_id, platform=platform, entity=entity, dt=dt)


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
_STATE = "prediction_data.silver.state.SilverStateStore"
_CATALOG = "prediction_data.silver.catalog.get_catalog"
_S3 = "prediction_data.storage.S3Client"
_LOGGING = "prediction_data.core.logging.configure_logging"


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
            patch(
                _PROCESS,
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
        assert "10 rows written" in result.output
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
            patch(
                _PROCESS,
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

        async def process_side_effect(m: object, s3: object, catalog: object) -> FakeProcessingResult:
            if getattr(m, "run_id") == "run-1":
                raise ProcessingError("boom")
            return FakeProcessingResult()

        with (
            patch(_LOGGING),
            patch(_S3),
            patch(_DISCOVER, new_callable=AsyncMock, return_value=manifests),
            patch(_STATE, return_value=fake_state),
            patch(_CATALOG, return_value=MagicMock()),
            patch(_PROCESS, new_callable=AsyncMock, side_effect=process_side_effect),
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
            patch(_PROCESS, new_callable=AsyncMock) as mock_process,
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
            patch(
                _PROCESS,
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
            patch(
                _PROCESS,
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
