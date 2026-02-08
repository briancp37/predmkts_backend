"""Tests for Silver processing orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prediction_data.silver.processor import (
    ProcessingError,
    ProcessingResult,
    _build_namespace,
    process_manifest,
    process_manifest_chunked,
)
from prediction_data.silver.quality import QualityCheckError
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
        assert result.quality_checks_passed >= 1

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
# process_manifest — append_only mode
# ---------------------------------------------------------------------------


class TestProcessManifestAppendOnly:
    @pytest.mark.asyncio
    async def test_append_only_calls_write_not_merge(self) -> None:
        """append_only=True should call write_to_iceberg instead of merge_to_iceberg."""
        manifest = _make_manifest()
        records = _raw_market_records(3)
        read_result = ReadResult(
            records=records, records_read=3, files_read=1, errors=0,
        )

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
            ),
            patch(
                "prediction_data.silver.processor.write_to_iceberg",
                return_value=write_result,
            ) as mock_append,
            patch(
                "prediction_data.silver.processor.merge_to_iceberg",
                return_value=write_result,
            ) as mock_merge,
        ):
            result = await process_manifest(
                manifest, MagicMock(), MagicMock(), append_only=True
            )

        mock_append.assert_called_once()
        mock_merge.assert_not_called()
        assert result.rows_written == 3

    @pytest.mark.asyncio
    async def test_catalog_entity_defaults_to_append(self) -> None:
        """Catalog entities (markets, events) now default to append (write_to_iceberg).

        The Gold layer handles deduplication at read time. Use --merge flag for
        legacy upsert behavior when needed.
        """
        manifest = _make_manifest()  # defaults to entity="markets"
        records = _raw_market_records(3)
        read_result = ReadResult(
            records=records, records_read=3, files_read=1, errors=0,
        )

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
            ),
            patch(
                "prediction_data.silver.processor.write_to_iceberg",
                return_value=write_result,
            ) as mock_append,
            patch(
                "prediction_data.silver.processor.merge_to_iceberg",
                return_value=write_result,
            ) as mock_merge,
        ):
            result = await process_manifest(manifest, MagicMock(), MagicMock())

        mock_append.assert_called_once()
        mock_merge.assert_not_called()

    @pytest.mark.asyncio
    async def test_stream_entity_defaults_to_append(self) -> None:
        """Stream entities (trades, order_filled) should default to write_to_iceberg."""
        from prediction_data.silver.polymarket.markets_reference import (
            MarketSide,
            MarketsReferenceLookup,
        )

        manifest = _make_manifest(platform="polymarket", entity="trades")
        records = _raw_order_filled_records(2)
        read_result = ReadResult(
            records=records, records_read=2, files_read=1, errors=0,
        )

        write_result = WriteResult(
            namespace="silver_polymarket",
            table_name="trades",
            rows_written=2,
            snapshot_id=42,
            duration_seconds=0.1,
        )

        mock_lookup = MarketsReferenceLookup()
        mock_lookup._lookup = {
            "token-0": MarketSide(market_id="market-A", side="token1"),
            "token-1": MarketSide(market_id="market-B", side="token2"),
        }

        with (
            patch(
                "prediction_data.silver.processor.read_manifest_data",
                new_callable=AsyncMock,
                return_value=read_result,
            ),
            patch(
                "prediction_data.silver.processor.write_to_iceberg",
                return_value=write_result,
            ) as mock_append,
            patch(
                "prediction_data.silver.processor.merge_to_iceberg",
                return_value=write_result,
            ) as mock_merge,
            patch(
                "prediction_data.silver.polymarket.markets_reference.load_markets_reference",
                new_callable=AsyncMock,
                return_value=mock_lookup,
            ),
        ):
            result = await process_manifest(
                manifest, MagicMock(), MagicMock(), skip_quality_checks=True
            )

        mock_append.assert_called_once()
        mock_merge.assert_not_called()


class TestProcessManifestOverwrite:
    @pytest.mark.asyncio
    async def test_overwrite_calls_overwrite_not_merge(self) -> None:
        """overwrite=True should call overwrite_to_iceberg instead of merge."""
        manifest = _make_manifest()
        records = _raw_market_records(3)
        read_result = ReadResult(
            records=records, records_read=3, files_read=1, errors=0,
        )

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
            ),
            patch(
                "prediction_data.silver.processor.overwrite_to_iceberg",
                return_value=write_result,
            ) as mock_overwrite,
            patch(
                "prediction_data.silver.processor.merge_to_iceberg",
                return_value=write_result,
            ) as mock_merge,
        ):
            result = await process_manifest(
                manifest, MagicMock(), MagicMock(), overwrite=True
            )

        mock_overwrite.assert_called_once()
        mock_merge.assert_not_called()
        assert result.rows_written == 3

    @pytest.mark.asyncio
    async def test_overwrite_not_used_by_default(self) -> None:
        """Default should call write_to_iceberg (append), not overwrite."""
        manifest = _make_manifest()
        records = _raw_market_records(3)
        read_result = ReadResult(
            records=records, records_read=3, files_read=1, errors=0,
        )

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
            ),
            patch(
                "prediction_data.silver.processor.overwrite_to_iceberg",
                return_value=write_result,
            ) as mock_overwrite,
            patch(
                "prediction_data.silver.processor.write_to_iceberg",
                return_value=write_result,
            ) as mock_append,
        ):
            await process_manifest(manifest, MagicMock(), MagicMock())

        mock_append.assert_called_once()
        mock_overwrite.assert_not_called()


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
        ), pytest.raises(ProcessingError, match="Failed to read"):
            await process_manifest(manifest, MagicMock(), MagicMock())

    @pytest.mark.asyncio
    async def test_empty_records_raises_processing_error(self) -> None:
        manifest = _make_manifest()
        read_result = ReadResult(records=[], records_read=0, files_read=1, errors=0)

        with patch(
            "prediction_data.silver.processor.read_manifest_data",
            new_callable=AsyncMock,
            return_value=read_result,
        ), pytest.raises(ProcessingError, match="No records read"):
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
            ),pytest.raises(ProcessingError, match="Failed to write")
        ):
            await process_manifest(manifest, MagicMock(), MagicMock())

    @pytest.mark.asyncio
    async def test_quality_check_failure_raises_processing_error(self) -> None:
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
                "prediction_data.silver.processor.run_quality_checks",
                side_effect=QualityCheckError("non_null failed"),
            ),pytest.raises(ProcessingError, match="Quality check failed")
        ):
            await process_manifest(manifest, MagicMock(), MagicMock())

    @pytest.mark.asyncio
    async def test_quality_check_failure_prevents_write(self) -> None:
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
                "prediction_data.silver.processor.run_quality_checks",
                side_effect=QualityCheckError("non_null failed"),
            ),
            patch(
                "prediction_data.silver.processor.merge_to_iceberg",
            ) as mock_write,pytest.raises(ProcessingError)
        ):
            await process_manifest(manifest, MagicMock(), MagicMock())

        mock_write.assert_not_called()

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
            ),pytest.raises(ProcessingError, match="All records failed normalization")
        ):
            await process_manifest(manifest, MagicMock(), MagicMock())


# ---------------------------------------------------------------------------
# ProcessingResult dataclass
# ---------------------------------------------------------------------------


class TestQualityLogging:
    """Test that quality check results are logged with structured metrics."""

    @pytest.mark.asyncio
    async def test_quality_results_logged_on_success(self) -> None:
        manifest = _make_manifest()
        records = _raw_market_records(3)
        read_result = ReadResult(
            records=records, records_read=3, files_read=1, errors=0,
        )
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
            ),
            patch(
                "prediction_data.silver.processor.merge_to_iceberg",
                return_value=write_result,
            ),
            patch(
                "prediction_data.silver.processor.logger",
            ) as mock_logger,
        ):
            await process_manifest(manifest, MagicMock(), MagicMock())

        # Find the processing_quality_done log call
        quality_calls = [
            call
            for call in mock_logger.info.call_args_list
            if call.args and call.args[0] == "processing_quality_done"
        ]
        assert len(quality_calls) == 1
        kwargs = quality_calls[0].kwargs
        assert "checks_passed" in kwargs
        assert kwargs["checks_passed"] >= 1
        assert kwargs["platform"] == "polymarket"
        assert kwargs["entity"] == "markets"

    @pytest.mark.asyncio
    async def test_quality_failure_logged_before_abort(self) -> None:
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
                "prediction_data.silver.processor.run_quality_checks",
                side_effect=QualityCheckError("non_null failed"),
            ),
            patch(
                "prediction_data.silver.processor.logger",
            ) as mock_logger,pytest.raises(ProcessingError)
        ):
            await process_manifest(manifest, MagicMock(), MagicMock())

        # Quality done log should NOT appear (failure aborts before it)
        quality_done_calls = [
            call
            for call in mock_logger.info.call_args_list
            if call.args and call.args[0] == "processing_quality_done"
        ]
        assert len(quality_done_calls) == 0


# ---------------------------------------------------------------------------
# Late-arriving data
# ---------------------------------------------------------------------------


class TestLateArrivingData:
    """Test that late-arriving data (>7 days old) triggers a warning log."""

    @pytest.mark.asyncio
    async def test_late_data_logs_warning(self) -> None:
        """Data with event_ts >7 days old should emit a late_arriving_data warning."""
        manifest = _make_manifest(dt="2024-01-10")
        # Records with old updated_at so event_ts will be old
        records = [
            {
                "id": "market-old",
                "condition_id": "cond-old",
                "question": "Old market?",
                "description": "desc",
                "market_slug": "slug-old",
                "active": True,
                "closed": False,
                "tokens": [{"token_id": "t1-old", "outcome": "Yes"}],
                "updated_at": "2024-01-10T12:00:00Z",
                "end_date_iso": "2024-12-31T00:00:00Z",
            }
        ]
        read_result = ReadResult(
            records=records, records_read=1, files_read=1, errors=0,
        )
        write_result = WriteResult(
            namespace="silver_polymarket",
            table_name="markets",
            rows_written=1,
            snapshot_id=55,
            duration_seconds=0.05,
        )

        with (
            patch(
                "prediction_data.silver.processor.read_manifest_data",
                new_callable=AsyncMock,
                return_value=read_result,
            ),
            patch(
                "prediction_data.silver.processor.merge_to_iceberg",
                return_value=write_result,
            ),
            patch(
                "prediction_data.silver.processor.logger",
            ) as mock_logger,
        ):
            result = await process_manifest(manifest, MagicMock(), MagicMock())

        # Should have logged a late_arriving_data warning
        late_calls = [
            call
            for call in mock_logger.warning.call_args_list
            if call.args and call.args[0] == "late_arriving_data"
        ]
        assert len(late_calls) == 1
        kwargs = late_calls[0].kwargs
        assert kwargs["late_record_count"] == 1
        assert kwargs["days_old"] > 7

    @pytest.mark.asyncio
    async def test_late_data_still_written_successfully(self) -> None:
        """Late-arriving data should still be written (warning only, not a blocker)."""
        manifest = _make_manifest(dt="2024-01-10")
        records = [
            {
                "id": "market-late",
                "condition_id": "cond-late",
                "question": "Late market?",
                "description": "desc",
                "market_slug": "slug-late",
                "active": True,
                "closed": False,
                "tokens": [{"token_id": "t1-late", "outcome": "Yes"}],
                "updated_at": "2024-01-10T12:00:00Z",
                "end_date_iso": "2024-12-31T00:00:00Z",
            }
        ]
        read_result = ReadResult(
            records=records, records_read=1, files_read=1, errors=0,
        )
        write_result = WriteResult(
            namespace="silver_polymarket",
            table_name="markets",
            rows_written=1,
            snapshot_id=57,
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

        # Data should still be written despite being late
        assert result.rows_written == 1
        mock_write.assert_called_once()


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
            rows_inserted=90,
            rows_updated=5,
            snapshot_id=42,
            quality_checks_passed=3,
            duration_seconds=1.5,
        )
        assert r.platform == "polymarket"
        assert r.rows_read == 100
        assert r.duplicates_dropped == 5


# ---------------------------------------------------------------------------
# Markets reference auto-loading for trades
# ---------------------------------------------------------------------------


def _raw_order_filled_records(n: int = 2) -> list[dict]:
    """Raw Bronze OrderFilledEvent records for testing trades processing."""
    return [
        {
            "id": f"fill-{i}",
            "transactionHash": f"0xabc{i}",
            "timestamp": "1718467200",
            "maker": f"0xmaker{i}",
            "taker": f"0xtaker{i}",
            "makerAssetId": f"token-{i}",
            "takerAssetId": "0",
            "makerAmountFilled": "1000000",
            "takerAmountFilled": "500000",
        }
        for i in range(n)
    ]


class TestMarketsReferenceLookupAutoLoad:
    """Test that process_manifest auto-loads MarketsReferenceLookup for polymarket/trades."""

    @pytest.mark.asyncio
    async def test_trades_auto_loads_markets_reference(self) -> None:
        """Processing polymarket/trades should automatically load and inject the lookup."""
        from prediction_data.silver.polymarket.markets_reference import (
            MarketSide,
            MarketsReferenceLookup,
        )

        manifest = _make_manifest(platform="polymarket", entity="trades")
        records = _raw_order_filled_records(2)
        read_result = ReadResult(
            records=records, records_read=2, files_read=1, errors=0,
        )
        write_result = WriteResult(
            namespace="silver_polymarket",
            table_name="trades",
            rows_written=2,
            snapshot_id=100,
            duration_seconds=0.1,
        )

        # Build a mock lookup that resolves our test token IDs
        mock_lookup = MarketsReferenceLookup()
        mock_lookup._lookup = {
            "token-0": MarketSide(market_id="market-A", side="token1"),
            "token-1": MarketSide(market_id="market-B", side="token2"),
        }

        with (
            patch(
                "prediction_data.silver.processor.read_manifest_data",
                new_callable=AsyncMock,
                return_value=read_result,
            ),
            patch(
                "prediction_data.silver.processor.write_to_iceberg",
                return_value=write_result,
            ),
            patch(
                "prediction_data.silver.polymarket.markets_reference.load_markets_reference",
                new_callable=AsyncMock,
                return_value=mock_lookup,
            ) as mock_load,
        ):
            result = await process_manifest(
                manifest, MagicMock(), MagicMock(), skip_quality_checks=True
            )

        assert result.rows_written == 2
        assert result.platform == "polymarket"
        assert result.entity == "trades"
        mock_load.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_markets_reference_load_failure_raises_processing_error(self) -> None:
        """If markets reference loading fails, should raise ProcessingError."""
        manifest = _make_manifest(platform="polymarket", entity="trades")
        records = _raw_order_filled_records(1)
        read_result = ReadResult(
            records=records, records_read=1, files_read=1, errors=0,
        )

        with (
            patch(
                "prediction_data.silver.processor.read_manifest_data",
                new_callable=AsyncMock,
                return_value=read_result,
            ),
            patch(
                "prediction_data.silver.polymarket.markets_reference.load_markets_reference",
                new_callable=AsyncMock,
                side_effect=RuntimeError("S3 unavailable"),
            ),pytest.raises(ProcessingError, match="Failed to load markets reference")
        ):
            await process_manifest(
                manifest, MagicMock(), MagicMock(), skip_quality_checks=True
            )

    @pytest.mark.asyncio
    async def test_empty_markets_reference_raises_processing_error(self) -> None:
        """If no markets data exists, should raise ProcessingError."""
        from prediction_data.silver.polymarket.markets_reference import (
            MarketsReferenceLookup,
        )

        manifest = _make_manifest(platform="polymarket", entity="trades")
        records = _raw_order_filled_records(1)
        read_result = ReadResult(
            records=records, records_read=1, files_read=1, errors=0,
        )

        empty_lookup = MarketsReferenceLookup()

        with (
            patch(
                "prediction_data.silver.processor.read_manifest_data",
                new_callable=AsyncMock,
                return_value=read_result,
            ),
            patch(
                "prediction_data.silver.polymarket.markets_reference.load_markets_reference",
                new_callable=AsyncMock,
                return_value=empty_lookup,
            ),pytest.raises(ProcessingError, match="Markets reference lookup is empty")
        ):
            await process_manifest(
                manifest, MagicMock(), MagicMock(), skip_quality_checks=True
            )

    @pytest.mark.asyncio
    async def test_non_trades_entities_skip_markets_reference(self) -> None:
        """Markets and events should NOT trigger markets reference loading."""
        manifest = _make_manifest(platform="polymarket", entity="markets")
        records = _raw_market_records(2)
        read_result = ReadResult(
            records=records, records_read=2, files_read=1, errors=0,
        )
        write_result = WriteResult(
            namespace="silver_polymarket",
            table_name="markets",
            rows_written=2,
            snapshot_id=99,
            duration_seconds=0.1,
        )

        with (
            patch(
                "prediction_data.silver.processor.read_manifest_data",
                new_callable=AsyncMock,
                return_value=read_result,
            ),
            patch(
                "prediction_data.silver.processor.merge_to_iceberg",
                return_value=write_result,
            ),
            patch(
                "prediction_data.silver.polymarket.markets_reference.load_markets_reference",
                new_callable=AsyncMock,
            ) as mock_load,
        ):
            result = await process_manifest(manifest, MagicMock(), MagicMock())

        assert result.rows_written == 2
        mock_load.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_trades_normalization_uses_loaded_lookup(self) -> None:
        """Verify that normalized trades contain market_id resolved via the lookup."""
        from prediction_data.silver.polymarket.markets_reference import (
            MarketSide,
            MarketsReferenceLookup,
        )

        manifest = _make_manifest(platform="polymarket", entity="trades")
        records = _raw_order_filled_records(1)
        read_result = ReadResult(
            records=records, records_read=1, files_read=1, errors=0,
        )
        write_result = WriteResult(
            namespace="silver_polymarket",
            table_name="trades",
            rows_written=1,
            snapshot_id=101,
            duration_seconds=0.1,
        )

        mock_lookup = MarketsReferenceLookup()
        mock_lookup._lookup = {
            "token-0": MarketSide(market_id="resolved-market-123", side="token1"),
        }

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
            patch(
                "prediction_data.silver.polymarket.markets_reference.load_markets_reference",
                new_callable=AsyncMock,
                return_value=mock_lookup,
            ),
        ):
            await process_manifest(
                manifest, MagicMock(), MagicMock(), skip_quality_checks=True
            )

        # Verify the normalized records passed to write_to_iceberg have resolved market IDs
        written_records = mock_write.call_args[0][0]
        assert len(written_records) == 1
        assert written_records[0]["platform_market_id"] == "resolved-market-123"

    @pytest.mark.asyncio
    async def test_trades_logs_markets_reference_loading(self) -> None:
        """Verify structured logging for markets reference load steps."""
        from prediction_data.silver.polymarket.markets_reference import (
            MarketSide,
            MarketsReferenceLookup,
        )

        manifest = _make_manifest(platform="polymarket", entity="trades")
        records = _raw_order_filled_records(1)
        read_result = ReadResult(
            records=records, records_read=1, files_read=1, errors=0,
        )
        write_result = WriteResult(
            namespace="silver_polymarket",
            table_name="trades",
            rows_written=1,
            snapshot_id=102,
            duration_seconds=0.1,
        )

        mock_lookup = MarketsReferenceLookup()
        mock_lookup._lookup = {
            "token-0": MarketSide(market_id="market-X", side="token1"),
        }

        with (
            patch(
                "prediction_data.silver.processor.read_manifest_data",
                new_callable=AsyncMock,
                return_value=read_result,
            ),
            patch(
                "prediction_data.silver.processor.write_to_iceberg",
                return_value=write_result,
            ),
            patch(
                "prediction_data.silver.polymarket.markets_reference.load_markets_reference",
                new_callable=AsyncMock,
                return_value=mock_lookup,
            ),
            patch(
                "prediction_data.silver.processor.logger",
            ) as mock_logger,
        ):
            await process_manifest(
                manifest, MagicMock(), MagicMock(), skip_quality_checks=True
            )

        # Check for loading_markets_reference log
        loading_calls = [
            call
            for call in mock_logger.info.call_args_list
            if call.args and call.args[0] == "loading_markets_reference"
        ]
        assert len(loading_calls) == 1

        # Check for markets_reference_loaded log
        loaded_calls = [
            call
            for call in mock_logger.info.call_args_list
            if call.args and call.args[0] == "markets_reference_loaded"
        ]
        assert len(loaded_calls) == 1
        kwargs = loaded_calls[0].kwargs
        assert "unique_markets" in kwargs
        assert "lookup_entries" in kwargs


# ---------------------------------------------------------------------------
# process_manifest_chunked — file-by-file processing for stream entities
# ---------------------------------------------------------------------------


def _make_file_ref(key: str = "part-000.json.gz", bucket: str = "test-bucket") -> MagicMock:
    """Create a mock FileReference."""
    ref = MagicMock()
    ref.key = key
    ref.bucket = bucket
    return ref


def _make_manifest_with_files(
    platform: str = "polymarket",
    entity: str = "order_filled",
    dt: str = "2024-06-15",
    run_id: str = "run-abc-123",
    file_keys: list[str] | None = None,
) -> MagicMock:
    """Create a mock DiscoveredManifest with file references."""
    if file_keys is None:
        file_keys = ["part-000.json.gz"]
    m = MagicMock()
    m.platform = platform
    m.entity = entity
    m.dt = dt
    m.run_id = run_id
    m.manifest.files = [_make_file_ref(k) for k in file_keys]
    return m


class TestProcessManifestChunkedHappyPath:
    @pytest.mark.asyncio
    async def test_single_file_manifest(self) -> None:
        """Single-file manifest processes correctly."""
        from prediction_data.silver.polymarket.markets_reference import (
            MarketSide,
            MarketsReferenceLookup,
        )

        manifest = _make_manifest_with_files(
            entity="order_filled",
            file_keys=["part-000.json.gz"],
        )
        records = _raw_order_filled_records(3)

        mock_lookup = MarketsReferenceLookup()
        mock_lookup._lookup = {
            f"token-{i}": MarketSide(market_id=f"market-{i}", side="token1")
            for i in range(3)
        }

        write_result = WriteResult(
            namespace="silver_polymarket",
            table_name="trades",
            rows_written=3,
            snapshot_id=42,
            duration_seconds=0.1,
        )

        with (
            patch(
                "prediction_data.silver.processor.read_single_file",
                return_value=records,
            ) as mock_read,
            patch(
                "prediction_data.silver.processor.write_to_iceberg",
                return_value=write_result,
            ) as mock_write,
        ):
            result = await process_manifest_chunked(
                manifest, MagicMock(), MagicMock(),
                skip_quality_checks=True,
                markets_lookup=mock_lookup,
            )

        assert result.rows_read == 3
        assert result.rows_written == 3
        assert result.snapshot_id == 42
        mock_read.assert_called_once()
        mock_write.assert_called_once()

    @pytest.mark.asyncio
    async def test_multi_file_manifest(self) -> None:
        """Multi-file manifest processes each file independently."""
        from prediction_data.silver.polymarket.markets_reference import (
            MarketSide,
            MarketsReferenceLookup,
        )

        manifest = _make_manifest_with_files(
            entity="order_filled",
            file_keys=["part-000.json.gz", "part-001.json.gz"],
        )

        records_file0 = _raw_order_filled_records(2)
        records_file1 = [
            {
                "id": "fill-10",
                "transactionHash": "0xabc10",
                "timestamp": "1718467200",
                "maker": "0xmaker10",
                "taker": "0xtaker10",
                "makerAssetId": "token-10",
                "takerAssetId": "0",
                "makerAmountFilled": "1000000",
                "takerAmountFilled": "500000",
            }
        ]

        mock_lookup = MarketsReferenceLookup()
        mock_lookup._lookup = {
            "token-0": MarketSide(market_id="market-A", side="token1"),
            "token-1": MarketSide(market_id="market-B", side="token1"),
            "token-10": MarketSide(market_id="market-C", side="token1"),
        }

        write_result_0 = WriteResult(
            namespace="silver_polymarket", table_name="trades",
            rows_written=2, snapshot_id=42, duration_seconds=0.1,
        )
        write_result_1 = WriteResult(
            namespace="silver_polymarket", table_name="trades",
            rows_written=1, snapshot_id=43, duration_seconds=0.05,
        )

        call_count = 0

        def fake_read(s3, file_ref):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return records_file0
            return records_file1

        write_calls = [write_result_0, write_result_1]
        write_idx = 0

        def fake_write(records, catalog, ns, table):
            nonlocal write_idx
            result = write_calls[write_idx]
            write_idx += 1
            return result

        with (
            patch("prediction_data.silver.processor.read_single_file", side_effect=fake_read),
            patch("prediction_data.silver.processor.write_to_iceberg", side_effect=fake_write) as mock_write,
        ):
            result = await process_manifest_chunked(
                manifest, MagicMock(), MagicMock(),
                skip_quality_checks=True,
                markets_lookup=mock_lookup,
            )

        assert result.rows_read == 3
        assert result.rows_written == 3
        assert result.snapshot_id == 43  # last snapshot
        assert mock_write.call_count == 2

    @pytest.mark.asyncio
    async def test_always_uses_append(self) -> None:
        """Chunked processing always uses write_to_iceberg (append), never merge."""
        from prediction_data.silver.polymarket.markets_reference import (
            MarketSide,
            MarketsReferenceLookup,
        )

        manifest = _make_manifest_with_files(entity="order_filled")
        records = _raw_order_filled_records(2)

        mock_lookup = MarketsReferenceLookup()
        mock_lookup._lookup = {
            "token-0": MarketSide(market_id="market-A", side="token1"),
            "token-1": MarketSide(market_id="market-B", side="token1"),
        }

        write_result = WriteResult(
            namespace="silver_polymarket", table_name="trades",
            rows_written=2, snapshot_id=42, duration_seconds=0.1,
        )

        with (
            patch("prediction_data.silver.processor.read_single_file", return_value=records),
            patch("prediction_data.silver.processor.write_to_iceberg", return_value=write_result) as mock_append,
            patch("prediction_data.silver.processor.merge_to_iceberg") as mock_merge,
        ):
            await process_manifest_chunked(
                manifest, MagicMock(), MagicMock(),
                skip_quality_checks=True,
                markets_lookup=mock_lookup,
            )

        mock_append.assert_called_once()
        mock_merge.assert_not_called()


class TestProcessManifestChunkedErrors:
    @pytest.mark.asyncio
    async def test_empty_files_raises(self) -> None:
        """Manifest with no files should raise ProcessingError."""
        manifest = _make_manifest_with_files(entity="order_filled")
        manifest.manifest.files = []

        with pytest.raises(ProcessingError, match="has no files"):
            await process_manifest_chunked(manifest, MagicMock(), MagicMock())

    @pytest.mark.asyncio
    async def test_file_read_failure_continues(self) -> None:
        """If one file fails to read, processing continues with the next."""
        from prediction_data.silver.polymarket.markets_reference import (
            MarketSide,
            MarketsReferenceLookup,
        )

        manifest = _make_manifest_with_files(
            entity="order_filled",
            file_keys=["bad-file.json.gz", "good-file.json.gz"],
        )

        good_records = _raw_order_filled_records(1)

        mock_lookup = MarketsReferenceLookup()
        mock_lookup._lookup = {
            "token-0": MarketSide(market_id="market-A", side="token1"),
        }

        call_count = 0
        def fake_read(s3, file_ref):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("S3 error")
            return good_records

        write_result = WriteResult(
            namespace="silver_polymarket", table_name="trades",
            rows_written=1, snapshot_id=42, duration_seconds=0.05,
        )

        with (
            patch("prediction_data.silver.processor.read_single_file", side_effect=fake_read),
            patch("prediction_data.silver.processor.write_to_iceberg", return_value=write_result),
        ):
            result = await process_manifest_chunked(
                manifest, MagicMock(), MagicMock(),
                skip_quality_checks=True,
                markets_lookup=mock_lookup,
            )

        assert result.rows_written == 1
        assert result.rows_read == 1
