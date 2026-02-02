"""Tests for Silver Iceberg table maintenance operations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pyarrow as pa  # type: ignore[import-untyped]
import pytest

from prediction_data.silver.maintenance import (
    SMALL_FILE_THRESHOLD_BYTES,
    CompactionResult,
    MaintenanceError,
    MaintenanceRunResult,
    OrphanCleanupResult,
    SnapshotExpirationResult,
    _needs_compaction,
    _parse_s3_url,
    compact_table,
    expire_snapshots,
    remove_orphans,
    run_all_maintenance,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_data_files_table(
    files: list[tuple[str, int, str]],
) -> pa.Table:
    """Build a PyArrow table mimicking table.inspect.data_files().

    Args:
        files: list of (file_path, file_size_in_bytes, partition_value).
    """
    return pa.table(
        {
            "file_path": [f[0] for f in files],
            "file_size_in_bytes": [f[1] for f in files],
            "partition": [f[2] for f in files],
        }
    )


def _mock_table(
    files: list[tuple[str, int, str]] | None = None,
    location: str = "s3://bucket/warehouse/silver/trades",
    snapshots: list[MagicMock] | None = None,
) -> MagicMock:
    """Create a mock Iceberg Table."""
    table = MagicMock()
    table.location.return_value = location

    if files is not None:
        table.inspect.data_files.return_value = _make_data_files_table(files)
    else:
        table.inspect.data_files.return_value = pa.table(
            {"file_path": [], "file_size_in_bytes": [], "partition": []}
        )

    if snapshots is not None:
        table.metadata.snapshots = snapshots
    else:
        table.metadata.snapshots = []

    # For compaction: scan -> to_arrow
    scan_mock = MagicMock()
    scan_mock.to_arrow.return_value = pa.table({"x": [1, 2, 3]})
    table.scan.return_value = scan_mock

    # For expire_snapshots
    expire_builder = MagicMock()
    expire_builder.older_than.return_value = expire_builder
    expire_builder._snapshot_ids_to_expire = set()
    table.maintenance.expire_snapshots.return_value = expire_builder

    return table


def _mock_catalog(table: MagicMock) -> MagicMock:
    catalog = MagicMock()
    catalog.load_table.return_value = table
    return catalog


# ---------------------------------------------------------------------------
# _needs_compaction
# ---------------------------------------------------------------------------

class TestNeedsCompaction:
    def test_below_file_count_threshold(self) -> None:
        files = [(f"f{i}.parquet", 1000) for i in range(10)]
        assert _needs_compaction(files) is False

    def test_large_files_not_compacted(self) -> None:
        big = SMALL_FILE_THRESHOLD_BYTES + 1
        files = [(f"f{i}.parquet", big) for i in range(60)]
        assert _needs_compaction(files) is False

    def test_many_small_files_triggers_compaction(self) -> None:
        small = SMALL_FILE_THRESHOLD_BYTES - 1
        files = [(f"f{i}.parquet", small) for i in range(60)]
        assert _needs_compaction(files) is True


# ---------------------------------------------------------------------------
# _parse_s3_url
# ---------------------------------------------------------------------------

class TestParseS3Url:
    def test_valid_url(self) -> None:
        bucket, key = _parse_s3_url("s3://my-bucket/some/key/file.parquet")
        assert bucket == "my-bucket"
        assert key == "some/key/file.parquet"

    def test_invalid_url_raises(self) -> None:
        with pytest.raises(MaintenanceError, match="Not an S3 URL"):
            _parse_s3_url("https://example.com/file.parquet")


# ---------------------------------------------------------------------------
# compact_table
# ---------------------------------------------------------------------------

class TestCompactTable:
    def test_unknown_table_raises(self) -> None:
        catalog = MagicMock()
        with pytest.raises(MaintenanceError, match="Unknown table"):
            compact_table(catalog, "bad_ns", "bad_table")

    def test_no_files_returns_skipped(self) -> None:
        table = _mock_table(files=[])
        catalog = _mock_catalog(table)
        results = compact_table(catalog, "silver_polymarket", "trades")
        assert len(results) == 1
        assert results[0].skipped is True
        assert results[0].files_before == 0

    def test_below_threshold_skipped(self) -> None:
        files = [
            (f"s3://b/k/f{i}.parquet", 1000, "2024-06-15")
            for i in range(10)
        ]
        table = _mock_table(files=files)
        catalog = _mock_catalog(table)
        results = compact_table(catalog, "silver_polymarket", "trades")
        assert len(results) == 1
        assert results[0].skipped is True
        assert results[0].files_before == 10

    def test_dry_run_does_not_overwrite(self) -> None:
        small = SMALL_FILE_THRESHOLD_BYTES - 1
        files = [
            (f"s3://b/k/f{i}.parquet", small, "2024-06-15")
            for i in range(60)
        ]
        table = _mock_table(files=files)
        catalog = _mock_catalog(table)
        results = compact_table(
            catalog, "silver_polymarket", "trades", dry_run=True
        )
        assert len(results) == 1
        assert results[0].skipped is False
        assert results[0].files_before == 60
        # dry_run should not call dynamic_partition_overwrite
        table.dynamic_partition_overwrite.assert_not_called()

    def test_compaction_rewrites_files(self) -> None:
        small = SMALL_FILE_THRESHOLD_BYTES - 1
        files = [
            (f"s3://b/k/f{i}.parquet", small, "2024-06-15")
            for i in range(60)
        ]
        table = _mock_table(files=files)
        catalog = _mock_catalog(table)

        # After compaction, simulate fewer files
        compacted_files = _make_data_files_table([
            ("s3://b/k/compacted.parquet", 256 * 1024 * 1024, "2024-06-15"),
        ])

        # First call returns original files, refresh returns compacted
        call_count = 0
        original_table = _make_data_files_table(files)

        def inspect_side_effect() -> pa.Table:
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return original_table
            return compacted_files

        table.inspect.data_files = inspect_side_effect

        results = compact_table(catalog, "silver_polymarket", "trades")
        assert len(results) == 1
        r = results[0]
        assert r.files_before == 60
        assert r.files_after == 1
        assert r.skipped is False
        table.dynamic_partition_overwrite.assert_called_once()

    def test_partition_filter(self) -> None:
        small = SMALL_FILE_THRESHOLD_BYTES - 1
        files = [
            (f"s3://b/k/f{i}.parquet", small, "2024-06-15")
            for i in range(60)
        ] + [
            (f"s3://b/k/g{i}.parquet", small, "2024-06-16")
            for i in range(60)
        ]
        table = _mock_table(files=files)
        catalog = _mock_catalog(table)
        results = compact_table(
            catalog,
            "silver_polymarket",
            "trades",
            partition="2024-06-15",
            dry_run=True,
        )
        # Should only include the filtered partition
        assert len(results) == 1
        assert results[0].partition == "2024-06-15" or results[0].files_before == 60

    def test_nonexistent_partition_returns_skipped(self) -> None:
        files = [
            (f"s3://b/k/f{i}.parquet", 1000, "2024-06-15")
            for i in range(10)
        ]
        table = _mock_table(files=files)
        catalog = _mock_catalog(table)
        results = compact_table(
            catalog,
            "silver_polymarket",
            "trades",
            partition="2099-01-01",
        )
        assert len(results) == 1
        assert results[0].skipped is True


# ---------------------------------------------------------------------------
# expire_snapshots
# ---------------------------------------------------------------------------

class TestExpireSnapshots:
    def test_unknown_table_raises(self) -> None:
        catalog = MagicMock()
        with pytest.raises(MaintenanceError, match="Unknown table"):
            expire_snapshots(catalog, "bad_ns", "bad_table")

    def test_dry_run_counts_without_committing(self) -> None:
        snapshots = [MagicMock() for _ in range(5)]
        table = _mock_table(snapshots=snapshots)

        # Simulate 3 snapshots that would be expired
        expire_builder = table.maintenance.expire_snapshots.return_value
        expire_builder.older_than.return_value = expire_builder
        expire_builder._snapshot_ids_to_expire = {1, 2, 3}

        catalog = _mock_catalog(table)
        result = expire_snapshots(
            catalog, "silver_polymarket", "trades", dry_run=True
        )
        assert result.snapshots_before == 5
        assert result.snapshots_expired == 3
        assert result.snapshots_after == 2
        expire_builder.commit.assert_not_called()

    def test_expire_commits_and_refreshes(self) -> None:
        snapshots_before = [MagicMock() for _ in range(5)]
        table = _mock_table(snapshots=snapshots_before)
        catalog = _mock_catalog(table)

        # After commit + refresh, fewer snapshots
        def refresh_side_effect() -> None:
            table.metadata.snapshots = [MagicMock(), MagicMock()]

        table.refresh.side_effect = refresh_side_effect

        result = expire_snapshots(catalog, "silver_polymarket", "trades")
        assert result.snapshots_before == 5
        assert result.snapshots_after == 2
        assert result.snapshots_expired == 3
        assert result.duration_seconds >= 0

        expire_builder = table.maintenance.expire_snapshots.return_value
        expire_builder.commit.assert_called_once()

    def test_custom_retention_period(self) -> None:
        table = _mock_table(snapshots=[MagicMock()])
        catalog = _mock_catalog(table)

        result = expire_snapshots(
            catalog, "silver_polymarket", "trades", older_than_days=30
        )
        # Verify cutoff is approximately 30 days ago
        expected_cutoff = datetime.now(tz=UTC) - timedelta(days=30)
        delta = abs((result.older_than - expected_cutoff).total_seconds())
        assert delta < 5  # within 5 seconds


# ---------------------------------------------------------------------------
# remove_orphans
# ---------------------------------------------------------------------------

class TestRemoveOrphans:
    def test_unknown_table_raises(self) -> None:
        catalog = MagicMock()
        with pytest.raises(MaintenanceError, match="Unknown table"):
            remove_orphans(catalog, "bad_ns", "bad_table")

    @patch("prediction_data.silver.maintenance._list_s3_data_files")
    def test_no_orphans(self, mock_list: MagicMock) -> None:
        tracked = [("s3://bucket/data/f1.parquet", 1000, "2024-06-15")]
        table = _mock_table(files=tracked)
        catalog = _mock_catalog(table)

        # S3 lists the same files that are tracked
        old_date = datetime.now(tz=UTC) - timedelta(days=30)
        mock_list.return_value = [
            ("s3://bucket/data/f1.parquet", 1000, old_date),
        ]

        result = remove_orphans(catalog, "silver_polymarket", "trades")
        assert result.orphan_files_found == 0
        assert result.orphan_files_deleted == 0

    @patch("boto3.client")
    @patch("prediction_data.silver.maintenance._list_s3_data_files")
    def test_detects_orphan_files(
        self, mock_list: MagicMock, _mock_boto3_client: MagicMock
    ) -> None:
        tracked = [("s3://bucket/warehouse/silver/trades/data/f1.parquet", 1000, "2024-06-15")]
        table = _mock_table(files=tracked)
        catalog = _mock_catalog(table)

        old_date = datetime.now(tz=UTC) - timedelta(days=30)
        mock_list.return_value = [
            ("s3://bucket/warehouse/silver/trades/data/f1.parquet", 1000, old_date),
            ("s3://bucket/warehouse/silver/trades/data/orphan.parquet", 2000, old_date),
        ]

        result = remove_orphans(
            catalog, "silver_polymarket", "trades", dry_run=True
        )
        assert result.orphan_files_found == 1
        assert result.orphan_files_deleted == 0  # dry_run
        assert result.orphan_bytes == 2000

    @patch("boto3.client")
    @patch("prediction_data.silver.maintenance._list_s3_data_files")
    def test_dry_run_does_not_delete(
        self, mock_list: MagicMock, mock_boto3_client: MagicMock
    ) -> None:
        table = _mock_table(files=[])
        catalog = _mock_catalog(table)

        old_date = datetime.now(tz=UTC) - timedelta(days=30)
        mock_list.return_value = [
            ("s3://bucket/warehouse/silver/trades/data/orphan.parquet", 5000, old_date),
        ]

        result = remove_orphans(
            catalog, "silver_polymarket", "trades", dry_run=True
        )
        assert result.orphan_files_found == 1
        assert result.orphan_files_deleted == 0
        mock_boto3_client.return_value.delete_object.assert_not_called()

    @patch("boto3.client")
    @patch("prediction_data.silver.maintenance._list_s3_data_files")
    def test_deletes_orphan_files(
        self, mock_list: MagicMock, _mock_boto3_client: MagicMock
    ) -> None:
        table = _mock_table(files=[])
        catalog = _mock_catalog(table)

        old_date = datetime.now(tz=UTC) - timedelta(days=30)
        mock_list.return_value = [
            ("s3://bucket/warehouse/silver/trades/data/orphan.parquet", 5000, old_date),
        ]

        result = remove_orphans(catalog, "silver_polymarket", "trades")
        assert result.orphan_files_found == 1
        assert result.orphan_files_deleted == 1
        assert result.orphan_bytes == 5000

    @patch("prediction_data.silver.maintenance._list_s3_data_files")
    def test_recent_orphans_not_deleted(self, mock_list: MagicMock) -> None:
        table = _mock_table(files=[])
        catalog = _mock_catalog(table)

        # File is only 1 day old — below the 7-day safety threshold
        recent_date = datetime.now(tz=UTC) - timedelta(days=1)
        mock_list.return_value = [
            ("s3://bucket/warehouse/silver/trades/data/recent.parquet", 3000, recent_date),
        ]

        result = remove_orphans(catalog, "silver_polymarket", "trades")
        assert result.orphan_files_found == 0  # too recent to be considered


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

class TestResultDataclasses:
    def test_compaction_result_fields(self) -> None:
        r = CompactionResult(
            namespace="silver_polymarket",
            table_name="trades",
            partition="2024-06-15",
            files_before=60,
            files_after=2,
            bytes_before=1000,
            bytes_after=500,
            duration_seconds=1.5,
        )
        assert r.skipped is False

    def test_snapshot_expiration_result_fields(self) -> None:
        now = datetime.now(tz=UTC)
        r = SnapshotExpirationResult(
            namespace="silver_polymarket",
            table_name="trades",
            snapshots_before=10,
            snapshots_after=5,
            snapshots_expired=5,
            older_than=now,
            duration_seconds=0.5,
        )
        assert r.snapshots_expired == 5

    def test_orphan_cleanup_result_fields(self) -> None:
        r = OrphanCleanupResult(
            namespace="silver_polymarket",
            table_name="trades",
            orphan_files_found=3,
            orphan_files_deleted=3,
            orphan_bytes=9000,
            duration_seconds=2.0,
        )
        assert r.orphan_files_found == 3

    def test_maintenance_run_result_fields(self) -> None:
        r = MaintenanceRunResult(
            tables_processed=6,
            compaction_results=[],
            expiration_results=[],
            orphan_results=[],
            errors=[],
            duration_seconds=10.0,
        )
        assert r.tables_processed == 6
        assert r.errors == []


# ---------------------------------------------------------------------------
# run_all_maintenance
# ---------------------------------------------------------------------------

class TestRunAllMaintenance:
    """Tests for the unified maintenance runner."""

    @patch("prediction_data.silver.maintenance.remove_orphans")
    @patch("prediction_data.silver.maintenance.expire_snapshots")
    @patch("prediction_data.silver.maintenance.compact_table")
    def test_runs_all_operations_on_all_tables(
        self,
        mock_compact: MagicMock,
        mock_expire: MagicMock,
        mock_orphans: MagicMock,
    ) -> None:
        mock_compact.return_value = []
        mock_expire.return_value = SnapshotExpirationResult(
            namespace="ns", table_name="t",
            snapshots_before=5, snapshots_after=5, snapshots_expired=0,
            older_than=datetime.now(tz=UTC), duration_seconds=0.0,
        )
        mock_orphans.return_value = OrphanCleanupResult(
            namespace="ns", table_name="t",
            orphan_files_found=0, orphan_files_deleted=0,
            orphan_bytes=0, duration_seconds=0.0,
        )

        catalog = MagicMock()
        result = run_all_maintenance(catalog, dry_run=True)

        # 6 tables in SILVER_TABLES
        assert result.tables_processed == 6
        assert mock_compact.call_count == 6
        assert mock_expire.call_count == 6
        assert mock_orphans.call_count == 6
        assert result.errors == []

    @patch("prediction_data.silver.maintenance.compact_table")
    def test_single_operation(self, mock_compact: MagicMock) -> None:
        mock_compact.return_value = []

        catalog = MagicMock()
        result = run_all_maintenance(
            catalog, operations=frozenset({"compact"}), dry_run=True,
        )

        assert result.tables_processed == 6
        assert mock_compact.call_count == 6
        assert result.expiration_results == []
        assert result.orphan_results == []

    @patch("prediction_data.silver.maintenance.compact_table")
    def test_error_captured_and_continues(self, mock_compact: MagicMock) -> None:
        call_count = 0

        def side_effect(*_args: object, **_kwargs: object) -> list[CompactionResult]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise MaintenanceError("test error")
            return []

        mock_compact.side_effect = side_effect

        catalog = MagicMock()
        result = run_all_maintenance(
            catalog, operations=frozenset({"compact"}), dry_run=True,
        )

        assert result.tables_processed == 6
        assert len(result.errors) == 1
        assert "test error" in result.errors[0][1]
