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


# ---------------------------------------------------------------------------
# Data quality metrics tracking
# ---------------------------------------------------------------------------


DATA_QUALITY_COLUMNS = [
    "dataset",
    "partition",
    "check_name",
    "status",
    "observed_value",
    "expected",
    "run_id",
    "checked_at",
]


def record_quality_check(
    ch: Client,
    dataset: str,
    partition: date,
    check_name: str,
    status: str,
    *,
    observed_value: float | None = None,
    expected: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Record a data quality check result in ``data_quality_metrics``.

    Args:
        ch: ClickHouse client.
        dataset: Name of the dataset (e.g., ``market_mark_daily``).
        partition: The partition date being checked.
        check_name: Name of the quality check (e.g., ``non_null_market_id``).
        status: Check result: ``pass``, ``fail``, or ``warn``.
        observed_value: The actual value observed (optional).
        expected: Description of expected value/range (optional).
        run_id: Associated pipeline run ID (optional).

    Returns:
        The quality record dict that was written.
    """
    now = datetime.now(UTC)
    ch.insert(
        "data_quality_metrics",
        data=[
            [
                dataset,
                partition,
                check_name,
                status,
                observed_value,
                expected,
                run_id,
                now,
            ]
        ],
        column_names=DATA_QUALITY_COLUMNS,
    )
    logger.info(
        "data_quality.recorded",
        dataset=dataset,
        partition=str(partition),
        check_name=check_name,
        status=status,
    )
    return {
        "dataset": dataset,
        "partition": partition,
        "check_name": check_name,
        "status": status,
        "observed_value": observed_value,
        "expected": expected,
        "run_id": run_id,
        "checked_at": now,
    }


def get_quality_metrics(
    ch: Client,
    dataset: str,
    partition: date | None = None,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Query data quality metrics with optional filtering.

    Args:
        ch: ClickHouse client.
        dataset: Name of the dataset to query.
        partition: Optional partition date filter.
        run_id: Optional run_id filter.

    Returns:
        List of quality metric dicts, ordered by checked_at descending.
    """
    query = (
        "SELECT dataset, partition, check_name, status, "
        "observed_value, expected, run_id, checked_at "
        "FROM data_quality_metrics "
        "WHERE dataset = {ds:String}"
    )
    params: dict[str, Any] = {"ds": dataset}

    if partition is not None:
        query += " AND partition = {part:Date}"
        params["part"] = partition

    if run_id is not None:
        query += " AND run_id = {rid:String}"
        params["rid"] = run_id

    query += " ORDER BY checked_at DESC"

    result = ch.query(query, parameters=params)
    return [dict(zip(DATA_QUALITY_COLUMNS, row, strict=False)) for row in result.result_rows]


def get_failed_checks(
    ch: Client,
    dataset: str | None = None,
    partition: date | None = None,
) -> list[dict[str, Any]]:
    """Query failed quality checks.

    Args:
        ch: ClickHouse client.
        dataset: Optional dataset filter.
        partition: Optional partition date filter.

    Returns:
        List of failed quality metric dicts, ordered by checked_at descending.
    """
    query = (
        "SELECT dataset, partition, check_name, status, "
        "observed_value, expected, run_id, checked_at "
        "FROM data_quality_metrics "
        "WHERE status = 'fail'"
    )
    params: dict[str, Any] = {}

    if dataset is not None:
        query += " AND dataset = {ds:String}"
        params["ds"] = dataset

    if partition is not None:
        query += " AND partition = {part:Date}"
        params["part"] = partition

    query += " ORDER BY checked_at DESC"

    result = ch.query(query, parameters=params)
    return [dict(zip(DATA_QUALITY_COLUMNS, row, strict=False)) for row in result.result_rows]


# ---------------------------------------------------------------------------
# Quality check helpers
# ---------------------------------------------------------------------------


def run_quality_checks(
    ch: Client,
    dataset: str,
    partition: date,
    data: list[dict[str, Any]],
    *,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Run standard quality checks for a dataset and record results.

    Runs checks appropriate for the dataset:
    - market_mark_daily: non-null keys, price ranges
    - wallet_pnl_daily: non-null wallet, PnL sanity
    - wallet_mtm_daily: non-null wallet, MTM sanity
    - wallet_position_snapshot_daily: non-null keys, position sanity

    Args:
        ch: ClickHouse client.
        dataset: Name of the dataset.
        partition: The partition date.
        data: List of row dicts to check.
        run_id: Optional pipeline run ID.

    Returns:
        List of quality check result dicts.
    """
    results: list[dict[str, Any]] = []

    if dataset == "market_mark_daily":
        results.extend(_check_market_marks(ch, dataset, partition, data, run_id))
    elif dataset == "wallet_pnl_daily":
        results.extend(_check_wallet_pnl(ch, dataset, partition, data, run_id))
    elif dataset == "wallet_mtm_daily":
        results.extend(_check_wallet_mtm(ch, dataset, partition, data, run_id))
    elif dataset == "wallet_position_snapshot_daily":
        results.extend(_check_wallet_positions(ch, dataset, partition, data, run_id))

    return results


def _check_market_marks(
    ch: Client,
    dataset: str,
    partition: date,
    data: list[dict[str, Any]],
    run_id: str | None,
) -> list[dict[str, Any]]:
    """Quality checks for market_mark_daily."""
    results: list[dict[str, Any]] = []

    # Check 1: Non-null market_id
    null_market_ids = sum(1 for row in data if not row.get("market_id"))
    status = "pass" if null_market_ids == 0 else "fail"
    results.append(
        record_quality_check(
            ch,
            dataset,
            partition,
            "non_null_market_id",
            status,
            observed_value=float(null_market_ids),
            expected="0 null values",
            run_id=run_id,
        )
    )

    # Check 2: Non-null outcome_id
    null_outcome_ids = sum(1 for row in data if not row.get("outcome_id"))
    status = "pass" if null_outcome_ids == 0 else "fail"
    results.append(
        record_quality_check(
            ch,
            dataset,
            partition,
            "non_null_outcome_id",
            status,
            observed_value=float(null_outcome_ids),
            expected="0 null values",
            run_id=run_id,
        )
    )

    # Check 3: Mark price in valid range [0, 1]
    invalid_prices = sum(
        1
        for row in data
        if row.get("mark_price") is not None
        and (row["mark_price"] < 0 or row["mark_price"] > 1)
    )
    status = "pass" if invalid_prices == 0 else "warn"
    results.append(
        record_quality_check(
            ch,
            dataset,
            partition,
            "mark_price_range",
            status,
            observed_value=float(invalid_prices),
            expected="prices in [0, 1]",
            run_id=run_id,
        )
    )

    # Check 4: Non-negative volume
    negative_volume = sum(
        1
        for row in data
        if row.get("volume_usd_24h") is not None and row["volume_usd_24h"] < 0
    )
    status = "pass" if negative_volume == 0 else "fail"
    results.append(
        record_quality_check(
            ch,
            dataset,
            partition,
            "non_negative_volume",
            status,
            observed_value=float(negative_volume),
            expected="0 negative values",
            run_id=run_id,
        )
    )

    return results


def _check_wallet_pnl(
    ch: Client,
    dataset: str,
    partition: date,
    data: list[dict[str, Any]],
    run_id: str | None,
) -> list[dict[str, Any]]:
    """Quality checks for wallet_pnl_daily."""
    results: list[dict[str, Any]] = []

    # Check 1: Non-null wallet
    null_wallets = sum(1 for row in data if not row.get("wallet"))
    status = "pass" if null_wallets == 0 else "fail"
    results.append(
        record_quality_check(
            ch,
            dataset,
            partition,
            "non_null_wallet",
            status,
            observed_value=float(null_wallets),
            expected="0 null values",
            run_id=run_id,
        )
    )

    # Check 2: PnL sanity - warn if any wallet has extreme PnL (> $1M)
    extreme_pnl = sum(
        1
        for row in data
        if row.get("realized_pnl_usd") is not None
        and abs(row["realized_pnl_usd"]) > 1_000_000
    )
    status = "pass" if extreme_pnl == 0 else "warn"
    results.append(
        record_quality_check(
            ch,
            dataset,
            partition,
            "pnl_sanity",
            status,
            observed_value=float(extreme_pnl),
            expected="|PnL| <= $1M per wallet",
            run_id=run_id,
        )
    )

    # Check 3: Non-negative volume
    negative_volume = sum(
        1
        for row in data
        if row.get("volume_usd") is not None and row["volume_usd"] < 0
    )
    status = "pass" if negative_volume == 0 else "fail"
    results.append(
        record_quality_check(
            ch,
            dataset,
            partition,
            "non_negative_volume",
            status,
            observed_value=float(negative_volume),
            expected="0 negative values",
            run_id=run_id,
        )
    )

    # Check 4: Wins + losses <= trades_count
    invalid_win_loss = sum(
        1
        for row in data
        if (row.get("wins") or 0) + (row.get("losses") or 0)
        > (row.get("trades_count") or 0)
    )
    status = "pass" if invalid_win_loss == 0 else "fail"
    results.append(
        record_quality_check(
            ch,
            dataset,
            partition,
            "win_loss_consistency",
            status,
            observed_value=float(invalid_win_loss),
            expected="wins + losses <= trades_count",
            run_id=run_id,
        )
    )

    return results


def _check_wallet_mtm(
    ch: Client,
    dataset: str,
    partition: date,
    data: list[dict[str, Any]],
    run_id: str | None,
) -> list[dict[str, Any]]:
    """Quality checks for wallet_mtm_daily."""
    results: list[dict[str, Any]] = []

    # Check 1: Non-null wallet
    null_wallets = sum(1 for row in data if not row.get("wallet"))
    status = "pass" if null_wallets == 0 else "fail"
    results.append(
        record_quality_check(
            ch,
            dataset,
            partition,
            "non_null_wallet",
            status,
            observed_value=float(null_wallets),
            expected="0 null values",
            run_id=run_id,
        )
    )

    # Check 2: MTM sanity - warn if any wallet has extreme MTM (> $10M)
    extreme_mtm = sum(
        1
        for row in data
        if row.get("mtm_usd") is not None and abs(row["mtm_usd"]) > 10_000_000
    )
    status = "pass" if extreme_mtm == 0 else "warn"
    results.append(
        record_quality_check(
            ch,
            dataset,
            partition,
            "mtm_sanity",
            status,
            observed_value=float(extreme_mtm),
            expected="|MTM| <= $10M per wallet",
            run_id=run_id,
        )
    )

    return results


def _check_wallet_positions(
    ch: Client,
    dataset: str,
    partition: date,
    data: list[dict[str, Any]],
    run_id: str | None,
) -> list[dict[str, Any]]:
    """Quality checks for wallet_position_snapshot_daily."""
    results: list[dict[str, Any]] = []

    # Check 1: Non-null wallet
    null_wallets = sum(1 for row in data if not row.get("wallet"))
    status = "pass" if null_wallets == 0 else "fail"
    results.append(
        record_quality_check(
            ch,
            dataset,
            partition,
            "non_null_wallet",
            status,
            observed_value=float(null_wallets),
            expected="0 null values",
            run_id=run_id,
        )
    )

    # Check 2: Non-null market_id
    null_market_ids = sum(1 for row in data if not row.get("market_id"))
    status = "pass" if null_market_ids == 0 else "fail"
    results.append(
        record_quality_check(
            ch,
            dataset,
            partition,
            "non_null_market_id",
            status,
            observed_value=float(null_market_ids),
            expected="0 null values",
            run_id=run_id,
        )
    )

    # Check 3: Non-null outcome_id
    null_outcome_ids = sum(1 for row in data if not row.get("outcome_id"))
    status = "pass" if null_outcome_ids == 0 else "fail"
    results.append(
        record_quality_check(
            ch,
            dataset,
            partition,
            "non_null_outcome_id",
            status,
            observed_value=float(null_outcome_ids),
            expected="0 null values",
            run_id=run_id,
        )
    )

    # Check 4: Position sanity - warn if extreme positions (> 1M contracts)
    extreme_positions = sum(
        1
        for row in data
        if row.get("position") is not None and abs(row["position"]) > 1_000_000
    )
    status = "pass" if extreme_positions == 0 else "warn"
    results.append(
        record_quality_check(
            ch,
            dataset,
            partition,
            "position_sanity",
            status,
            observed_value=float(extreme_positions),
            expected="|position| <= 1M",
            run_id=run_id,
        )
    )

    return results
