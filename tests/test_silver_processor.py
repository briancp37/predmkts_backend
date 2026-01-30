"""Tests for Silver processing orchestrator."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prediction_data.silver.processor import (
    ProcessingError,
    ProcessingResult,
    _build_namespace,
    process_manifest,
)
from prediction_data.silver.reader import ReadResult
from prediction_data.silver.writer import IcebergWriteError, WriteResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manifest(
    platform: str = "polymarket",
    entity: str = "markets",
    dt: str = "2024-06-15",
    run_id: str = "run-abc-123",
) -> MagicMock:
    m = MagicMock()
    m.platform = platform
    m.entity = entity
    m.dt = dt
    m.run_id = run_id
    return m


def _raw_market_records(n: int = 3) -> list[dict]:
    """Raw Bronze market records (pre-normalization)."""
    return [
        {
            "id": f"market-{i}",
            "condition_id": f"cond-{i}",
            "question": f"Will X happen? #{i}",
            "description": "desc",
            "market_slug": f"slug-{i}",
            "active": True,
            "closed": False,
            "tokens": [{"token_id": f"t1-{i}", "outcome": "Yes"}],
            "updated_at": f"2024-06-15T12:00:0{i}Z",
            "end_date_iso": "2024-12-31T00:00:00Z",
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# _build_namespace
# ---------------------------------------------------------------------------


class TestBuildNamespace:
    def test_polymarket(self) -> None:
        assert _build_namespace("polymarket") == "silver_polymarket"

    def test_kalshi(self) -> None:
        assert _build_namespace("kalshi") == "silver_kalshi"


# ---------------------------------------------------------------------------
# process_manifest — happy path
# ---------------------------------------------------------------------------


class TestProcessManifestHappyPath:
    @pytest.mark.asyncio
    async def test_full_pipeline(self) -> None:
        manifest = _make_manifest()
        records = _raw_market_records(3)
        read_result = ReadResult(
            records=records, records_read=3, files_read=1, errors=0,
        )

        mock_s3 = MagicMock()
        mock_catalog = MagicMock()

        write_result = WriteResult(
            namespace="silver_polymarket",
            table_name="markets",
            rows_written=3,
            snapshot_id=42,
            duration_seconds=0.1,
        )

        with (
            patch(
                "prediction_data.silver.processor.read_manifest_data",
                new_callable=AsyncMock,
                return_value=read_result,
            ) as mock_read,
            patch(
                "prediction_data.silver.processor.write_to_iceberg",
                return_value=write_result,
            ) as mock_write,
        ):
            result = await process_manifest(manifest, mock_s3, mock_catalog)

        assert isinstance(result, ProcessingResult)
        assert result.platform == "polymarket"
        assert result.entity == "markets"
        assert result.dt == "2024-06-15"
        assert result.run_id == "run-abc-123"
        assert result.rows_read == 3
        assert result.rows_written == 3
        assert result.snapshot_id == 42

        mock_read.assert_awaited_once_with(mock_s3, manifest)
        mock_write.assert_called_once()
        # Verify namespace mapping
        call_args = mock_write.call_args
        assert call_args[0][1] == mock_catalog
        assert call_args[0][2] == "silver_polymarket"
        assert call_args[0][3] == "markets"

    @pytest.mark.asyncio
    async def test_dedup_removes_duplicates(self) -> None:
        manifest = _make_manifest()
        # Two records with same dedup key (same id + updated_at)
        rec = _raw_market_records(1)[0]
        records = [rec, rec.copy()]
        read_result = ReadResult(
            records=records, records_read=2, files_read=1, errors=0,
        )

        write_result = WriteResult(
            namespace="silver_polymarket",
            table_name="markets",
            rows_written=1,
            snapshot_id=99,
            duration_seconds=0.05,
        )

        with (
            patch(
                "prediction_data.silver.processor.read_manifest_data",
                new_callable=AsyncMock,
                return_value=read_result,
            ),
            patch(
                "prediction_data.silver.processor.write_to_iceberg",
                return_value=write_result,
            ) as mock_write,
        ):
            result = await process_manifest(manifest, MagicMock(), MagicMock())

        assert result.duplicates_dropped == 1
        assert result.rows_after_dedup == 1
        # Writer receives 1 normalized record
        written_records = mock_write.call_args[0][0]
        assert len(written_records) == 1


# ---------------------------------------------------------------------------
# process_manifest — error handling
# ---------------------------------------------------------------------------


class TestProcessManifestErrors:
    @pytest.mark.asyncio
    async def test_read_failure_raises_processing_error(self) -> None:
        manifest = _make_manifest()

        with patch(
            "prediction_data.silver.processor.read_manifest_data",
            new_callable=AsyncMock,
            side_effect=RuntimeError("S3 down"),
        ):
            with pytest.raises(ProcessingError, match="Failed to read"):
                await process_manifest(manifest, MagicMock(), MagicMock())

    @pytest.mark.asyncio
    async def test_empty_records_raises_processing_error(self) -> None:
        manifest = _make_manifest()
        read_result = ReadResult(records=[], records_read=0, files_read=1, errors=0)

        with patch(
            "prediction_data.silver.processor.read_manifest_data",
            new_callable=AsyncMock,
            return_value=read_result,
        ):
            with pytest.raises(ProcessingError, match="No records read"):
                await process_manifest(manifest, MagicMock(), MagicMock())

    @pytest.mark.asyncio
    async def test_write_failure_raises_processing_error(self) -> None:
        manifest = _make_manifest()
        records = _raw_market_records(2)
        read_result = ReadResult(
            records=records, records_read=2, files_read=1, errors=0,
        )

        with (
            patch(
                "prediction_data.silver.processor.read_manifest_data",
                new_callable=AsyncMock,
                return_value=read_result,
            ),
            patch(
                "prediction_data.silver.processor.write_to_iceberg",
                side_effect=IcebergWriteError("schema mismatch"),
            ),
        ):
            with pytest.raises(ProcessingError, match="Failed to write"):
                await process_manifest(manifest, MagicMock(), MagicMock())

    @pytest.mark.asyncio
    async def test_all_normalization_failures_raises(self) -> None:
        manifest = _make_manifest()
        # Records that will fail normalization (missing required fields)
        bad_records = [{"garbage": True}, {"also_garbage": True}]
        read_result = ReadResult(
            records=bad_records, records_read=2, files_read=1, errors=0,
        )

        with (
            patch(
                "prediction_data.silver.processor.read_manifest_data",
                new_callable=AsyncMock,
                return_value=read_result,
            ),
        ):
            with pytest.raises(ProcessingError, match="All records failed normalization"):
                await process_manifest(manifest, MagicMock(), MagicMock())


# ---------------------------------------------------------------------------
# ProcessingResult dataclass
# ---------------------------------------------------------------------------


class TestProcessingResult:
    def test_fields(self) -> None:
        r = ProcessingResult(
            platform="polymarket",
            entity="trades",
            dt="2024-06-15",
            run_id="run-123",
            rows_read=100,
            rows_after_dedup=95,
            duplicates_dropped=5,
            rows_normalized=95,
            rows_written=95,
            snapshot_id=42,
            duration_seconds=1.5,
        )
        assert r.platform == "polymarket"
        assert r.rows_read == 100
        assert r.duplicates_dropped == 5
