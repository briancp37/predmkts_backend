"""Tests for Gold ops_metadata: pipeline runs, dataset partitions, and freshness."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest

from prediction_data.gold.ops_metadata import (
    DATASET_PARTITIONS_COLUMNS,
    PIPELINE_RUNS_COLUMNS,
    check_freshness,
    compute_freshness_state,
    end_run,
    get_all_freshness,
    get_latest_partition,
    get_partitions,
    record_partition,
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
