"""Tests for Gold ops_metadata pipeline run tracking."""

from __future__ import annotations

from datetime import UTC
from unittest.mock import MagicMock

import pytest

from prediction_data.gold.ops_metadata import (
    PIPELINE_RUNS_COLUMNS,
    end_run,
    start_run,
    track_run,
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
