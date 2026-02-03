"""Pipeline run tracking for ops metadata.

Records start/end of each pipeline run in ClickHouse ``pipeline_runs`` table.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from clickhouse_connect.driver.client import Client

logger = structlog.stdlib.get_logger(__name__)

# Default SLA thresholds (seconds) per dataset.
DEFAULT_SLAS: dict[str, int] = {
    "market_mark_daily": 300,
    "wallet_pnl_daily": 600,
    "wallet_mtm_daily": 900,
    "wallet_position_snapshot_daily": 900,
}

DATASET_FRESHNESS_COLUMNS = [
    "dataset",
    "last_success_at",
    "expected_lag_seconds",
    "actual_lag_seconds",
    "state",
    "last_run_id",
]

DATASET_PARTITIONS_COLUMNS = [
    "dataset",
    "partition_day_utc",
    "row_count",
    "max_event_ts",
    "written_at",
    "run_id",
]


PIPELINE_RUNS_COLUMNS = [
    "run_id",
    "stage",
    "started_at",
    "ended_at",
    "status",
    "input_snapshot_id",
    "output_snapshot_id",
    "rows_written",
    "bytes_written",
    "error",
]


def start_run(
    ch: Client,
    stage: str,
    *,
    input_snapshot_id: str | None = None,
) -> str:
    """Insert a ``running`` record and return the run_id."""
    run_id = uuid.uuid4().hex
    now = datetime.now(UTC)
    ch.insert(
        "pipeline_runs",
        data=[
            [
                run_id,
                stage,
                now,
                None,
                "running",
                input_snapshot_id,
                None,
                0,
                0,
                None,
            ]
        ],
        column_names=PIPELINE_RUNS_COLUMNS,
    )
    logger.info("pipeline_run.started", run_id=run_id, stage=stage)
    return run_id


def end_run(
    ch: Client,
    run_id: str,
    stage: str,
    started_at: datetime,
    *,
    status: str = "success",
    output_snapshot_id: str | None = None,
    rows_written: int = 0,
    bytes_written: int = 0,
    error: str | None = None,
) -> None:
    """Insert the completion record for a pipeline run."""
    now = datetime.now(UTC)
    ch.insert(
        "pipeline_runs",
        data=[
            [
                run_id,
                stage,
                started_at,
                now,
                status,
                None,
                output_snapshot_id,
                rows_written,
                bytes_written,
                error,
            ]
        ],
        column_names=PIPELINE_RUNS_COLUMNS,
    )
    logger.info(
        "pipeline_run.ended",
        run_id=run_id,
        stage=stage,
        status=status,
        rows_written=rows_written,
    )


@contextmanager
def track_run(
    ch: Client,
    stage: str,
    *,
    input_snapshot_id: str | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Context manager that tracks a pipeline run.

    Yields a mutable dict where the caller can set ``rows_written``,
    ``bytes_written``, and ``output_snapshot_id``.  On normal exit the
    run is marked *success*; on exception it is marked *failed* with the
    error message captured.

    Usage::

        with track_run(ch, "gold") as ctx:
            # ... do work ...
            ctx["rows_written"] = 42
    """
    run_id = start_run(ch, stage, input_snapshot_id=input_snapshot_id)
    started_at = datetime.now(UTC)
    ctx: dict[str, Any] = {
        "run_id": run_id,
        "rows_written": 0,
        "bytes_written": 0,
        "output_snapshot_id": None,
    }
    try:
        yield ctx
    except Exception as exc:
        end_run(
            ch,
            run_id,
            stage,
            started_at,
            status="failed",
            rows_written=ctx.get("rows_written", 0),
            bytes_written=ctx.get("bytes_written", 0),
            error=str(exc)[:4096],
        )
        raise
    else:
        end_run(
            ch,
            run_id,
            stage,
            started_at,
            status="success",
            output_snapshot_id=ctx.get("output_snapshot_id"),
            rows_written=ctx.get("rows_written", 0),
            bytes_written=ctx.get("bytes_written", 0),
        )


# ---------------------------------------------------------------------------
# Dataset partition tracking
# ---------------------------------------------------------------------------


def record_partition(
    ch: Client,
    dataset: str,
    partition_day_utc: date,
    *,
    row_count: int = 0,
    max_event_ts: datetime | None = None,
    run_id: str | None = None,
) -> None:
    """Record (or update) a partition entry in ``dataset_partitions``.

    Uses ReplacingMergeTree(written_at) so repeated writes for the same
    (dataset, partition_day_utc) naturally keep the latest row after merges.
    """
    now = datetime.now(UTC)
    ch.insert(
        "dataset_partitions",
        data=[
            [
                dataset,
                partition_day_utc,
                row_count,
                max_event_ts,
                now,
                run_id,
            ]
        ],
        column_names=DATASET_PARTITIONS_COLUMNS,
    )
    logger.info(
        "dataset_partition.recorded",
        dataset=dataset,
        partition_day_utc=str(partition_day_utc),
        row_count=row_count,
    )


def get_latest_partition(
    ch: Client,
    dataset: str,
) -> dict[str, Any] | None:
    """Return the most recently written partition for *dataset*, or *None*."""
    result = ch.query(
        "SELECT dataset, partition_day_utc, row_count, max_event_ts, written_at, run_id "
        "FROM dataset_partitions FINAL "
        "WHERE dataset = {ds:String} "
        "ORDER BY partition_day_utc DESC LIMIT 1",
        parameters={"ds": dataset},
    )
    if not result.result_rows:
        return None
    row = result.result_rows[0]
    return dict(zip(DATASET_PARTITIONS_COLUMNS, row, strict=False))


def get_partitions(
    ch: Client,
    dataset: str,
) -> list[dict[str, Any]]:
    """Return all partitions for *dataset*, ordered by day ascending."""
    result = ch.query(
        "SELECT dataset, partition_day_utc, row_count, max_event_ts, written_at, run_id "
        "FROM dataset_partitions FINAL "
        "WHERE dataset = {ds:String} "
        "ORDER BY partition_day_utc ASC",
        parameters={"ds": dataset},
    )
    return [dict(zip(DATASET_PARTITIONS_COLUMNS, row, strict=False)) for row in result.result_rows]


# ---------------------------------------------------------------------------
# Dataset freshness tracking
# ---------------------------------------------------------------------------


def compute_freshness_state(
    actual_lag_seconds: int,
    expected_lag_seconds: int,
    last_run_failed: bool = False,
) -> str:
    """Determine freshness state: ``fresh``, ``stale``, or ``broken``.

    - **fresh**: actual lag <= SLA
    - **stale**: actual lag > SLA and <= 2× SLA
    - **broken**: actual lag > 2× SLA, or last run failed
    """
    if last_run_failed:
        return "broken"
    if actual_lag_seconds <= expected_lag_seconds:
        return "fresh"
    if actual_lag_seconds <= 2 * expected_lag_seconds:
        return "stale"
    return "broken"


def update_freshness(
    ch: Client,
    dataset: str,
    *,
    last_success_at: datetime,
    run_id: str | None = None,
    now: datetime | None = None,
    last_run_failed: bool = False,
) -> dict[str, Any]:
    """Compute and upsert a freshness record for *dataset*.

    Returns the freshness record dict that was written.
    """
    if now is None:
        now = datetime.now(UTC)
    expected = DEFAULT_SLAS.get(dataset, 900)
    actual = max(0, int((now - last_success_at).total_seconds()))
    state = compute_freshness_state(actual, expected, last_run_failed=last_run_failed)

    ch.insert(
        "dataset_freshness",
        data=[
            [
                dataset,
                last_success_at,
                expected,
                actual,
                state,
                run_id,
            ]
        ],
        column_names=DATASET_FRESHNESS_COLUMNS,
    )
    logger.info(
        "dataset_freshness.updated",
        dataset=dataset,
        state=state,
        actual_lag_seconds=actual,
        expected_lag_seconds=expected,
    )
    return {
        "dataset": dataset,
        "last_success_at": last_success_at,
        "expected_lag_seconds": expected,
        "actual_lag_seconds": actual,
        "state": state,
        "last_run_id": run_id,
    }


def get_all_freshness(
    ch: Client,
) -> list[dict[str, Any]]:
    """Return the latest freshness record for every tracked dataset."""
    result = ch.query(
        "SELECT dataset, last_success_at, expected_lag_seconds, "
        "actual_lag_seconds, state, last_run_id "
        "FROM dataset_freshness FINAL "
        "ORDER BY dataset ASC",
    )
    return [dict(zip(DATASET_FRESHNESS_COLUMNS, row, strict=False)) for row in result.result_rows]


def check_freshness(
    ch: Client,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Re-evaluate freshness for all datasets using current time.

    Reads the latest ``dataset_freshness`` rows and recomputes ``actual_lag_seconds``
    and ``state`` based on *now*.  Does **not** write back — this is a read-only check.
    """
    if now is None:
        now = datetime.now(UTC)
    rows = get_all_freshness(ch)
    for row in rows:
        last_success = row["last_success_at"]
        if hasattr(last_success, "tzinfo") and last_success.tzinfo is None:
            last_success = last_success.replace(tzinfo=UTC)
        actual = max(0, int((now - last_success).total_seconds()))
        row["actual_lag_seconds"] = actual
        row["state"] = compute_freshness_state(
            actual, row["expected_lag_seconds"]
        )
    return rows
