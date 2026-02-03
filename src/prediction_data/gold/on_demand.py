"""On-demand reconstruction of historical position snapshots.

Given a wallet address and date range, replays fills from
wallet_position_ledger to rebuild the position state at each day
boundary, then joins with market_mark_daily to compute valuations.

Produces ``wallet_position_snapshot_daily`` rows with:
- Per-position detail: qty, avg_cost, mark_price, position_value_usd,
  unrealized_pnl_usd for each (wallet, platform, market_id, outcome_id, day).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import structlog

logger = structlog.stdlib.get_logger(__name__)

SNAPSHOT_SCHEMA = pa.schema(
    [
        pa.field("day_utc", pa.date32()),
        pa.field("wallet", pa.string()),
        pa.field("platform", pa.string()),
        pa.field("market_id", pa.string()),
        pa.field("outcome_id", pa.string()),
        pa.field("qty", pa.float64()),
        pa.field("avg_cost", pa.float64()),
        pa.field("mark_price", pa.float64()),
        pa.field("position_value_usd", pa.float64()),
        pa.field("unrealized_pnl_usd", pa.float64()),
    ]
)

SNAPSHOT_COLUMNS = [f.name for f in SNAPSHOT_SCHEMA]

TABLE_NAME = "wallet_position_snapshot_daily"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _date_range(start: date, end: date) -> list[date]:
    """Return inclusive list of dates from *start* to *end*."""
    dates: list[date] = []
    cur = start
    while cur <= end:
        dates.append(cur)
        cur += timedelta(days=1)
    return dates


def _check_existing_partitions(
    wallet: str,  # noqa: ARG001
    dates: list[date],
    gold_bucket: str,
    s3_client: Any,
) -> set[date]:
    """Return the subset of *dates* that already have S3 Gold partitions."""
    existing: set[date] = set()
    for dt in dates:
        prefix = f"gold/{TABLE_NAME}/day={dt}/"
        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=gold_bucket, Prefix=prefix):
            for _obj in page.get("Contents", []):
                # Check if wallet appears in the parquet filename or we need to
                # read the file.  For simplicity, if *any* file exists in the
                # partition we consider it present.  This is a coarse check —
                # the partition may contain data for other wallets too.  A more
                # precise check would read the parquet and filter by wallet.
                existing.add(dt)
                break
            if dt in existing:
                break
    return existing


def _read_ledger_for_wallet(
    wallet: str,
    start: date,
    end: date,
    clickhouse_client: Any,
) -> list[dict[str, Any]]:
    """Read all ledger fills for *wallet* within [start, end] from ClickHouse.

    Returns dicts with: ts, platform, market_id, outcome_id, side,
    qty_delta, price, fees_usd, avg_cost_after, qty_after.
    Rows are ordered by timestamp.
    """
    query = (
        "SELECT ts, platform, market_id, outcome_id, side, "
        "qty_delta, price, fees_usd, avg_cost_after, qty_after "
        "FROM wallet_position_ledger "
        "WHERE wallet = %(wallet)s "
        "AND toDate(ts) >= %(start)s "
        "AND toDate(ts) <= %(end)s "
        "ORDER BY ts"
    )
    result = clickhouse_client.query(
        query,
        parameters={
            "wallet": wallet,
            "start": str(start),
            "end": str(end),
        },
    )
    columns = [
        "ts", "platform", "market_id", "outcome_id", "side",
        "qty_delta", "price", "fees_usd", "avg_cost_after", "qty_after",
    ]
    return [dict(zip(columns, row, strict=False)) for row in result.result_rows]


def _read_initial_positions(
    wallet: str,
    before_date: date,
    clickhouse_client: Any,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Read wallet's position state just before *before_date*.

    Replays all ledger rows up to (but not including) *before_date* and
    returns the final state keyed by (platform, market_id, outcome_id).
    """
    query = (
        "SELECT platform, market_id, outcome_id, qty_after, avg_cost_after "
        "FROM wallet_position_ledger "
        "WHERE wallet = %(wallet)s "
        "AND toDate(ts) < %(before_date)s "
        "ORDER BY ts"
    )
    result = clickhouse_client.query(
        query,
        parameters={"wallet": wallet, "before_date": str(before_date)},
    )
    positions: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in result.result_rows:
        key = (str(row[0]), str(row[1]), str(row[2]))
        positions[key] = {
            "qty": float(row[3]),
            "avg_cost": float(row[4]),
        }
    # Remove positions with qty == 0.
    return {k: v for k, v in positions.items() if v["qty"] != 0}


def _read_marks_for_days(
    dates: list[date],
    clickhouse_client: Any,
) -> dict[tuple[date, str, str, str], float]:
    """Read market_mark_daily for all requested *dates*.

    Returns dict of (day, platform, market_id, outcome_id) -> mark_price.
    """
    if not dates:
        return {}
    query = (
        "SELECT day_utc, platform, market_id, outcome_id, mark_price "
        "FROM market_mark_daily FINAL "
        "WHERE day_utc >= %(start)s AND day_utc <= %(end)s"
    )
    result = clickhouse_client.query(
        query,
        parameters={"start": str(min(dates)), "end": str(max(dates))},
    )
    marks: dict[tuple[date, str, str, str], float] = {}
    for row in result.result_rows:
        day = row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0]))
        marks[(day, str(row[1]), str(row[2]), str(row[3]))] = float(row[4])
    return marks


def _replay_fills_to_snapshots(
    wallet: str,
    dates: list[date],
    initial_positions: dict[tuple[str, str, str], dict[str, Any]],
    fills: list[dict[str, Any]],
    marks: dict[tuple[date, str, str, str], float],
) -> pa.Table:
    """Replay fills day-by-day and produce snapshot rows.

    For each day boundary in *dates*, emits a snapshot row for every
    open position, valued using the mark price from *marks*.
    """
    # Index fills by date.
    fills_by_day: dict[date, list[dict[str, Any]]] = {}
    for f in fills:
        ts = f["ts"]
        fill_date = ts.date() if hasattr(ts, "date") else date.fromisoformat(str(ts)[:10])
        fills_by_day.setdefault(fill_date, []).append(f)

    # Current position state — will be mutated as we replay.
    positions = {k: dict(v) for k, v in initial_positions.items()}

    rows: dict[str, list[Any]] = {col: [] for col in SNAPSHOT_COLUMNS}

    for dt in dates:
        # Apply fills for this day.
        day_fills = fills_by_day.get(dt, [])
        for f in day_fills:
            key = (
                str(f.get("platform", "")),
                str(f.get("market_id", "")),
                str(f.get("outcome_id", "")),
            )
            positions[key] = {
                "qty": float(f.get("qty_after", 0)),
                "avg_cost": float(f.get("avg_cost_after", 0)),
            }

        # Remove closed positions (qty == 0).
        positions = {k: v for k, v in positions.items() if v["qty"] != 0}

        # Emit snapshot for each open position.
        for (platform, market_id, outcome_id), pos in sorted(positions.items()):
            qty = pos["qty"]
            avg_cost = pos["avg_cost"]
            mark_key = (dt, platform, market_id, outcome_id)
            mark_price = marks.get(mark_key)

            if mark_price is None:
                # Skip positions without a mark price for this day.
                logger.debug(
                    "snapshot_missing_mark",
                    wallet=wallet,
                    day=str(dt),
                    platform=platform,
                    market_id=market_id,
                    outcome_id=outcome_id,
                )
                # Still emit the row with NaN mark/values so position is visible.
                mark_price_val = float("nan")
                position_value = float("nan")
                unrealized_pnl = float("nan")
            else:
                mark_price_val = mark_price
                position_value = qty * mark_price
                unrealized_pnl = qty * (mark_price - avg_cost)

            rows["day_utc"].append(dt)
            rows["wallet"].append(wallet)
            rows["platform"].append(platform)
            rows["market_id"].append(market_id)
            rows["outcome_id"].append(outcome_id)
            rows["qty"].append(qty)
            rows["avg_cost"].append(avg_cost)
            rows["mark_price"].append(mark_price_val)
            rows["position_value_usd"].append(position_value)
            rows["unrealized_pnl_usd"].append(unrealized_pnl)

    return pa.table(rows, schema=SNAPSHOT_SCHEMA)


def compute_wallet_snapshots(
    *,
    wallet: str,
    start_date: date,
    end_date: date,
    gold_bucket: str | None = None,
    s3_client: Any | None = None,
    clickhouse_client: Any | None = None,
    dry_run: bool = False,
    skip_ch: bool = False,
) -> pa.Table:
    """Reconstruct historical position snapshots for a wallet.

    Checks S3 Gold for existing partitions, computes only missing days
    by replaying fills from ``wallet_position_ledger``, and joins with
    ``market_mark_daily`` for valuations.

    Args:
        wallet: Wallet address to compute snapshots for.
        start_date: First day (inclusive).
        end_date: Last day (inclusive).
        gold_bucket: S3 bucket for Gold data. When provided and not
            *dry_run*, existing partitions are checked and results written.
        s3_client: Optional boto3 S3 client.
        clickhouse_client: Optional ClickHouse client.
        dry_run: If True, compute but don't write.
        skip_ch: If True, skip ClickHouse loading (S3 only).

    Returns:
        PyArrow table of snapshot rows for the *missing* days.
    """
    import boto3 as _boto3

    if clickhouse_client is None:
        from prediction_data.gold.clickhouse import get_client
        clickhouse_client = get_client()

    all_dates = _date_range(start_date, end_date)

    # Determine which days need computation.
    if gold_bucket and not dry_run:
        if s3_client is None:
            s3_client = _boto3.client("s3")
        existing = _check_existing_partitions(wallet, all_dates, gold_bucket, s3_client)
    else:
        existing = set()

    missing_dates = sorted(d for d in all_dates if d not in existing)

    logger.info(
        "snapshot_plan",
        wallet=wallet,
        total_days=len(all_dates),
        existing_days=len(existing),
        missing_days=len(missing_dates),
    )

    if not missing_dates:
        logger.info("all_snapshots_exist", wallet=wallet)
        return pa.table(
            {col: [] for col in SNAPSHOT_COLUMNS}, schema=SNAPSHOT_SCHEMA
        )

    # Load initial position state (before the first missing date).
    initial_positions = _read_initial_positions(
        wallet, missing_dates[0], clickhouse_client
    )

    # Read fills covering the missing date range.
    fills = _read_ledger_for_wallet(
        wallet, missing_dates[0], missing_dates[-1], clickhouse_client
    )

    # Read marks for all missing dates.
    marks = _read_marks_for_days(missing_dates, clickhouse_client)

    logger.info(
        "snapshot_inputs",
        wallet=wallet,
        initial_positions=len(initial_positions),
        fills=len(fills),
        marks=len(marks),
    )

    snapshot_table = _replay_fills_to_snapshots(
        wallet, missing_dates, initial_positions, fills, marks
    )

    logger.info(
        "snapshots_computed",
        wallet=wallet,
        rows=snapshot_table.num_rows,
        days=len(missing_dates),
    )

    if dry_run:
        logger.info("dry_run_snapshots", rows=snapshot_table.num_rows)
        return snapshot_table

    # Write to S3 Gold — one partition per day.
    days_written: set[date] = set()
    ch_dates: list[date] = []
    if gold_bucket:
        from prediction_data.gold.s3_writer import write_gold_parquet

        if s3_client is None:
            s3_client = _boto3.client("s3")

        days_written = set()
        for dt in missing_dates:
            # Filter table to just this day.
            mask = pc.equal(snapshot_table.column("day_utc"), pa.scalar(dt, pa.date32()))
            day_table = snapshot_table.filter(mask)
            if day_table.num_rows == 0:
                continue
            write_gold_parquet(
                day_table, gold_bucket, TABLE_NAME, str(dt), s3_client=s3_client
            )
            days_written.add(dt)

        logger.info(
            "snapshots_written_s3",
            wallet=wallet,
            partitions=len(days_written),
        )

    # Load recent partitions into ClickHouse (hot mirror).
    if not skip_ch:
        from prediction_data.gold.config import DEFAULT_TTL_DAYS

        cutoff = date.today() - timedelta(days=DEFAULT_TTL_DAYS)
        ch_dates = [d for d in missing_dates if d >= cutoff]
        if ch_dates:
            # Filter snapshot table to only CH-eligible dates.
            ch_mask = pc.greater_equal(
                snapshot_table.column("day_utc"),
                pa.scalar(cutoff, pa.date32()),
            )
            ch_table = snapshot_table.filter(ch_mask)
            if ch_table.num_rows > 0:
                clickhouse_client.insert(
                    TABLE_NAME,
                    data=ch_table.to_pylist(),
                    column_names=SNAPSHOT_COLUMNS,
                )
                logger.info(
                    "snapshots_loaded_ch",
                    wallet=wallet,
                    rows=ch_table.num_rows,
                    days=len(ch_dates),
                )
        else:
            logger.info(
                "snapshots_ch_skipped_all_outside_ttl",
                wallet=wallet,
                ttl_days=DEFAULT_TTL_DAYS,
            )

    # Summary log.
    logger.info(
        "compute_wallet_snapshots_summary",
        wallet=wallet,
        partitions_computed=len(missing_dates),
        partitions_cached_s3=len(days_written) if gold_bucket else 0,
        partitions_cached_ch=len(ch_dates) if not skip_ch else 0,
        rows_written=snapshot_table.num_rows,
    )

    return snapshot_table
