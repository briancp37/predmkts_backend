"""Compute daily mark prices and metrics from Silver trades.

Produces one row per (platform, market_id, outcome_id, day) with:
- VWAP mark price (volume-weighted average price)
- Last trade price
- 24h volume in USD
- 24h trade count
- 24h active wallet count
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import structlog

if TYPE_CHECKING:
    from pyiceberg.catalog import Catalog

logger = structlog.stdlib.get_logger(__name__)

# Minimum trades required for VWAP; below this, fall back to last trade price.
MIN_TRADES_FOR_VWAP = 3

MARKET_MARK_DAILY_SCHEMA = pa.schema(
    [
        pa.field("platform", pa.string()),
        pa.field("market_id", pa.string()),
        pa.field("outcome_id", pa.string()),
        pa.field("day_utc", pa.date32()),
        pa.field("mark_price", pa.float64()),
        pa.field("last_trade_price", pa.float64()),
        pa.field("volume_usd_24h", pa.float64()),
        pa.field("trades_count_24h", pa.uint64()),
        pa.field("active_wallets_24h", pa.uint64()),
        # Liquidity proxy: trailing 7-day average daily volume in USD.
        # Open interest is not feasible without position state tracking,
        # so we use trailing average volume as a liquidity proxy instead.
        pa.field("liquidity_metric", pa.float64()),
    ]
)

MARKET_MARK_DAILY_COLUMNS = [f.name for f in MARKET_MARK_DAILY_SCHEMA]


def _read_silver_trades_for_day(
    platform: str,
    dt: date,
    catalog: Catalog | None = None,
) -> pa.Table:
    """Read Silver trades for *platform* filtered to a single day."""
    if catalog is None:
        from prediction_data.silver.catalog import get_catalog

        catalog = get_catalog()

    namespace = f"silver_{platform}"
    table = catalog.load_table((namespace, "trades"))

    # Filter trades to the target day using Iceberg row filter.
    from pyiceberg.expressions import And, GreaterThanOrEqual, LessThan

    day_start = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
    next_day = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc).replace(
        day=dt.day
    )
    # Compute next day boundary
    from datetime import timedelta

    day_end = day_start + timedelta(days=1)

    row_filter = And(
        GreaterThanOrEqual("event_ts", day_start.isoformat()),
        LessThan("event_ts", day_end.isoformat()),
    )
    return table.scan(row_filter=row_filter).to_arrow()


def compute_vwap(prices: list[float], amounts: list[float]) -> float | None:
    """Compute volume-weighted average price.

    Returns *None* if there are no trades or total volume is zero.
    """
    if not prices or not amounts:
        return None
    total_volume = sum(amounts)
    if total_volume == 0:
        return None
    return sum(p * a for p, a in zip(prices, amounts)) / total_volume


def compute_marks_for_day(
    trades: list[dict[str, Any]],
    platform: str,
    dt: date,
) -> pa.Table:
    """Compute market_mark_daily rows from a list of trade dicts.

    Groups trades by (market_id, outcome_id) — where outcome_id is derived
    from the ``nonusdc_side`` field (the token ID that identifies the outcome).

    Args:
        trades: List of trade dicts from Silver (must have event_ts, platform_market_id,
            nonusdc_side, price, usd_amount, maker, taker fields).
        platform: Platform identifier (e.g. ``"polymarket"``).
        dt: The date being computed.

    Returns:
        PyArrow table conforming to MARKET_MARK_DAILY_SCHEMA.
    """
    # Group trades by (market_id, outcome_id).
    # outcome_id = nonusdc_side (the token ID for the outcome).
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for trade in trades:
        market_id = str(trade.get("platform_market_id", "") or "")
        outcome_id = str(trade.get("nonusdc_side", "") or "")
        if not market_id or not outcome_id:
            continue
        key = (market_id, outcome_id)
        groups.setdefault(key, []).append(trade)

    rows: dict[str, list[Any]] = {col: [] for col in MARKET_MARK_DAILY_COLUMNS}

    for (market_id, outcome_id), group_trades in groups.items():
        prices = [float(t["price"]) for t in group_trades if t.get("price") is not None]
        amounts = [
            float(t["usd_amount"]) for t in group_trades if t.get("usd_amount") is not None
        ]

        # Last trade price: sort by event_ts descending, take first.
        sorted_trades = sorted(
            [t for t in group_trades if t.get("event_ts") is not None],
            key=lambda t: t["event_ts"],
            reverse=True,
        )
        last_trade_price = (
            float(sorted_trades[0]["price"])
            if sorted_trades and sorted_trades[0].get("price") is not None
            else None
        )

        # VWAP or fallback to last trade price.
        if len(prices) >= MIN_TRADES_FOR_VWAP:
            mark_price = compute_vwap(prices, amounts)
        else:
            mark_price = last_trade_price

        # Volume.
        volume_usd = sum(amounts) if amounts else 0.0

        # Trade count.
        trades_count = len(group_trades)

        # Active wallets: distinct maker + taker addresses.
        wallets: set[str] = set()
        for t in group_trades:
            for field in ("maker", "taker"):
                addr = t.get(field)
                if addr:
                    wallets.add(str(addr))

        rows["platform"].append(platform)
        rows["market_id"].append(market_id)
        rows["outcome_id"].append(outcome_id)
        rows["day_utc"].append(dt)
        rows["mark_price"].append(mark_price)
        rows["last_trade_price"].append(last_trade_price)
        rows["volume_usd_24h"].append(volume_usd)
        rows["trades_count_24h"].append(trades_count)
        rows["active_wallets_24h"].append(len(wallets))
        # liquidity_metric is populated after compute via attach_liquidity_metric()
        rows["liquidity_metric"].append(None)

    return pa.table(rows, schema=MARKET_MARK_DAILY_SCHEMA)


# Number of days (including current) for trailing average volume liquidity proxy.
LIQUIDITY_WINDOW_DAYS = 7


def _read_gold_marks_for_day(
    gold_bucket: str,
    day: str,
    s3_client: Any | None = None,
) -> pa.Table | None:
    """Read a Gold market_mark_daily partition from S3, returning None if missing."""
    import io

    import pyarrow.parquet as pq

    if s3_client is None:
        import boto3

        s3_client = boto3.client("s3")

    key = f"gold/market_mark_daily/day={day}/part-000.parquet"
    try:
        resp = s3_client.get_object(Bucket=gold_bucket, Key=key)
        buf = io.BytesIO(resp["Body"].read())
        return pq.read_table(buf)
    except s3_client.exceptions.NoSuchKey:
        return None
    except Exception:
        logger.debug("could_not_read_gold_marks", day=day, key=key)
        return None


def attach_liquidity_metric(
    current_marks: pa.Table,
    prior_volumes: dict[tuple[str, str], list[float]],
) -> pa.Table:
    """Replace the liquidity_metric column with trailing 7-day avg daily volume.

    Args:
        current_marks: Today's mark table (liquidity_metric column is all-null).
        prior_volumes: Mapping of (market_id, outcome_id) to list of prior days'
            volume_usd_24h values (up to 6 prior days).

    Returns:
        New table with liquidity_metric filled in.
    """
    rows = current_marks.to_pylist()
    for row in rows:
        key = (row["market_id"], row["outcome_id"])
        prior = prior_volumes.get(key, [])
        all_volumes = prior + [row["volume_usd_24h"]]
        row["liquidity_metric"] = sum(all_volumes) / len(all_volumes)

    return pa.table(
        {col: [r[col] for r in rows] for col in MARKET_MARK_DAILY_COLUMNS},
        schema=MARKET_MARK_DAILY_SCHEMA,
    )


def _collect_prior_volumes(
    gold_bucket: str,
    dt: date,
    s3_client: Any | None = None,
) -> dict[tuple[str, str], list[float]]:
    """Read up to LIQUIDITY_WINDOW_DAYS-1 prior days and collect volumes per outcome."""
    from datetime import timedelta

    volumes: dict[tuple[str, str], list[float]] = {}
    for offset in range(1, LIQUIDITY_WINDOW_DAYS):
        prior_day = dt - timedelta(days=offset)
        tbl = _read_gold_marks_for_day(gold_bucket, str(prior_day), s3_client=s3_client)
        if tbl is None:
            continue
        for row in tbl.to_pylist():
            key = (row["market_id"], row["outcome_id"])
            volumes.setdefault(key, []).append(float(row["volume_usd_24h"]))
    return volumes


def compute_market_marks(
    *,
    platform: str = "polymarket",
    dt: date,
    catalog: Catalog | None = None,
    gold_bucket: str | None = None,
    s3_client: Any | None = None,
    clickhouse_client: Any | None = None,
    dry_run: bool = False,
) -> int:
    """Compute and store market_mark_daily for a single day.

    Reads Silver trades for the given date, computes VWAP and metrics per
    (market_id, outcome_id), and writes to S3 Gold Parquet.

    Args:
        platform: Platform to process.
        dt: Date to compute marks for.
        catalog: Optional PyIceberg catalog.
        gold_bucket: S3 bucket for Gold output. Skips S3 write if *None*.
        s3_client: Optional boto3 S3 client.
        clickhouse_client: Optional ClickHouse client. If provided, inserts marks into CH.
        dry_run: Preview without writing.

    Returns:
        Number of rows produced.
    """
    silver_trades = _read_silver_trades_for_day(platform, dt, catalog=catalog)
    trade_records = silver_trades.to_pylist()

    logger.info(
        "computing_market_marks",
        platform=platform,
        day=str(dt),
        silver_trades=len(trade_records),
    )

    mark_table = compute_marks_for_day(trade_records, platform, dt)
    num_rows: int = mark_table.num_rows

    logger.info("market_marks_computed", platform=platform, day=str(dt), rows=num_rows)

    # Attach liquidity metric (trailing 7-day avg volume) if we have a gold bucket.
    if gold_bucket and num_rows > 0:
        prior_volumes = _collect_prior_volumes(gold_bucket, dt, s3_client=s3_client)
        mark_table = attach_liquidity_metric(mark_table, prior_volumes)

    if dry_run:
        logger.info("dry_run_market_marks", rows=num_rows, day=str(dt))
        return num_rows

    # Write to S3 if bucket configured.
    if gold_bucket:
        from prediction_data.gold.s3_writer import write_gold_parquet

        write_gold_parquet(
            mark_table,
            gold_bucket,
            "market_mark_daily",
            str(dt),
            s3_client=s3_client,
        )

    # Insert into ClickHouse if client provided.
    if clickhouse_client is not None and num_rows > 0:
        _load_marks_to_clickhouse(mark_table, clickhouse_client)

    logger.info("loaded_market_marks", platform=platform, day=str(dt), rows=num_rows)
    return num_rows


def _load_marks_to_clickhouse(
    mark_table: pa.Table,
    clickhouse_client: Any,
) -> None:
    """Insert a market_mark_daily Arrow table into ClickHouse."""
    clickhouse_client.insert(
        "market_mark_daily",
        data=mark_table.to_pylist(),
        column_names=MARKET_MARK_DAILY_COLUMNS,
    )
    logger.info("inserted_market_marks_to_ch", rows=mark_table.num_rows)


def load_marks_to_clickhouse_from_s3(
    *,
    gold_bucket: str,
    lookback_days: int = 90,
    s3_client: Any | None = None,
    clickhouse_client: Any | None = None,
) -> int:
    """Load market_mark_daily partitions from S3 Gold into ClickHouse.

    Reads the most recent *lookback_days* of Gold partitions and inserts
    them into the ClickHouse ``market_mark_daily`` table.

    Args:
        gold_bucket: S3 bucket containing Gold Parquet files.
        lookback_days: Number of days to look back from today.
        s3_client: Optional boto3 S3 client.
        clickhouse_client: Optional ClickHouse client.

    Returns:
        Total number of rows loaded.
    """
    from datetime import timedelta

    if clickhouse_client is None:
        from prediction_data.gold.clickhouse import get_client

        clickhouse_client = get_client()

    if s3_client is None:
        import boto3

        s3_client = boto3.client("s3")

    today = date.today()
    total_rows = 0

    for offset in range(lookback_days):
        day = today - timedelta(days=offset)
        tbl = _read_gold_marks_for_day(gold_bucket, str(day), s3_client=s3_client)
        if tbl is None or tbl.num_rows == 0:
            continue
        _load_marks_to_clickhouse(tbl, clickhouse_client)
        total_rows += tbl.num_rows

    logger.info(
        "loaded_marks_from_s3_to_ch",
        lookback_days=lookback_days,
        total_rows=total_rows,
    )
    return total_rows
