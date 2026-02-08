"""Gold dimension table loaders."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import structlog

from prediction_data.gold.canonical import CanonicalResolver
from prediction_data.gold.clickhouse import get_client
from prediction_data.gold.s3_writer import write_gold_parquet

if TYPE_CHECKING:
    from pyiceberg.catalog import Catalog

logger = structlog.stdlib.get_logger(__name__)

# Static platform data.
PLATFORMS = [
    {
        "platform_id": "polymarket",
        "platform_name": "Polymarket",
        "url": "https://polymarket.com",
    },
    {
        "platform_id": "kalshi",
        "platform_name": "Kalshi",
        "url": "https://kalshi.com",
    },
]

DIM_PLATFORM_SCHEMA = pa.schema(
    [
        pa.field("platform_id", pa.string()),
        pa.field("platform_name", pa.string()),
        pa.field("url", pa.string()),
    ]
)


def _platforms_to_arrow() -> pa.Table:
    """Convert static platform data to a PyArrow table."""
    return pa.table(
        {
            "platform_id": [p["platform_id"] for p in PLATFORMS],
            "platform_name": [p["platform_name"] for p in PLATFORMS],
            "url": [p["url"] for p in PLATFORMS],
        },
        schema=DIM_PLATFORM_SCHEMA,
    )


def load_dim_platform(
    *,
    gold_bucket: str | None = None,
    s3_client: Any | None = None,
    clickhouse_client: Any | None = None,
    dry_run: bool = False,
) -> int:
    """Load the dim_platform dimension table.

    Writes static platform rows to S3 Gold Parquet and inserts into ClickHouse.

    Args:
        gold_bucket: S3 bucket for Gold output. Skips S3 write if *None*.
        s3_client: Optional boto3 S3 client.
        clickhouse_client: Optional ClickHouse client. Creates one if *None*.
        dry_run: Preview without writing.

    Returns:
        Number of rows loaded.
    """
    table = _platforms_to_arrow()
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    num_rows: int = table.num_rows

    if dry_run:
        logger.info("dry_run_dim_platform", rows=num_rows, day=day)
        return num_rows

    # Write to S3 if bucket configured.
    if gold_bucket:
        write_gold_parquet(
            table,
            gold_bucket,
            "dim_platform",
            day,
            s3_client=s3_client,
        )

    # Insert into ClickHouse.
    ch = clickhouse_client or get_client()
    ch.insert(
        "dim_platform",
        data=[[p["platform_id"], p["platform_name"], p["url"]] for p in PLATFORMS],
        column_names=["platform_id", "platform_name", "url"],
    )

    logger.info("loaded_dim_platform", rows=num_rows, day=day)
    return num_rows


# ---------------------------------------------------------------------------
# dim_market
# ---------------------------------------------------------------------------

DIM_MARKET_SCHEMA = pa.schema(
    [
        pa.field("platform", pa.string()),
        pa.field("platform_market_id", pa.string()),
        pa.field("canonical_market_id", pa.string()),
        pa.field("question", pa.string()),
        pa.field("description", pa.string()),
        pa.field("market_slug", pa.string()),
        pa.field("status", pa.string()),
        pa.field("event_id", pa.string()),
        pa.field("tokens", pa.string()),
    ]
)

DIM_MARKET_COLUMNS = [f.name for f in DIM_MARKET_SCHEMA]


def _read_silver_markets(
    platform: str,
    catalog: Catalog | None = None,
) -> pa.Table:
    """Read the Silver markets table for *platform* via PyIceberg.

    Deduplicates by platform_market_id, keeping the record with the latest
    updated_at timestamp. This supports append-only Silver ingestion where
    duplicates are cleaned up during maintenance compaction.
    """
    if catalog is None:
        from prediction_data.silver.catalog import get_catalog

        catalog = get_catalog()

    namespace = f"silver_{platform}"
    table = catalog.load_table((namespace, "markets"))
    arrow = table.scan().to_arrow()

    # Dedupe: keep latest record per platform_market_id by updated_at
    if arrow.num_rows == 0:
        return arrow

    records = arrow.to_pylist()
    latest_by_id: dict[str, dict[str, Any]] = {}
    for rec in records:
        market_id = rec.get("platform_market_id", "")
        updated_at = rec.get("updated_at")
        existing = latest_by_id.get(market_id)
        if existing is None or (updated_at and updated_at > existing.get("updated_at")):
            latest_by_id[market_id] = rec

    deduped = list(latest_by_id.values())
    return pa.Table.from_pylist(deduped, schema=arrow.schema)


def _silver_to_dim_market(
    arrow: pa.Table,
    platform: str,
    resolver: CanonicalResolver,
) -> pa.Table:
    """Transform Silver markets Arrow table into dim_market rows."""
    records = arrow.to_pylist()

    rows: dict[str, list[Any]] = {col: [] for col in DIM_MARKET_COLUMNS}

    for rec in records:
        pid = str(rec.get("platform_market_id", "") or "")
        rows["platform"].append(platform)
        rows["platform_market_id"].append(pid)
        rows["canonical_market_id"].append(resolver.resolve(platform, pid))
        rows["question"].append(str(rec.get("question", "") or ""))
        rows["description"].append(str(rec.get("description", "") or ""))
        rows["market_slug"].append(str(rec.get("market_slug", "") or ""))
        rows["status"].append(str(rec.get("status", "") or ""))
        rows["event_id"].append(str(rec.get("event_id", "") or ""))
        rows["tokens"].append(str(rec.get("tokens", "") or ""))

    return pa.table(rows, schema=DIM_MARKET_SCHEMA)


def load_dim_market(
    *,
    gold_bucket: str | None = None,
    s3_client: Any | None = None,
    clickhouse_client: Any | None = None,
    catalog: Catalog | None = None,
    resolver: CanonicalResolver | None = None,
    dry_run: bool = False,
) -> int:
    """Load the dim_market dimension table.

    Reads Silver polymarket.markets, applies canonical ID resolution,
    and writes to S3 Gold Parquet + ClickHouse.

    Returns:
        Number of rows loaded.
    """
    resolver = resolver or CanonicalResolver()
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Read and transform Polymarket markets.
    silver_arrow = _read_silver_markets("polymarket", catalog=catalog)
    dim_table = _silver_to_dim_market(silver_arrow, "polymarket", resolver)

    num_rows: int = dim_table.num_rows
    logger.info("dim_market_transformed", platform="polymarket", rows=num_rows)

    if dry_run:
        logger.info("dry_run_dim_market", rows=num_rows, day=day)
        return num_rows

    # Write to S3 if bucket configured.
    if gold_bucket:
        write_gold_parquet(
            dim_table,
            gold_bucket,
            "dim_market",
            day,
            s3_client=s3_client,
        )

    # Insert into ClickHouse.
    ch = clickhouse_client or get_client()
    # Convert to list of lists for insert (pylist returns dicts which need column_names removed)
    rows = dim_table.to_pylist()
    data = [[row[col] for col in DIM_MARKET_COLUMNS] for row in rows]
    ch.insert(
        "dim_market",
        data=data,
        column_names=DIM_MARKET_COLUMNS,
    )

    logger.info("loaded_dim_market", rows=num_rows, day=day)
    return num_rows


# ---------------------------------------------------------------------------
# dim_outcome
# ---------------------------------------------------------------------------

DIM_OUTCOME_SCHEMA = pa.schema(
    [
        pa.field("platform", pa.string()),
        pa.field("market_id", pa.string()),
        pa.field("outcome_id", pa.string()),
        pa.field("token_id", pa.string()),
        pa.field("side", pa.string()),
        pa.field("outcome_label", pa.string()),
    ]
)

DIM_OUTCOME_COLUMNS = [f.name for f in DIM_OUTCOME_SCHEMA]


def _parse_json_array(json_str: str | None) -> list[str]:
    """Parse a JSON array string into a list of strings.

    Returns an empty list on None, empty string, or invalid JSON.
    """
    if not json_str:
        return []
    try:
        parsed = json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return []


def parse_tokens(json_str: str | None) -> list[dict[str, Any]]:
    """Parse a JSON array of token objects.

    Returns a list of dicts, filtering out any non-dict items.
    Returns an empty list on None, empty string, or invalid JSON.
    """
    if not json_str:
        return []
    try:
        parsed = json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _silver_to_dim_outcome(
    arrow: pa.Table,
    platform: str,
) -> pa.Table:
    """Transform Silver markets Arrow table into dim_outcome rows.

    Each market with N tokens produces N outcome rows.  The *side* field is
    ``token1`` for index 0, ``token2`` for index 1, etc.

    Silver markets have:
    - tokens: JSON array of token ID strings (e.g. '["123...", "456..."]')
    - outcome: JSON array of outcome labels (e.g. '["Yes", "No"]' or '["Over", "Under"]')
    """
    records = arrow.to_pylist()

    rows: dict[str, list[Any]] = {col: [] for col in DIM_OUTCOME_COLUMNS}

    for rec in records:
        market_id = str(rec.get("platform_market_id", "") or "")
        token_ids = _parse_json_array(rec.get("tokens"))
        outcome_labels = _parse_json_array(rec.get("outcome"))

        # Pair token IDs with outcome labels; if no labels, use empty strings
        for idx, token_id in enumerate(token_ids):
            outcome_label = outcome_labels[idx] if idx < len(outcome_labels) else ""
            # outcome_id: deterministic composite key
            outcome_id = f"{market_id}_{idx}"
            side = f"token{idx + 1}"

            rows["platform"].append(platform)
            rows["market_id"].append(market_id)
            rows["outcome_id"].append(outcome_id)
            rows["token_id"].append(token_id)
            rows["side"].append(side)
            rows["outcome_label"].append(outcome_label)

    return pa.table(rows, schema=DIM_OUTCOME_SCHEMA)


def load_dim_outcome(
    *,
    gold_bucket: str | None = None,
    s3_client: Any | None = None,
    clickhouse_client: Any | None = None,
    catalog: Catalog | None = None,
    dry_run: bool = False,
) -> int:
    """Load the dim_outcome dimension table.

    Reads Silver polymarket.markets, parses the tokens field, and writes
    one row per outcome to S3 Gold Parquet + ClickHouse.

    Returns:
        Number of rows loaded.
    """
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    silver_arrow = _read_silver_markets("polymarket", catalog=catalog)
    dim_table = _silver_to_dim_outcome(silver_arrow, "polymarket")

    num_rows: int = dim_table.num_rows
    logger.info("dim_outcome_transformed", platform="polymarket", rows=num_rows)

    if dry_run:
        logger.info("dry_run_dim_outcome", rows=num_rows, day=day)
        return num_rows

    # Write to S3 if bucket configured.
    if gold_bucket:
        write_gold_parquet(
            dim_table,
            gold_bucket,
            "dim_outcome",
            day,
            s3_client=s3_client,
        )

    # Insert into ClickHouse.
    ch = clickhouse_client or get_client()
    rows = dim_table.to_pylist()
    data = [[row[col] for col in DIM_OUTCOME_COLUMNS] for row in rows]
    ch.insert(
        "dim_outcome",
        data=data,
        column_names=DIM_OUTCOME_COLUMNS,
    )

    logger.info("loaded_dim_outcome", rows=num_rows, day=day)
    return num_rows


# ---------------------------------------------------------------------------
# dim_wallet
# ---------------------------------------------------------------------------

DIM_WALLET_SCHEMA = pa.schema(
    [
        pa.field("platform", pa.string()),
        pa.field("wallet_address", pa.string()),
        pa.field("first_trade_ts", pa.timestamp("us", tz="UTC")),
        pa.field("last_trade_ts", pa.timestamp("us", tz="UTC")),
        pa.field("trade_count", pa.uint64()),
    ]
)

DIM_WALLET_COLUMNS = [f.name for f in DIM_WALLET_SCHEMA]


def _read_silver_trades(
    platform: str,
    catalog: Catalog | None = None,
) -> pa.Table:
    """Read the Silver trades table for *platform* via PyIceberg."""
    if catalog is None:
        from prediction_data.silver.catalog import get_catalog

        catalog = get_catalog()

    namespace = f"silver_{platform}"
    table = catalog.load_table((namespace, "trades"))
    return table.scan().to_arrow()


def _silver_trades_to_dim_wallet(
    arrow: pa.Table,
    platform: str,
) -> pa.Table:
    """Extract unique wallets from Silver trades maker/taker columns.

    Each distinct wallet address produces one row with aggregated stats:
    first_trade_ts, last_trade_ts, and trade_count.
    """
    records = arrow.to_pylist()

    # Accumulate per-wallet stats.
    wallets: dict[str, dict[str, Any]] = {}

    for rec in records:
        ts = rec.get("event_ts")
        for addr_field in ("maker", "taker"):
            addr = rec.get(addr_field)
            if not addr:
                continue
            addr = str(addr)
            if addr in wallets:
                w = wallets[addr]
                w["trade_count"] += 1
                if ts is not None:
                    if w["first_trade_ts"] is None or ts < w["first_trade_ts"]:
                        w["first_trade_ts"] = ts
                    if w["last_trade_ts"] is None or ts > w["last_trade_ts"]:
                        w["last_trade_ts"] = ts
            else:
                wallets[addr] = {
                    "first_trade_ts": ts,
                    "last_trade_ts": ts,
                    "trade_count": 1,
                }

    rows: dict[str, list[Any]] = {col: [] for col in DIM_WALLET_COLUMNS}
    for addr, stats in wallets.items():
        rows["platform"].append(platform)
        rows["wallet_address"].append(addr)
        rows["first_trade_ts"].append(stats["first_trade_ts"])
        rows["last_trade_ts"].append(stats["last_trade_ts"])
        rows["trade_count"].append(stats["trade_count"])

    return pa.table(rows, schema=DIM_WALLET_SCHEMA)


def load_dim_wallet(
    *,
    gold_bucket: str | None = None,
    s3_client: Any | None = None,
    clickhouse_client: Any | None = None,
    catalog: Catalog | None = None,
    dry_run: bool = False,
) -> int:
    """Load the dim_wallet dimension table.

    Reads Silver polymarket.trades, extracts unique wallets from maker/taker,
    aggregates trade statistics, and writes to S3 Gold Parquet + ClickHouse.

    Returns:
        Number of rows loaded.
    """
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    silver_arrow = _read_silver_trades("polymarket", catalog=catalog)
    dim_table = _silver_trades_to_dim_wallet(silver_arrow, "polymarket")

    num_rows: int = dim_table.num_rows
    logger.info("dim_wallet_transformed", platform="polymarket", rows=num_rows)

    if dry_run:
        logger.info("dry_run_dim_wallet", rows=num_rows, day=day)
        return num_rows

    # Write to S3 if bucket configured.
    if gold_bucket:
        write_gold_parquet(
            dim_table,
            gold_bucket,
            "dim_wallet",
            day,
            s3_client=s3_client,
        )

    # Insert into ClickHouse.
    ch = clickhouse_client or get_client()
    rows = dim_table.to_pylist()
    data = [[row[col] for col in DIM_WALLET_COLUMNS] for row in rows]
    ch.insert(
        "dim_wallet",
        data=data,
        column_names=DIM_WALLET_COLUMNS,
    )

    logger.info("loaded_dim_wallet", rows=num_rows, day=day)
    return num_rows


# ---------------------------------------------------------------------------
# dim_event
# ---------------------------------------------------------------------------

DIM_EVENT_SCHEMA = pa.schema(
    [
        pa.field("platform", pa.string()),
        pa.field("platform_event_id", pa.string()),
        pa.field("title", pa.string()),
        pa.field("description", pa.string()),
        pa.field("slug", pa.string()),
        pa.field("status", pa.string()),
        pa.field("category", pa.string()),
    ]
)

DIM_EVENT_COLUMNS = [f.name for f in DIM_EVENT_SCHEMA]


def _read_silver_events(
    platform: str,
    catalog: Catalog | None = None,
) -> pa.Table:
    """Read the Silver events table for *platform* via PyIceberg.

    Deduplicates by platform_event_id, keeping the record with the latest
    updated_at timestamp. This supports append-only Silver ingestion where
    duplicates are cleaned up during maintenance compaction.
    """
    if catalog is None:
        from prediction_data.silver.catalog import get_catalog

        catalog = get_catalog()

    namespace = f"silver_{platform}"
    table = catalog.load_table((namespace, "events"))
    arrow = table.scan().to_arrow()

    # Dedupe: keep latest record per platform_event_id by updated_at
    if arrow.num_rows == 0:
        return arrow

    records = arrow.to_pylist()
    latest_by_id: dict[str, dict[str, Any]] = {}
    for rec in records:
        event_id = rec.get("platform_event_id", "")
        updated_at = rec.get("updated_at")
        existing = latest_by_id.get(event_id)
        if existing is None or (updated_at and updated_at > existing.get("updated_at")):
            latest_by_id[event_id] = rec

    deduped = list(latest_by_id.values())
    return pa.Table.from_pylist(deduped, schema=arrow.schema)


def _silver_to_dim_event(
    arrow: pa.Table,
    platform: str,
) -> pa.Table:
    """Transform Silver events Arrow table into dim_event rows.

    Deduplicates by platform_event_id, keeping the last occurrence
    (which has the most recent updated_at in a sorted Silver table).
    """
    records = arrow.to_pylist()

    # Deduplicate by platform_event_id (last-write-wins).
    seen: dict[str, dict[str, Any]] = {}
    for rec in records:
        pid = str(rec.get("platform_event_id", "") or "")
        seen[pid] = rec

    rows: dict[str, list[Any]] = {col: [] for col in DIM_EVENT_COLUMNS}

    for pid, rec in seen.items():
        rows["platform"].append(platform)
        rows["platform_event_id"].append(pid)
        rows["title"].append(str(rec.get("title", "") or ""))
        rows["description"].append(str(rec.get("description", "") or ""))
        rows["slug"].append(str(rec.get("slug", "") or ""))
        rows["status"].append(str(rec.get("status", "") or ""))
        rows["category"].append(str(rec.get("category", "") or ""))

    return pa.table(rows, schema=DIM_EVENT_SCHEMA)


def load_dim_event(
    *,
    gold_bucket: str | None = None,
    s3_client: Any | None = None,
    clickhouse_client: Any | None = None,
    catalog: Catalog | None = None,
    dry_run: bool = False,
) -> int:
    """Load the dim_event dimension table.

    Reads Silver polymarket.events, transforms to dim_event rows,
    and writes to S3 Gold Parquet + ClickHouse.

    Returns:
        Number of rows loaded.
    """
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Read and transform Polymarket events.
    silver_arrow = _read_silver_events("polymarket", catalog=catalog)
    dim_table = _silver_to_dim_event(silver_arrow, "polymarket")

    num_rows: int = dim_table.num_rows
    logger.info("dim_event_transformed", platform="polymarket", rows=num_rows)

    if dry_run:
        logger.info("dry_run_dim_event", rows=num_rows, day=day)
        return num_rows

    # Write to S3 if bucket configured.
    if gold_bucket:
        write_gold_parquet(
            dim_table,
            gold_bucket,
            "dim_event",
            day,
            s3_client=s3_client,
        )

    # Insert into ClickHouse.
    ch = clickhouse_client or get_client()
    rows = dim_table.to_pylist()
    data = [[row[col] for col in DIM_EVENT_COLUMNS] for row in rows]
    ch.insert(
        "dim_event",
        data=data,
        column_names=DIM_EVENT_COLUMNS,
    )

    logger.info("loaded_dim_event", rows=num_rows, day=day)
    return num_rows


# ---------------------------------------------------------------------------
# dim_category
# ---------------------------------------------------------------------------

DIM_CATEGORY_SCHEMA = pa.schema(
    [
        pa.field("platform", pa.string()),
        pa.field("category", pa.string()),
        pa.field("event_count", pa.uint64()),
    ]
)

DIM_CATEGORY_COLUMNS = [f.name for f in DIM_CATEGORY_SCHEMA]


def _silver_events_to_dim_category(
    arrow: pa.Table,
    platform: str,
) -> pa.Table:
    """Extract distinct categories from Silver events with event counts.

    Groups events by category and counts occurrences.  Deduplicates events
    by platform_event_id before counting so that delta duplicates don't
    inflate the totals.
    """
    records = arrow.to_pylist()

    # Deduplicate events by platform_event_id first (same as dim_event).
    seen: dict[str, dict[str, Any]] = {}
    for rec in records:
        pid = str(rec.get("platform_event_id", "") or "")
        seen[pid] = rec

    # Count events per category.
    counts: dict[str, int] = {}
    for rec in seen.values():
        cat = str(rec.get("category", "") or "")
        counts[cat] = counts.get(cat, 0) + 1

    rows: dict[str, list[Any]] = {col: [] for col in DIM_CATEGORY_COLUMNS}
    for cat, count in sorted(counts.items()):
        rows["platform"].append(platform)
        rows["category"].append(cat)
        rows["event_count"].append(count)

    return pa.table(rows, schema=DIM_CATEGORY_SCHEMA)


def load_dim_category(
    *,
    gold_bucket: str | None = None,
    s3_client: Any | None = None,
    clickhouse_client: Any | None = None,
    catalog: Catalog | None = None,
    dry_run: bool = False,
) -> int:
    """Load the dim_category dimension table.

    Reads Silver polymarket.events, extracts distinct categories with
    event counts, and writes to S3 Gold Parquet + ClickHouse.

    Returns:
        Number of rows loaded.
    """
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    silver_arrow = _read_silver_events("polymarket", catalog=catalog)
    dim_table = _silver_events_to_dim_category(silver_arrow, "polymarket")

    num_rows: int = dim_table.num_rows
    logger.info("dim_category_transformed", platform="polymarket", rows=num_rows)

    if dry_run:
        logger.info("dry_run_dim_category", rows=num_rows, day=day)
        return num_rows

    # Write to S3 if bucket configured.
    if gold_bucket:
        write_gold_parquet(
            dim_table,
            gold_bucket,
            "dim_category",
            day,
            s3_client=s3_client,
        )

    # Insert into ClickHouse.
    ch = clickhouse_client or get_client()
    rows = dim_table.to_pylist()
    data = [[row[col] for col in DIM_CATEGORY_COLUMNS] for row in rows]
    ch.insert(
        "dim_category",
        data=data,
        column_names=DIM_CATEGORY_COLUMNS,
    )

    logger.info("loaded_dim_category", rows=num_rows, day=day)
    return num_rows
