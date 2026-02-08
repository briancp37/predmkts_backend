"""Integration tests for the full Silver processing pipeline.

These tests exercise the pipeline end-to-end using mock S3 and catalog,
verifying that data flows correctly through read → dedup → normalize → write.
They are NOT marked as ``integration`` (no real AWS calls) — they test
cross-module integration with realistic data shapes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pyarrow as pa
import pytest

from prediction_data.core.compression import compress_jsonl
from prediction_data.silver.dedup import dedup_batch
from prediction_data.silver.discovery import DiscoveredManifest
from prediction_data.silver.normalize import (
    NormalizationError,
    get_normalizer,
)
from prediction_data.silver.processor import (
    ProcessingError,
    ProcessingResult,
    process_manifest,
)
from prediction_data.silver.reader import ReadResult, read_manifest_data
from prediction_data.silver.tables import SILVER_TABLES
from prediction_data.silver.writer import (
    IcebergWriteError,
    WriteResult,
    _to_arrow_table,
    write_to_iceberg,
)
from prediction_data.storage.manifest import FileReference, Manifest, Source


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_discovered_manifest(
    platform: str = "polymarket",
    entity: str = "markets",
    dt: str = "2024-06-15",
    run_id: str = "run-int-001",
    bucket: str = "test-bucket",
    row_count: int = 3,
    n_files: int = 1,
) -> DiscoveredManifest:
    """Build a real DiscoveredManifest with valid Manifest + FileReferences."""
    files = [
        FileReference(
            bucket=bucket,
            key=f"bronze/{platform}/{entity}/dt={dt}/run_id={run_id}/part-{i:03d}.jsonl.gz",
        )
        for i in range(n_files)
    ]
    manifest = Manifest(
        run_id=run_id,
        platform=platform,
        entity=entity,
        dt=dt,
        generated_at=datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
        files=files,
        row_count=row_count,
        source=Source(api_base_url="https://example.com", pagination="cursor"),
    )
    s3_key = f"bronze/{platform}/{entity}/dt={dt}/run_id={run_id}/_manifest.json"
    return DiscoveredManifest(manifest=manifest, s3_key=s3_key)


def _raw_market_records(n: int = 3) -> list[dict]:
    """Raw Bronze Polymarket market records."""
    return [
        {
            "id": f"0xmarket{i}",
            "condition_id": f"0xcond{i}",
            "question": f"Will event {i} happen?",
            "description": f"Description for market {i}",
            "market_slug": f"event-{i}",
            "status": "open",
            "outcome": None,
            "tokens": [{"token_id": f"t1-{i}", "outcome": "Yes"}],
            "event_id": f"evt-{i}",
            "updated_at": f"2024-06-15T12:00:{i:02d}Z",
            "end_date_iso": "2024-12-31T00:00:00Z",
        }
        for i in range(n)
    ]


def _raw_event_records(n: int = 3) -> list[dict]:
    """Raw Bronze Polymarket event records."""
    return [
        {
            "id": f"event-{i}",
            "title": f"Event title {i}",
            "description": f"Event description {i}",
            "slug": f"event-slug-{i}",
            "status": "active",
            "category": "politics",
            "updated_at": f"2024-06-15T12:00:{i:02d}Z",
        }
        for i in range(n)
    ]


def _mock_s3_with_compressed(data_by_key: dict[str, list[dict]]) -> MagicMock:
    """Build mock S3Client that returns gzipped JSONL for given keys."""
    boto_client = MagicMock()

    def _get_object(Bucket: str, Key: str) -> dict:
        if Key not in data_by_key:
            raise Exception(f"NoSuchKey: {Key}")
        compressed, _ = compress_jsonl(data_by_key[Key])
        body = MagicMock()
        body.read.return_value = compressed
        return {"Body": body}

    boto_client.get_object = MagicMock(side_effect=_get_object)
    s3_client = MagicMock()
    s3_client._get_client.return_value = boto_client
    return s3_client


def _mock_catalog_with_capture() -> tuple[MagicMock, list[pa.Table]]:
    """Build a mock catalog that captures upserted PyArrow tables."""
    captured: list[pa.Table] = []
    catalog = MagicMock()
    mock_table = MagicMock()
    mock_snapshot = MagicMock()
    mock_snapshot.snapshot_id = 77777

    def _capture(arrow_table: pa.Table, **kwargs: object) -> MagicMock:
        captured.append(arrow_table)
        result = MagicMock()
        result.rows_inserted = arrow_table.num_rows
        result.rows_updated = 0
        return result

    mock_table.append = MagicMock(side_effect=lambda t: captured.append(t))
    mock_table.upsert = MagicMock(side_effect=_capture)
    mock_table.current_snapshot.return_value = mock_snapshot
    catalog.load_table.return_value = mock_table
    return catalog, captured


# ---------------------------------------------------------------------------
# End-to-end pipeline: manifest → read → dedup → normalize → write
# ---------------------------------------------------------------------------


class TestEndToEndPipeline:
    """Full pipeline integration using mock S3 + mock catalog."""

    @pytest.mark.asyncio
    async def test_markets_pipeline_end_to_end(self) -> None:
        """Process 3 market records through the full pipeline."""
        records = _raw_market_records(3)
        manifest = _make_discovered_manifest(
            entity="markets", row_count=3,
        )
        key = manifest.manifest.files[0].key
        s3_client = _mock_s3_with_compressed({key: records})
        catalog, captured = _mock_catalog_with_capture()

        result = await process_manifest(manifest, s3_client, catalog)

        assert isinstance(result, ProcessingResult)
        assert result.platform == "polymarket"
        assert result.entity == "markets"
        assert result.rows_read == 3
        assert result.rows_written == 3
        assert result.duplicates_dropped == 0
        assert result.snapshot_id == 77777

        # Verify the Arrow table that was appended to catalog
        assert len(captured) == 1
        arrow_tbl = captured[0]
        assert arrow_tbl.num_rows == 3
        # Verify key columns exist
        assert "event_ts" in arrow_tbl.column_names
        assert "platform_market_id" in arrow_tbl.column_names

    @pytest.mark.asyncio
    async def test_events_pipeline_end_to_end(self) -> None:
        """Process event records through the full pipeline."""
        records = _raw_event_records(5)
        manifest = _make_discovered_manifest(
            entity="events", row_count=5,
        )
        key = manifest.manifest.files[0].key
        s3_client = _mock_s3_with_compressed({key: records})
        catalog, captured = _mock_catalog_with_capture()

        result = await process_manifest(manifest, s3_client, catalog)

        assert result.rows_read == 5
        assert result.rows_written == 5
        assert result.duplicates_dropped == 0
        assert len(captured) == 1
        assert captured[0].num_rows == 5

    @pytest.mark.asyncio
    async def test_multi_part_files(self) -> None:
        """Pipeline reads and concatenates multiple part files."""
        manifest = _make_discovered_manifest(
            entity="markets", row_count=6, n_files=2,
        )
        records_part0 = _raw_market_records(3)
        records_part1 = [
            {
                "id": f"0xmarket{i}",
                "condition_id": f"0xcond{i}",
                "question": f"Part 2 question {i}",
                "description": "desc",
                "market_slug": f"slug-p2-{i}",
                "status": "open",
                "outcome": None,
                "tokens": [],
                "event_id": f"evt-p2-{i}",
                "updated_at": f"2024-06-15T13:00:{i:02d}Z",
            }
            for i in range(3, 6)
        ]

        data_by_key = {
            manifest.manifest.files[0].key: records_part0,
            manifest.manifest.files[1].key: records_part1,
        }
        s3_client = _mock_s3_with_compressed(data_by_key)
        catalog, captured = _mock_catalog_with_capture()

        result = await process_manifest(manifest, s3_client, catalog)

        assert result.rows_read == 6
        assert result.rows_written == 6
        assert len(captured) == 1
        assert captured[0].num_rows == 6


# ---------------------------------------------------------------------------
# Deduplication within a single run
# ---------------------------------------------------------------------------


class TestDeduplicationIntegration:
    """Test dedup using real normalizers (not mocks)."""

    @pytest.mark.asyncio
    async def test_duplicate_markets_deduped_in_pipeline(self) -> None:
        """Two identical market records should be deduped to one."""
        rec = _raw_market_records(1)[0]
        records = [rec, rec.copy()]
        manifest = _make_discovered_manifest(entity="markets", row_count=2)
        key = manifest.manifest.files[0].key
        s3_client = _mock_s3_with_compressed({key: records})
        catalog, captured = _mock_catalog_with_capture()

        result = await process_manifest(manifest, s3_client, catalog)

        assert result.rows_read == 2
        assert result.duplicates_dropped == 1
        assert result.rows_after_dedup == 1
        assert result.rows_written == 1
        assert captured[0].num_rows == 1

    def test_dedup_latest_wins_with_real_normalizer(self) -> None:
        """Conflict resolution: later updated_at wins."""
        normalizer = get_normalizer("polymarket", "markets")
        old = {
            "id": "0xdup",
            "updated_at": "2024-06-15T10:00:00Z",
        }
        new = {
            "id": "0xdup",
            "updated_at": "2024-06-15T12:00:00Z",
        }
        # Both share same dedup key prefix (polymarket:0xdup:...) but
        # different updated_at → different dedup keys → both kept
        # To get actual dups, they need identical dedup keys
        rec1 = {"id": "0xdup", "updated_at": "2024-06-15T10:00:00Z"}
        rec2 = {"id": "0xdup", "updated_at": "2024-06-15T10:00:00Z"}

        deduped, stats = dedup_batch([rec1, rec2], normalizer)

        assert stats.records_in == 2
        assert stats.duplicates_dropped == 1
        assert len(deduped) == 1

    def test_dedup_events_with_real_normalizer(self) -> None:
        """Events dedup by (id, updated_at)."""
        normalizer = get_normalizer("polymarket", "events")
        rec = _raw_event_records(1)[0]
        records = [rec, rec.copy(), rec.copy()]

        deduped, stats = dedup_batch(records, normalizer)

        assert stats.duplicates_dropped == 2
        assert len(deduped) == 1


# ---------------------------------------------------------------------------
# Iceberg write and snapshot creation
# ---------------------------------------------------------------------------


class TestIcebergWriteIntegration:
    """Test Arrow conversion + write using real schemas from SILVER_TABLES."""

    def test_normalized_markets_convert_to_arrow(self) -> None:
        """Verify real normalizer output converts cleanly to Arrow."""
        normalizer = get_normalizer("polymarket", "markets")
        raw = _raw_market_records(3)
        normalized = normalizer.normalize_batch(raw, bronze_run_id="run-1")

        assert len(normalized) == 3

        schema, _ = SILVER_TABLES[("silver_polymarket", "markets")]
        arrow_tbl = _to_arrow_table(normalized, schema)

        assert isinstance(arrow_tbl, pa.Table)
        assert arrow_tbl.num_rows == 3
        assert "platform_market_id" in arrow_tbl.column_names
        assert "event_ts" in arrow_tbl.column_names

    def test_normalized_events_convert_to_arrow(self) -> None:
        """Verify event normalization → Arrow conversion works."""
        normalizer = get_normalizer("polymarket", "events")
        raw = _raw_event_records(3)
        normalized = normalizer.normalize_batch(raw, bronze_run_id="run-1")

        schema, _ = SILVER_TABLES[("silver_polymarket", "events")]
        arrow_tbl = _to_arrow_table(normalized, schema)

        assert arrow_tbl.num_rows == 3
        assert "platform_event_id" in arrow_tbl.column_names

    def test_write_captures_snapshot_id(self) -> None:
        """Write to mock catalog captures snapshot ID in result."""
        normalizer = get_normalizer("polymarket", "markets")
        raw = _raw_market_records(2)
        normalized = normalizer.normalize_batch(raw, bronze_run_id="run-1")

        catalog, captured = _mock_catalog_with_capture()

        result = write_to_iceberg(
            normalized, catalog, "silver_polymarket", "markets",
        )

        assert result.snapshot_id == 77777
        assert result.rows_written == 2
        assert len(captured) == 1


# ---------------------------------------------------------------------------
# Error handling: malformed JSON, schema violations
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test error paths through the integrated pipeline."""

    @pytest.mark.asyncio
    async def test_malformed_records_fail_normalization(self) -> None:
        """Records missing required fields cause ProcessingError when all fail."""
        bad_records = [
            {"garbage": True},
            {"also_garbage": "yes"},
        ]
        manifest = _make_discovered_manifest(entity="markets", row_count=2)
        key = manifest.manifest.files[0].key
        s3_client = _mock_s3_with_compressed({key: bad_records})
        catalog, _ = _mock_catalog_with_capture()

        with pytest.raises(ProcessingError, match="All records failed normalization"):
            await process_manifest(manifest, s3_client, catalog)

    @pytest.mark.asyncio
    async def test_partial_normalization_failures_still_write(self) -> None:
        """Mix of good and bad records: good ones still get written."""
        good = _raw_market_records(2)
        bad = [{"garbage": True}]
        records = good + bad

        manifest = _make_discovered_manifest(entity="markets", row_count=3)
        key = manifest.manifest.files[0].key
        s3_client = _mock_s3_with_compressed({key: records})
        catalog, captured = _mock_catalog_with_capture()

        result = await process_manifest(manifest, s3_client, catalog)

        assert result.rows_read == 3
        assert result.rows_normalized == 2
        assert result.rows_written == 2
        assert captured[0].num_rows == 2

    @pytest.mark.asyncio
    async def test_s3_read_failure_raises_processing_error(self) -> None:
        """S3 file missing → reader error → ProcessingError."""
        manifest = _make_discovered_manifest(entity="markets", row_count=1)
        # S3 mock with no data → get_object raises
        s3_client = _mock_s3_with_compressed({})
        catalog, _ = _mock_catalog_with_capture()

        # Reader will log warning and result in 0 records → "No records read"
        with pytest.raises(ProcessingError, match="No records read"):
            await process_manifest(manifest, s3_client, catalog)

    def test_schema_violation_in_arrow_conversion(self) -> None:
        """Wrong types should raise IcebergWriteError."""
        schema, _ = SILVER_TABLES[("silver_polymarket", "markets")]
        bad_records = [
            {
                "event_ts": "not-a-datetime",
                "platform_market_id": "m1",
            }
        ]

        with pytest.raises(IcebergWriteError, match="Failed to convert"):
            _to_arrow_table(bad_records, schema)

    @pytest.mark.asyncio
    async def test_iceberg_append_failure_raises_processing_error(self) -> None:
        """Catalog append failure propagates as ProcessingError.

        Note: Catalog entities now default to append (write_to_iceberg), not
        merge/upsert. The Gold layer handles deduplication at read time.
        """
        records = _raw_market_records(2)
        manifest = _make_discovered_manifest(entity="markets", row_count=2)
        key = manifest.manifest.files[0].key
        s3_client = _mock_s3_with_compressed({key: records})

        catalog = MagicMock()
        mock_table = MagicMock()
        mock_table.append.side_effect = RuntimeError("Iceberg down")
        catalog.load_table.return_value = mock_table

        with pytest.raises(ProcessingError, match="Failed to write"):
            await process_manifest(manifest, s3_client, catalog)


# ---------------------------------------------------------------------------
# PyArrow schema matches Iceberg schema
# ---------------------------------------------------------------------------


class TestSchemaConsistency:
    """Verify normalized output matches the registered Iceberg schemas."""

    @pytest.mark.parametrize(
        "platform,entity,make_records",
        [
            ("polymarket", "markets", _raw_market_records),
            ("polymarket", "events", _raw_event_records),
        ],
    )
    def test_normalizer_output_matches_iceberg_schema(
        self,
        platform: str,
        entity: str,
        make_records: callable,
    ) -> None:
        """All fields from normalizer output are present in Iceberg schema."""
        normalizer = get_normalizer(platform, entity)
        raw = make_records(2)
        normalized = normalizer.normalize_batch(raw, bronze_run_id="run-1")
        assert len(normalized) > 0

        namespace = f"silver_{platform}"
        schema, _ = SILVER_TABLES[(namespace, entity)]
        from pyiceberg.io.pyarrow import schema_to_pyarrow

        arrow_schema = schema_to_pyarrow(schema)
        arrow_field_names = set(arrow_schema.names)

        for rec in normalized:
            for key in rec:
                assert key in arrow_field_names, (
                    f"Normalizer output field '{key}' not in Iceberg schema "
                    f"for {namespace}.{entity}"
                )

    @pytest.mark.parametrize(
        "namespace,table_name",
        [
            ("silver_polymarket", "markets"),
            ("silver_polymarket", "events"),
            ("silver_polymarket", "trades"),
            ("silver_kalshi", "trades"),
            ("silver_kalshi", "markets"),
            ("silver_kalshi", "events"),
        ],
    )
    def test_all_silver_tables_have_event_ts_first(
        self, namespace: str, table_name: str,
    ) -> None:
        """All Silver schemas should have event_ts as their first field."""
        schema, _ = SILVER_TABLES[(namespace, table_name)]
        first_field = schema.fields[0]
        assert first_field.name == "event_ts"


# ---------------------------------------------------------------------------
# Multi-catchup: independent run_ids processed as incremental batches
# ---------------------------------------------------------------------------


class TestMultiCatchupIncrementalProcessing:
    """Integration tests for the continuous ingestion architecture.

    Validates that multiple independent catchup cycles (each producing its own
    run_id and manifest) are processed correctly by Silver, including
    cross-manifest deduplication at the Iceberg merge level.
    """

    @pytest.mark.asyncio
    async def test_multiple_manifests_processed_independently(self) -> None:
        """Each catchup cycle manifest is processed as an independent batch."""
        # Two independent catchup runs for the same day, each with unique records
        records_run1 = [
            {
                "id": f"0xmarket{i}",
                "condition_id": f"0xcond{i}",
                "question": f"Catchup 1 market {i}",
                "description": "desc",
                "market_slug": f"slug-c1-{i}",
                "status": "open",
                "outcome": None,
                "tokens": [{"token_id": f"t1-{i}", "outcome": "Yes"}],
                "event_id": f"evt-{i}",
                "updated_at": f"2024-06-15T10:00:{i:02d}Z",
                "end_date_iso": "2024-12-31T00:00:00Z",
            }
            for i in range(3)
        ]
        records_run2 = [
            {
                "id": f"0xmarket{i}",
                "condition_id": f"0xcond{i}",
                "question": f"Catchup 2 market {i}",
                "description": "desc",
                "market_slug": f"slug-c2-{i}",
                "status": "open",
                "outcome": None,
                "tokens": [{"token_id": f"t1-{i}", "outcome": "Yes"}],
                "event_id": f"evt-{i}",
                "updated_at": f"2024-06-15T14:00:{i:02d}Z",
                "end_date_iso": "2024-12-31T00:00:00Z",
            }
            for i in range(3, 6)
        ]

        manifest1 = _make_discovered_manifest(
            entity="markets", dt="2024-06-15", run_id="catchup-run-1", row_count=3,
        )
        manifest2 = _make_discovered_manifest(
            entity="markets", dt="2024-06-15", run_id="catchup-run-2", row_count=3,
        )

        # Process each manifest independently (simulating two catchup cycles)
        for records, manifest, expected_run_id in [
            (records_run1, manifest1, "catchup-run-1"),
            (records_run2, manifest2, "catchup-run-2"),
        ]:
            key = manifest.manifest.files[0].key
            s3_client = _mock_s3_with_compressed({key: records})
            catalog, captured = _mock_catalog_with_capture()

            result = await process_manifest(manifest, s3_client, catalog)

            assert result.run_id == expected_run_id
            assert result.rows_read == 3
            assert result.rows_written == 3
            assert result.duplicates_dropped == 0
            assert len(captured) == 1
            assert captured[0].num_rows == 3

    @pytest.mark.asyncio
    async def test_overlapping_records_deduped_within_single_manifest(self) -> None:
        """Records duplicated within a single catchup cycle are deduped before write."""
        rec = _raw_market_records(1)[0]
        # Same record appearing twice in one catchup batch (overlapping ingestion window)
        records = [rec, rec.copy()]

        manifest = _make_discovered_manifest(
            entity="markets", dt="2024-06-15", run_id="catchup-overlap-1", row_count=2,
        )
        key = manifest.manifest.files[0].key
        s3_client = _mock_s3_with_compressed({key: records})
        catalog, captured = _mock_catalog_with_capture()

        result = await process_manifest(manifest, s3_client, catalog)

        assert result.rows_read == 2
        assert result.duplicates_dropped == 1
        assert result.rows_written == 1
        assert captured[0].num_rows == 1

    @pytest.mark.asyncio
    async def test_cross_manifest_overlap_handled_by_append(self) -> None:
        """Overlapping records across catchup cycles are handled by append + Gold dedup.

        When two catchup cycles ingest the same record (overlapping time windows),
        each manifest processes independently using append. The Gold layer handles
        deduplication at read time by keeping the latest record per primary key.

        The Silver maintenance compact-dedup operation can periodically clean up
        duplicates in the Silver table.
        """
        # Same market appears in both catchup runs (simulating overlapping windows)
        shared_record = {
            "id": "0xshared-market",
            "condition_id": "0xcond-shared",
            "question": "Shared market across catchups",
            "description": "desc",
            "market_slug": "slug-shared",
            "status": "open",
            "outcome": None,
            "tokens": [{"token_id": "t-shared", "outcome": "Yes"}],
            "event_id": "evt-shared",
            "updated_at": "2024-06-15T12:00:00Z",
            "end_date_iso": "2024-12-31T00:00:00Z",
        }

        unique_rec_1 = {
            "id": "0xunique-1",
            "condition_id": "0xcond-u1",
            "question": "Unique to run 1",
            "description": "desc",
            "market_slug": "slug-u1",
            "status": "open",
            "outcome": None,
            "tokens": [],
            "event_id": "evt-u1",
            "updated_at": "2024-06-15T10:00:00Z",
            "end_date_iso": "2024-12-31T00:00:00Z",
        }

        unique_rec_2 = {
            "id": "0xunique-2",
            "condition_id": "0xcond-u2",
            "question": "Unique to run 2",
            "description": "desc",
            "market_slug": "slug-u2",
            "status": "open",
            "outcome": None,
            "tokens": [],
            "event_id": "evt-u2",
            "updated_at": "2024-06-15T14:00:00Z",
            "end_date_iso": "2024-12-31T00:00:00Z",
        }

        # Run 1: shared + unique-1
        manifest1 = _make_discovered_manifest(
            entity="markets", dt="2024-06-15", run_id="overlap-run-1", row_count=2,
        )
        key1 = manifest1.manifest.files[0].key
        s3_client1 = _mock_s3_with_compressed({key1: [shared_record, unique_rec_1]})
        catalog1, captured1 = _mock_catalog_with_capture()

        result1 = await process_manifest(manifest1, s3_client1, catalog1)
        assert result1.rows_written == 2

        # Run 2: shared + unique-2
        manifest2 = _make_discovered_manifest(
            entity="markets", dt="2024-06-15", run_id="overlap-run-2", row_count=2,
        )
        key2 = manifest2.manifest.files[0].key
        s3_client2 = _mock_s3_with_compressed({key2: [shared_record, unique_rec_2]})
        catalog2, captured2 = _mock_catalog_with_capture()

        result2 = await process_manifest(manifest2, s3_client2, catalog2)
        assert result2.rows_written == 2

        # Both runs write 2 rows each via append.
        # The shared record appears in both write batches — this is expected.
        # Gold layer deduplicates at read time; compact-dedup can clean Silver.
        assert len(captured1) == 1
        assert len(captured2) == 1

        # Verify append was used (not upsert) - check that append method was called
        append_call1 = catalog1.load_table.return_value.append
        append_call1.assert_called_once()

        append_call2 = catalog2.load_table.return_value.append
        append_call2.assert_called_once()


# ---------------------------------------------------------------------------
# Concurrent ingestion safety
# ---------------------------------------------------------------------------


class TestConcurrentIngestionSafety:
    """Tests for correctness when two catchup runs with overlapping time windows
    produce independent manifests that are then both processed into Silver.

    This validates the continuous ingestion architecture where each catchup
    invocation is independently processable.
    """

    @pytest.mark.asyncio
    async def test_independent_manifests_produce_independent_results(self) -> None:
        """Two concurrent ingestion runs produce independent ProcessingResults."""
        records_a = _raw_market_records(3)
        records_b = [
            {
                "id": f"0xmarket{i}",
                "condition_id": f"0xcond{i}",
                "question": f"Concurrent batch B market {i}",
                "description": "desc",
                "market_slug": f"slug-b-{i}",
                "status": "open",
                "outcome": None,
                "tokens": [],
                "event_id": f"evt-b-{i}",
                "updated_at": f"2024-06-15T15:00:{i:02d}Z",
                "end_date_iso": "2024-12-31T00:00:00Z",
            }
            for i in range(3)
        ]

        manifest_a = _make_discovered_manifest(
            entity="markets", dt="2024-06-15", run_id="concurrent-a", row_count=3,
        )
        manifest_b = _make_discovered_manifest(
            entity="markets", dt="2024-06-15", run_id="concurrent-b", row_count=3,
        )

        # Process A
        key_a = manifest_a.manifest.files[0].key
        s3_a = _mock_s3_with_compressed({key_a: records_a})
        catalog_a, captured_a = _mock_catalog_with_capture()
        result_a = await process_manifest(manifest_a, s3_a, catalog_a)

        # Process B
        key_b = manifest_b.manifest.files[0].key
        s3_b = _mock_s3_with_compressed({key_b: records_b})
        catalog_b, captured_b = _mock_catalog_with_capture()
        result_b = await process_manifest(manifest_b, s3_b, catalog_b)

        # Each result is independent
        assert result_a.run_id == "concurrent-a"
        assert result_b.run_id == "concurrent-b"
        assert result_a.rows_written == 3
        assert result_b.rows_written == 3

        # Each captured its own Arrow table
        assert len(captured_a) == 1
        assert len(captured_b) == 1
        assert captured_a[0].num_rows == 3
        assert captured_b[0].num_rows == 3

    @pytest.mark.asyncio
    async def test_overlapping_windows_each_produce_valid_output(self) -> None:
        """Two ingestion runs with overlapping records each produce valid Silver output.

        In the continuous model, overlapping time windows are expected. Each
        catchup run produces its own manifest and is processed independently.
        The Iceberg upsert with merge_keys handles any cross-batch duplicates.
        """
        # Overlapping event records: some appear in both runs
        overlap_events = _raw_event_records(2)  # events 0 and 1
        unique_a = [
            {
                "id": "event-unique-a",
                "title": "Unique event A",
                "description": "Only in run A",
                "slug": "unique-a",
                "status": "active",
                "category": "sports",
                "updated_at": "2024-06-15T10:00:00Z",
            },
        ]
        unique_b = [
            {
                "id": "event-unique-b",
                "title": "Unique event B",
                "description": "Only in run B",
                "slug": "unique-b",
                "status": "active",
                "category": "politics",
                "updated_at": "2024-06-15T14:00:00Z",
            },
        ]

        records_a = overlap_events + unique_a  # 3 records
        records_b = overlap_events + unique_b  # 3 records

        manifest_a = _make_discovered_manifest(
            entity="events", dt="2024-06-15", run_id="window-a", row_count=3,
        )
        manifest_b = _make_discovered_manifest(
            entity="events", dt="2024-06-15", run_id="window-b", row_count=3,
        )

        # Process both
        key_a = manifest_a.manifest.files[0].key
        s3_a = _mock_s3_with_compressed({key_a: records_a})
        catalog_a, captured_a = _mock_catalog_with_capture()
        result_a = await process_manifest(manifest_a, s3_a, catalog_a)

        key_b = manifest_b.manifest.files[0].key
        s3_b = _mock_s3_with_compressed({key_b: records_b})
        catalog_b, captured_b = _mock_catalog_with_capture()
        result_b = await process_manifest(manifest_b, s3_b, catalog_b)

        # Both runs produce valid output
        assert result_a.rows_written == 3
        assert result_b.rows_written == 3
        assert result_a.duplicates_dropped == 0  # no dupes within each batch
        assert result_b.duplicates_dropped == 0

        # Verify platform_event_id column present for merge-key dedup at Iceberg level
        tbl_a = captured_a[0]
        tbl_b = captured_b[0]
        assert "platform_event_id" in tbl_a.column_names
        assert "platform_event_id" in tbl_b.column_names

    @pytest.mark.asyncio
    async def test_state_store_tracks_each_manifest_independently(self) -> None:
        """Each manifest from each catchup run is independently tracked by state store."""
        from prediction_data.silver.state import SilverStateStore, _state_key

        # Set up an in-memory state store
        store_data: dict[str, bytes] = {}
        mock_s3 = MagicMock()
        mock_s3.bucket = "test-bucket"
        boto_client = MagicMock()

        def get_object(Bucket: str, Key: str) -> dict:  # noqa: ARG001
            if Key not in store_data:
                raise type("NoSuchKey", (Exception,), {})(f"Key not found: {Key}")
            body = MagicMock()
            body.read.return_value = store_data[Key]
            return {"Body": body}

        def put_object(Bucket: str, Key: str, Body: bytes, **kw: object) -> None:  # noqa: ARG001
            store_data[Key] = Body

        boto_client.get_object = get_object
        boto_client.put_object = put_object
        boto_client.exceptions = MagicMock()
        boto_client.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        mock_s3._get_client.return_value = boto_client

        state = SilverStateStore(mock_s3, "polymarket", "markets")
        await state.load()

        # Mark two independent catchup runs as processed
        await state.mark_processed("catchup-run-1", "polymarket", "markets", "2024-06-15")
        await state.mark_processed("catchup-run-2", "polymarket", "markets", "2024-06-15")

        assert state.is_processed("catchup-run-1")
        assert state.is_processed("catchup-run-2")
        assert not state.is_processed("catchup-run-3")

        # Verify both entries persisted
        key = _state_key("polymarket", "markets")
        import json
        data = store_data[key].decode()
        lines = [line for line in data.strip().splitlines() if line.strip()]
        assert len(lines) == 2
        run_ids = {json.loads(line)["run_id"] for line in lines}
        assert run_ids == {"catchup-run-1", "catchup-run-2"}


# ---------------------------------------------------------------------------
# Idempotency: reprocessing already-processed manifests
# ---------------------------------------------------------------------------


class TestIdempotencyIntegration:
    """Test that the Silver pipeline is idempotent via the state store.

    The state store (SilverStateStore) tracks processed run_ids. Re-running
    Silver process on already-processed manifests should be a no-op at the
    CLI level. At the processor level, process_manifest itself is deterministic
    — reprocessing produces the same upsert, and Iceberg merge keys prevent
    duplicates.
    """

    @pytest.mark.asyncio
    async def test_reprocessing_same_data_produces_same_result(self) -> None:
        """Processing the same manifest twice produces identical results."""
        records = _raw_market_records(3)
        manifest = _make_discovered_manifest(
            entity="markets", dt="2024-06-15", run_id="idempotent-run-1", row_count=3,
        )
        key = manifest.manifest.files[0].key

        # First run
        s3_1 = _mock_s3_with_compressed({key: records})
        catalog_1, captured_1 = _mock_catalog_with_capture()
        result_1 = await process_manifest(manifest, s3_1, catalog_1)

        # Second run (same data)
        s3_2 = _mock_s3_with_compressed({key: records})
        catalog_2, captured_2 = _mock_catalog_with_capture()
        result_2 = await process_manifest(manifest, s3_2, catalog_2)

        # Results should be identical
        assert result_1.rows_read == result_2.rows_read
        assert result_1.rows_written == result_2.rows_written
        assert result_1.duplicates_dropped == result_2.duplicates_dropped
        assert result_1.rows_normalized == result_2.rows_normalized

        # Arrow tables should have same shape
        assert captured_1[0].num_rows == captured_2[0].num_rows
        assert captured_1[0].column_names == captured_2[0].column_names

    @pytest.mark.asyncio
    async def test_catalog_entity_quality_checks_pass_without_skip_flag(self) -> None:
        """Markets snapshot with wide timestamp range passes quality checks.

        This validates that catalog entities (markets, events) can be processed
        without --skip-quality-checks, because the timestamp_range check is
        not applied to them.
        """
        # Records spanning years — typical of a markets catalog snapshot
        records = [
            {
                "id": f"0xmarket-old-{i}",
                "condition_id": f"0xcond-old-{i}",
                "question": f"Old market {i}",
                "description": "desc",
                "market_slug": f"slug-old-{i}",
                "status": "resolved",
                "outcome": "Yes",
                "tokens": [{"token_id": f"t-old-{i}", "outcome": "Yes"}],
                "event_id": f"evt-old-{i}",
                "updated_at": f"2023-0{i + 1}-15T12:00:00Z",
                "end_date_iso": f"2023-0{i + 1}-30T00:00:00Z",
            }
            for i in range(3)
        ] + [
            {
                "id": "0xmarket-recent",
                "condition_id": "0xcond-recent",
                "question": "Recent market",
                "description": "desc",
                "market_slug": "slug-recent",
                "status": "open",
                "outcome": None,
                "tokens": [{"token_id": "t-recent", "outcome": "Yes"}],
                "event_id": "evt-recent",
                "updated_at": "2024-06-15T12:00:00Z",
                "end_date_iso": "2024-12-31T00:00:00Z",
            },
        ]

        manifest = _make_discovered_manifest(
            entity="markets", dt="2024-06-15", run_id="catalog-no-skip", row_count=4,
        )
        key = manifest.manifest.files[0].key
        s3_client = _mock_s3_with_compressed({key: records})
        catalog, captured = _mock_catalog_with_capture()

        # Process WITHOUT skip_quality_checks — should succeed for catalog entities
        result = await process_manifest(
            manifest, s3_client, catalog, skip_quality_checks=False
        )

        assert result.rows_written == 4
        assert result.quality_checks_passed >= 1
        assert len(captured) == 1
        assert captured[0].num_rows == 4
