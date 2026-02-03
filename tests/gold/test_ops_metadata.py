"""Tests for Gold ops_metadata: pipeline runs, dataset partitions, and freshness."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest

from prediction_data.gold.ops_metadata import (
    DATA_QUALITY_COLUMNS,
    DATASET_PARTITIONS_COLUMNS,
    PIPELINE_RUNS_COLUMNS,
    check_freshness,
    compute_freshness_state,
    end_run,
    get_all_freshness,
    get_failed_checks,
    get_latest_partition,
    get_partitions,
    get_quality_metrics,
    record_partition,
    record_quality_check,
    run_quality_checks,
    start_run,
    track_run,
    update_freshness,
)


@pytest.fixture()
def mock_ch() -> MagicMock:
    client = MagicMock()
    return client


class TestStartRun:
    def test_inserts_running_record(self, mock_ch: MagicMock) -> None:
        run_id = start_run(mock_ch, "gold")
        assert len(run_id) == 32  # hex uuid
        mock_ch.insert.assert_called_once()
        args, kwargs = mock_ch.insert.call_args
        assert args[0] == "pipeline_runs"
        row = kwargs["data"][0]
        assert row[0] == run_id
        assert row[1] == "gold"
        assert row[4] == "running"
        assert kwargs["column_names"] == PIPELINE_RUNS_COLUMNS

    def test_passes_input_snapshot_id(self, mock_ch: MagicMock) -> None:
        start_run(mock_ch, "silver", input_snapshot_id="snap-123")
        row = mock_ch.insert.call_args[1]["data"][0]
        assert row[5] == "snap-123"


class TestEndRun:
    def test_inserts_completion_record(self, mock_ch: MagicMock) -> None:
        from datetime import datetime

        started = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        end_run(
            mock_ch,
            "run-abc",
            "gold",
            started,
            status="success",
            rows_written=100,
            bytes_written=2048,
        )
        mock_ch.insert.assert_called_once()
        row = mock_ch.insert.call_args[1]["data"][0]
        assert row[0] == "run-abc"
        assert row[4] == "success"
        assert row[7] == 100
        assert row[8] == 2048


class TestTrackRun:
    def test_success_path(self, mock_ch: MagicMock) -> None:
        with track_run(mock_ch, "gold") as ctx:
            ctx["rows_written"] = 42
        # Two inserts: start + end
        assert mock_ch.insert.call_count == 2
        end_row = mock_ch.insert.call_args_list[1][1]["data"][0]
        assert end_row[4] == "success"
        assert end_row[7] == 42

    def test_failure_path(self, mock_ch: MagicMock) -> None:
        with pytest.raises(ValueError, match="boom"), track_run(mock_ch, "gold") as ctx:
            ctx["rows_written"] = 5
            raise ValueError("boom")
        assert mock_ch.insert.call_count == 2
        end_row = mock_ch.insert.call_args_list[1][1]["data"][0]
        assert end_row[4] == "failed"
        assert end_row[9] == "boom"
        assert end_row[7] == 5

    def test_ctx_contains_run_id(self, mock_ch: MagicMock) -> None:
        with track_run(mock_ch, "gold") as ctx:
            assert "run_id" in ctx
            assert len(ctx["run_id"]) == 32


class TestRecordPartition:
    def test_inserts_partition_record(self, mock_ch: MagicMock) -> None:
        record_partition(
            mock_ch,
            "market_mark_daily",
            date(2024, 6, 15),
            row_count=500,
            run_id="run-xyz",
        )
        mock_ch.insert.assert_called_once()
        args, kwargs = mock_ch.insert.call_args
        assert args[0] == "dataset_partitions"
        row = kwargs["data"][0]
        assert row[0] == "market_mark_daily"
        assert row[1] == date(2024, 6, 15)
        assert row[2] == 500
        assert row[3] is None  # max_event_ts not provided
        assert row[5] == "run-xyz"
        assert kwargs["column_names"] == DATASET_PARTITIONS_COLUMNS

    def test_passes_max_event_ts(self, mock_ch: MagicMock) -> None:
        ts = datetime(2024, 6, 15, 23, 59, 0, tzinfo=UTC)
        record_partition(
            mock_ch,
            "wallet_pnl_daily",
            date(2024, 6, 15),
            row_count=10,
            max_event_ts=ts,
        )
        row = mock_ch.insert.call_args[1]["data"][0]
        assert row[3] == ts

    def test_defaults(self, mock_ch: MagicMock) -> None:
        record_partition(mock_ch, "market_mark_daily", date(2024, 1, 1))
        row = mock_ch.insert.call_args[1]["data"][0]
        assert row[2] == 0  # row_count default
        assert row[3] is None  # max_event_ts default
        assert row[5] is None  # run_id default


class TestGetLatestPartition:
    def test_returns_dict_when_found(self, mock_ch: MagicMock) -> None:
        mock_ch.query.return_value.result_rows = [
            ("market_mark_daily", date(2024, 6, 15), 500, None, datetime(2024, 6, 15, 12, tzinfo=UTC), "run-1"),
        ]
        result = get_latest_partition(mock_ch, "market_mark_daily")
        assert result is not None
        assert result["dataset"] == "market_mark_daily"
        assert result["partition_day_utc"] == date(2024, 6, 15)
        assert result["row_count"] == 500

    def test_returns_none_when_empty(self, mock_ch: MagicMock) -> None:
        mock_ch.query.return_value.result_rows = []
        assert get_latest_partition(mock_ch, "nonexistent") is None


class TestGetPartitions:
    def test_returns_list_of_dicts(self, mock_ch: MagicMock) -> None:
        mock_ch.query.return_value.result_rows = [
            ("ds", date(2024, 6, 14), 100, None, datetime(2024, 6, 14, 12, tzinfo=UTC), "r1"),
            ("ds", date(2024, 6, 15), 200, None, datetime(2024, 6, 15, 12, tzinfo=UTC), "r2"),
        ]
        results = get_partitions(mock_ch, "ds")
        assert len(results) == 2
        assert results[0]["partition_day_utc"] == date(2024, 6, 14)
        assert results[1]["row_count"] == 200

    def test_returns_empty_list(self, mock_ch: MagicMock) -> None:
        mock_ch.query.return_value.result_rows = []
        assert get_partitions(mock_ch, "ds") == []


class TestComputeFreshnessState:
    def test_fresh_within_sla(self) -> None:
        assert compute_freshness_state(100, 300) == "fresh"

    def test_fresh_exactly_at_sla(self) -> None:
        assert compute_freshness_state(300, 300) == "fresh"

    def test_stale_above_sla(self) -> None:
        assert compute_freshness_state(400, 300) == "stale"

    def test_stale_at_double_sla(self) -> None:
        assert compute_freshness_state(600, 300) == "stale"

    def test_broken_above_double_sla(self) -> None:
        assert compute_freshness_state(601, 300) == "broken"

    def test_broken_on_last_run_failed(self) -> None:
        assert compute_freshness_state(0, 300, last_run_failed=True) == "broken"


class TestUpdateFreshness:
    def test_inserts_freshness_record(self, mock_ch: MagicMock) -> None:
        now = datetime(2024, 6, 15, 12, 5, 0, tzinfo=UTC)
        last = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        result = update_freshness(
            mock_ch,
            "market_mark_daily",
            last_success_at=last,
            run_id="run-1",
            now=now,
        )
        mock_ch.insert.assert_called_once()
        assert result["state"] == "fresh"
        assert result["actual_lag_seconds"] == 300
        assert result["expected_lag_seconds"] == 300
        assert result["dataset"] == "market_mark_daily"

    def test_stale_state(self, mock_ch: MagicMock) -> None:
        now = datetime(2024, 6, 15, 12, 8, 0, tzinfo=UTC)
        last = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        result = update_freshness(
            mock_ch, "market_mark_daily", last_success_at=last, now=now,
        )
        assert result["state"] == "stale"
        assert result["actual_lag_seconds"] == 480

    def test_broken_on_failure(self, mock_ch: MagicMock) -> None:
        now = datetime(2024, 6, 15, 12, 0, 10, tzinfo=UTC)
        last = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        result = update_freshness(
            mock_ch, "market_mark_daily", last_success_at=last, now=now,
            last_run_failed=True,
        )
        assert result["state"] == "broken"


class TestGetAllFreshness:
    def test_returns_list(self, mock_ch: MagicMock) -> None:
        mock_ch.query.return_value.result_rows = [
            ("market_mark_daily", datetime(2024, 6, 15, 12, tzinfo=UTC), 300, 100, "fresh", "r1"),
        ]
        results = get_all_freshness(mock_ch)
        assert len(results) == 1
        assert results[0]["dataset"] == "market_mark_daily"
        assert results[0]["state"] == "fresh"


class TestCheckFreshness:
    def test_recomputes_state(self, mock_ch: MagicMock) -> None:
        mock_ch.query.return_value.result_rows = [
            ("market_mark_daily", datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC), 300, 100, "fresh", "r1"),
        ]
        now = datetime(2024, 6, 15, 12, 10, 0, tzinfo=UTC)
        results = check_freshness(mock_ch, now=now)
        assert results[0]["actual_lag_seconds"] == 600
        assert results[0]["state"] == "stale"

    def test_empty(self, mock_ch: MagicMock) -> None:
        mock_ch.query.return_value.result_rows = []
        assert check_freshness(mock_ch) == []


# ---------------------------------------------------------------------------
# Integration tests: simulate Gold processing with ops metadata
# ---------------------------------------------------------------------------


class TestOpsMetadataIntegration:
    """Integration test: simulates a Gold processing job and verifies ops records.

    This test uses a mock ClickHouse client to capture the records that would
    be written to pipeline_runs, dataset_partitions, and dataset_freshness tables.
    """

    def test_gold_processing_emits_all_ops_records(self, mock_ch: MagicMock) -> None:
        """Simulate a Gold compute job that writes to all three ops tables.

        Verifies that:
        1. pipeline_runs receives start (running) + end (success) records
        2. dataset_partitions receives a partition record
        3. dataset_freshness receives an update
        """
        # Simulate a Gold compute-marks style job
        dt = date(2024, 6, 15)
        dataset = "market_mark_daily"

        # --- Step 1: Run the pipeline with tracking ---
        with track_run(mock_ch, "gold") as ctx:
            # Simulate work
            rows_computed = 500
            ctx["rows_written"] = rows_computed

            # After processing, record the partition
            record_partition(
                mock_ch,
                dataset,
                dt,
                row_count=rows_computed,
                run_id=ctx["run_id"],
            )

            # Update freshness
            now = datetime(2024, 6, 15, 12, 5, 0, tzinfo=UTC)
            update_freshness(
                mock_ch,
                dataset,
                last_success_at=now,
                run_id=ctx["run_id"],
                now=now,
            )

        # --- Step 2: Verify records were inserted ---
        # Should have 4 inserts total: start_run, record_partition, update_freshness, end_run
        assert mock_ch.insert.call_count == 4

        # Collect all inserts by table
        inserts_by_table: dict[str, list[list[object]]] = {}
        for call in mock_ch.insert.call_args_list:
            table = call[0][0]
            row = call[1]["data"][0]
            inserts_by_table.setdefault(table, []).append(row)

        # Verify pipeline_runs: 2 records (running + success)
        assert len(inserts_by_table["pipeline_runs"]) == 2
        start_row = inserts_by_table["pipeline_runs"][0]
        end_row = inserts_by_table["pipeline_runs"][1]
        assert start_row[4] == "running"
        assert end_row[4] == "success"
        assert end_row[7] == 500  # rows_written

        # Verify dataset_partitions: 1 record
        assert len(inserts_by_table["dataset_partitions"]) == 1
        part_row = inserts_by_table["dataset_partitions"][0]
        assert part_row[0] == "market_mark_daily"
        assert part_row[1] == date(2024, 6, 15)
        assert part_row[2] == 500

        # Verify dataset_freshness: 1 record
        assert len(inserts_by_table["dataset_freshness"]) == 1
        fresh_row = inserts_by_table["dataset_freshness"][0]
        assert fresh_row[0] == "market_mark_daily"
        assert fresh_row[4] == "fresh"  # state

    def test_failed_pipeline_records_error(self, mock_ch: MagicMock) -> None:
        """Verify that a failed pipeline run captures the error message."""
        with pytest.raises(RuntimeError, match="Silver table missing"), track_run(mock_ch, "gold") as ctx:
            ctx["rows_written"] = 10
            raise RuntimeError("Silver table missing")

        # Should have 2 inserts: start + failed end
        assert mock_ch.insert.call_count == 2
        end_row = mock_ch.insert.call_args_list[1][1]["data"][0]
        assert end_row[4] == "failed"
        assert "Silver table missing" in end_row[9]  # error column

    def test_run_id_links_across_tables(self, mock_ch: MagicMock) -> None:
        """Verify run_id consistency across pipeline_runs, partitions, and freshness."""
        captured_run_id: str | None = None

        with track_run(mock_ch, "gold") as ctx:
            captured_run_id = ctx["run_id"]
            record_partition(
                mock_ch,
                "wallet_pnl_daily",
                date(2024, 6, 15),
                row_count=100,
                run_id=captured_run_id,
            )
            update_freshness(
                mock_ch,
                "wallet_pnl_daily",
                last_success_at=datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
                run_id=captured_run_id,
            )

        assert captured_run_id is not None

        # Verify run_id appears in all records
        for call in mock_ch.insert.call_args_list:
            table = call[0][0]
            row = call[1]["data"][0]
            if table == "pipeline_runs":
                assert row[0] == captured_run_id  # run_id is first column
            elif table == "dataset_partitions":
                assert row[5] == captured_run_id  # run_id is last column
            elif table == "dataset_freshness":
                assert row[5] == captured_run_id  # last_run_id is last column


# ---------------------------------------------------------------------------
# Data quality metrics tests
# ---------------------------------------------------------------------------


class TestRecordQualityCheck:
    def test_inserts_quality_record(self, mock_ch: MagicMock) -> None:
        result = record_quality_check(
            mock_ch,
            "market_mark_daily",
            date(2024, 6, 15),
            "non_null_market_id",
            "pass",
            observed_value=0.0,
            expected="0 null values",
            run_id="run-123",
        )
        mock_ch.insert.assert_called_once()
        args, kwargs = mock_ch.insert.call_args
        assert args[0] == "data_quality_metrics"
        row = kwargs["data"][0]
        assert row[0] == "market_mark_daily"
        assert row[1] == date(2024, 6, 15)
        assert row[2] == "non_null_market_id"
        assert row[3] == "pass"
        assert row[4] == 0.0
        assert row[5] == "0 null values"
        assert row[6] == "run-123"
        assert kwargs["column_names"] == DATA_QUALITY_COLUMNS
        assert result["status"] == "pass"
        assert result["check_name"] == "non_null_market_id"

    def test_defaults(self, mock_ch: MagicMock) -> None:
        record_quality_check(
            mock_ch,
            "wallet_pnl_daily",
            date(2024, 6, 15),
            "pnl_sanity",
            "warn",
        )
        row = mock_ch.insert.call_args[1]["data"][0]
        assert row[4] is None  # observed_value default
        assert row[5] is None  # expected default
        assert row[6] is None  # run_id default


class TestGetQualityMetrics:
    def test_returns_list_for_dataset(self, mock_ch: MagicMock) -> None:
        mock_ch.query.return_value.result_rows = [
            ("market_mark_daily", date(2024, 6, 15), "non_null_market_id", "pass", 0.0, "0 null values", "r1", datetime(2024, 6, 15, 12, tzinfo=UTC)),
        ]
        results = get_quality_metrics(mock_ch, "market_mark_daily")
        assert len(results) == 1
        assert results[0]["dataset"] == "market_mark_daily"
        assert results[0]["status"] == "pass"

    def test_filters_by_partition(self, mock_ch: MagicMock) -> None:
        mock_ch.query.return_value.result_rows = []
        get_quality_metrics(mock_ch, "market_mark_daily", partition=date(2024, 6, 15))
        query = mock_ch.query.call_args[0][0]
        assert "partition = {part:Date}" in query
        assert mock_ch.query.call_args[1]["parameters"]["part"] == date(2024, 6, 15)

    def test_filters_by_run_id(self, mock_ch: MagicMock) -> None:
        mock_ch.query.return_value.result_rows = []
        get_quality_metrics(mock_ch, "market_mark_daily", run_id="run-xyz")
        query = mock_ch.query.call_args[0][0]
        assert "run_id = {rid:String}" in query
        assert mock_ch.query.call_args[1]["parameters"]["rid"] == "run-xyz"


class TestGetFailedChecks:
    def test_returns_failed_checks(self, mock_ch: MagicMock) -> None:
        mock_ch.query.return_value.result_rows = [
            ("market_mark_daily", date(2024, 6, 15), "non_null_market_id", "fail", 5.0, "0 null values", "r1", datetime(2024, 6, 15, 12, tzinfo=UTC)),
        ]
        results = get_failed_checks(mock_ch)
        assert len(results) == 1
        assert results[0]["status"] == "fail"

    def test_filters_by_dataset(self, mock_ch: MagicMock) -> None:
        mock_ch.query.return_value.result_rows = []
        get_failed_checks(mock_ch, dataset="wallet_pnl_daily")
        query = mock_ch.query.call_args[0][0]
        assert "dataset = {ds:String}" in query


class TestRunQualityChecksMarketMarks:
    def test_all_pass_for_valid_data(self, mock_ch: MagicMock) -> None:
        data = [
            {"market_id": "m1", "outcome_id": "o1", "mark_price": 0.5, "volume_usd_24h": 1000.0},
            {"market_id": "m2", "outcome_id": "o2", "mark_price": 0.75, "volume_usd_24h": 500.0},
        ]
        results = run_quality_checks(mock_ch, "market_mark_daily", date(2024, 6, 15), data, run_id="run-1")
        # Should have 4 checks: non_null_market_id, non_null_outcome_id, mark_price_range, non_negative_volume
        assert len(results) == 4
        assert all(r["status"] == "pass" for r in results)

    def test_fails_on_null_market_id(self, mock_ch: MagicMock) -> None:
        data = [
            {"market_id": None, "outcome_id": "o1", "mark_price": 0.5, "volume_usd_24h": 100.0},
            {"market_id": "m2", "outcome_id": "o2", "mark_price": 0.6, "volume_usd_24h": 200.0},
        ]
        results = run_quality_checks(mock_ch, "market_mark_daily", date(2024, 6, 15), data)
        market_id_check = next(r for r in results if r["check_name"] == "non_null_market_id")
        assert market_id_check["status"] == "fail"
        assert market_id_check["observed_value"] == 1.0

    def test_warns_on_invalid_price_range(self, mock_ch: MagicMock) -> None:
        data = [
            {"market_id": "m1", "outcome_id": "o1", "mark_price": 1.5, "volume_usd_24h": 100.0},  # > 1
        ]
        results = run_quality_checks(mock_ch, "market_mark_daily", date(2024, 6, 15), data)
        price_check = next(r for r in results if r["check_name"] == "mark_price_range")
        assert price_check["status"] == "warn"


class TestRunQualityChecksWalletPnl:
    def test_all_pass_for_valid_data(self, mock_ch: MagicMock) -> None:
        data = [
            {"wallet": "0x123", "realized_pnl_usd": 100.0, "volume_usd": 1000.0, "wins": 5, "losses": 3, "trades_count": 10},
        ]
        results = run_quality_checks(mock_ch, "wallet_pnl_daily", date(2024, 6, 15), data)
        # Should have 4 checks
        assert len(results) == 4
        assert all(r["status"] == "pass" for r in results)

    def test_fails_on_null_wallet(self, mock_ch: MagicMock) -> None:
        data = [
            {"wallet": None, "realized_pnl_usd": 100.0, "volume_usd": 1000.0, "wins": 1, "losses": 0, "trades_count": 1},
        ]
        results = run_quality_checks(mock_ch, "wallet_pnl_daily", date(2024, 6, 15), data)
        wallet_check = next(r for r in results if r["check_name"] == "non_null_wallet")
        assert wallet_check["status"] == "fail"

    def test_warns_on_extreme_pnl(self, mock_ch: MagicMock) -> None:
        data = [
            {"wallet": "0x123", "realized_pnl_usd": 2_000_000.0, "volume_usd": 1000.0, "wins": 1, "losses": 0, "trades_count": 1},
        ]
        results = run_quality_checks(mock_ch, "wallet_pnl_daily", date(2024, 6, 15), data)
        pnl_check = next(r for r in results if r["check_name"] == "pnl_sanity")
        assert pnl_check["status"] == "warn"

    def test_fails_on_win_loss_inconsistency(self, mock_ch: MagicMock) -> None:
        data = [
            {"wallet": "0x123", "realized_pnl_usd": 100.0, "volume_usd": 1000.0, "wins": 10, "losses": 10, "trades_count": 5},
        ]
        results = run_quality_checks(mock_ch, "wallet_pnl_daily", date(2024, 6, 15), data)
        consistency_check = next(r for r in results if r["check_name"] == "win_loss_consistency")
        assert consistency_check["status"] == "fail"


class TestRunQualityChecksWalletMtm:
    def test_all_pass_for_valid_data(self, mock_ch: MagicMock) -> None:
        data = [
            {"wallet": "0x123", "mtm_usd": 5000.0},
        ]
        results = run_quality_checks(mock_ch, "wallet_mtm_daily", date(2024, 6, 15), data)
        assert len(results) == 2
        assert all(r["status"] == "pass" for r in results)

    def test_warns_on_extreme_mtm(self, mock_ch: MagicMock) -> None:
        data = [
            {"wallet": "0x123", "mtm_usd": 50_000_000.0},
        ]
        results = run_quality_checks(mock_ch, "wallet_mtm_daily", date(2024, 6, 15), data)
        mtm_check = next(r for r in results if r["check_name"] == "mtm_sanity")
        assert mtm_check["status"] == "warn"


class TestRunQualityChecksWalletPositions:
    def test_all_pass_for_valid_data(self, mock_ch: MagicMock) -> None:
        data = [
            {"wallet": "0x123", "market_id": "m1", "outcome_id": "o1", "position": 100.0},
        ]
        results = run_quality_checks(mock_ch, "wallet_position_snapshot_daily", date(2024, 6, 15), data)
        assert len(results) == 4
        assert all(r["status"] == "pass" for r in results)

    def test_fails_on_null_keys(self, mock_ch: MagicMock) -> None:
        data = [
            {"wallet": "0x123", "market_id": None, "outcome_id": "o1", "position": 100.0},
        ]
        results = run_quality_checks(mock_ch, "wallet_position_snapshot_daily", date(2024, 6, 15), data)
        market_id_check = next(r for r in results if r["check_name"] == "non_null_market_id")
        assert market_id_check["status"] == "fail"

    def test_warns_on_extreme_positions(self, mock_ch: MagicMock) -> None:
        data = [
            {"wallet": "0x123", "market_id": "m1", "outcome_id": "o1", "position": 5_000_000.0},
        ]
        results = run_quality_checks(mock_ch, "wallet_position_snapshot_daily", date(2024, 6, 15), data)
        position_check = next(r for r in results if r["check_name"] == "position_sanity")
        assert position_check["status"] == "warn"
