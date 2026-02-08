"""Silver Iceberg table definitions and initialization."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.table.sorting import NullOrder, SortDirection, SortField, SortOrder
from pyiceberg.transforms import DayTransform, IdentityTransform
from pyiceberg.types import (
    DoubleType,
    ListType,
    LongType,
    NestedField,
    StringType,
    TimestamptzType,
)

from prediction_data.core.logging import get_logger
from prediction_data.silver.catalog import SILVER_DATABASE

if TYPE_CHECKING:
    from pyiceberg.catalog import Catalog
    from pyiceberg.table import Table

logger = get_logger(__name__)

# Table properties shared by all Silver tables
TABLE_PROPERTIES = {
    "format-version": "2",
    "write.parquet.compression-codec": "zstd",
    "write.target-file-size-bytes": str(256 * 1024 * 1024),  # 256MB
    "write.delete.mode": "copy-on-write",
    "write.update.mode": "copy-on-write",
    "write.merge.mode": "copy-on-write",
}

# -- Polymarket Trades Schema --
# Derived from order_filled events (see RELEASE.md §4.2)
_POLYMARKET_TRADES_SCHEMA = Schema(
    NestedField(1, "event_ts", TimestamptzType(), required=True),
    NestedField(2, "platform_market_id", StringType(), required=True),
    NestedField(3, "platform_trade_id", StringType(), required=True),
    NestedField(4, "maker", StringType(), required=True),
    NestedField(5, "taker", StringType(), required=True),
    NestedField(6, "nonusdc_side", StringType(), required=True),
    NestedField(7, "maker_direction", StringType(), required=True),
    NestedField(8, "taker_direction", StringType(), required=True),
    NestedField(9, "price", DoubleType(), required=True),
    NestedField(10, "usd_amount", DoubleType(), required=True),
    NestedField(11, "token_amount", DoubleType(), required=True),
    NestedField(12, "transaction_hash", StringType(), required=False),
    NestedField(13, "bronze_run_id", StringType(), required=False),
    NestedField(14, "silver_ingestion_ts", TimestamptzType(), required=False),
)

# -- Polymarket Markets Schema --
_POLYMARKET_MARKETS_SCHEMA = Schema(
    NestedField(1, "event_ts", TimestamptzType(), required=True),
    NestedField(2, "platform_market_id", StringType(), required=True),
    NestedField(3, "question", StringType(), required=False),
    NestedField(4, "description", StringType(), required=False),
    NestedField(5, "market_slug", StringType(), required=False),
    NestedField(6, "status", StringType(), required=False),
    NestedField(7, "outcome", StringType(), required=False),
    NestedField(8, "tokens", StringType(), required=False),
    NestedField(9, "event_id", StringType(), required=False),
    NestedField(10, "updated_at", TimestamptzType(), required=False),
    NestedField(11, "bronze_run_id", StringType(), required=False),
    NestedField(12, "silver_ingestion_ts", TimestamptzType(), required=False),
)

# -- Polymarket Events Schema --
_POLYMARKET_EVENTS_SCHEMA = Schema(
    NestedField(1, "event_ts", TimestamptzType(), required=True),
    NestedField(2, "platform_event_id", StringType(), required=True),
    NestedField(3, "title", StringType(), required=False),
    NestedField(4, "description", StringType(), required=False),
    NestedField(5, "slug", StringType(), required=False),
    NestedField(6, "status", StringType(), required=False),
    NestedField(7, "category", StringType(), required=False),
    NestedField(8, "updated_at", TimestamptzType(), required=False),
    NestedField(9, "bronze_run_id", StringType(), required=False),
    NestedField(10, "silver_ingestion_ts", TimestamptzType(), required=False),
    NestedField(11, "image_url", StringType(), required=False),
    NestedField(
        12,
        "tags",
        ListType(element_id=13, element_type=StringType(), element_required=False),
        required=False,
    ),
)

# -- Kalshi Trades Schema (scaffold) --
_KALSHI_TRADES_SCHEMA = Schema(
    NestedField(1, "event_ts", TimestamptzType(), required=True),
    NestedField(2, "platform_market_id", StringType(), required=True),
    NestedField(3, "platform_trade_id", StringType(), required=True),
    NestedField(4, "side", StringType(), required=False),
    NestedField(5, "yes_price", DoubleType(), required=False),
    NestedField(6, "no_price", DoubleType(), required=False),
    NestedField(7, "count", LongType(), required=False),
    NestedField(8, "taker_side", StringType(), required=False),
    NestedField(9, "bronze_run_id", StringType(), required=False),
    NestedField(10, "silver_ingestion_ts", TimestamptzType(), required=False),
)

# -- Kalshi Markets Schema (scaffold) --
_KALSHI_MARKETS_SCHEMA = Schema(
    NestedField(1, "event_ts", TimestamptzType(), required=True),
    NestedField(2, "platform_market_id", StringType(), required=True),
    NestedField(3, "title", StringType(), required=False),
    NestedField(4, "subtitle", StringType(), required=False),
    NestedField(5, "status", StringType(), required=False),
    NestedField(6, "event_ticker", StringType(), required=False),
    NestedField(7, "series_ticker", StringType(), required=False),
    NestedField(8, "updated_at", TimestamptzType(), required=False),
    NestedField(9, "bronze_run_id", StringType(), required=False),
    NestedField(10, "silver_ingestion_ts", TimestamptzType(), required=False),
)

# -- Kalshi Events Schema (scaffold) --
_KALSHI_EVENTS_SCHEMA = Schema(
    NestedField(1, "event_ts", TimestamptzType(), required=True),
    NestedField(2, "platform_event_id", StringType(), required=True),
    NestedField(3, "title", StringType(), required=False),
    NestedField(4, "category", StringType(), required=False),
    NestedField(5, "status", StringType(), required=False),
    NestedField(6, "series_ticker", StringType(), required=False),
    NestedField(7, "updated_at", TimestamptzType(), required=False),
    NestedField(8, "bronze_run_id", StringType(), required=False),
    NestedField(9, "silver_ingestion_ts", TimestamptzType(), required=False),
)


def _partition_spec() -> PartitionSpec:
    """Partition by days(event_ts)."""
    return PartitionSpec(
        PartitionField(
            source_id=1,  # event_ts is always field 1
            field_id=1000,
            transform=DayTransform(),
            name="event_ts_day",
        )
    )


def _sort_order_trades() -> SortOrder:
    """Sort order for trades tables: platform_market_id, event_ts."""
    return SortOrder(
        SortField(
            source_id=2,  # platform_market_id
            transform=IdentityTransform(),
            direction=SortDirection.ASC,
            null_order=NullOrder.NULLS_LAST,
        ),
        SortField(
            source_id=1,  # event_ts
            transform=IdentityTransform(),
            direction=SortDirection.ASC,
            null_order=NullOrder.NULLS_LAST,
        ),
    )


def _sort_order_catalog() -> SortOrder:
    """Sort order for markets/events tables: primary ID, event_ts."""
    return SortOrder(
        SortField(
            source_id=2,  # platform_market_id or platform_event_id
            transform=IdentityTransform(),
            direction=SortDirection.ASC,
            null_order=NullOrder.NULLS_LAST,
        ),
        SortField(
            source_id=1,  # event_ts
            transform=IdentityTransform(),
            direction=SortDirection.ASC,
            null_order=NullOrder.NULLS_LAST,
        ),
    )


# Registry of all Silver tables: (namespace, table_name) -> (schema, sort_order)
SILVER_TABLES: dict[
    tuple[str, str],
    tuple[Schema, SortOrder],
] = {
    ("silver_polymarket", "trades"): (_POLYMARKET_TRADES_SCHEMA, _sort_order_trades()),
    ("silver_polymarket", "markets"): (_POLYMARKET_MARKETS_SCHEMA, _sort_order_catalog()),
    ("silver_polymarket", "events"): (_POLYMARKET_EVENTS_SCHEMA, _sort_order_catalog()),
    ("silver_kalshi", "trades"): (_KALSHI_TRADES_SCHEMA, _sort_order_trades()),
    ("silver_kalshi", "markets"): (_KALSHI_MARKETS_SCHEMA, _sort_order_catalog()),
    ("silver_kalshi", "events"): (_KALSHI_EVENTS_SCHEMA, _sort_order_catalog()),
}


def init_tables(
    catalog: Catalog,
    *,
    dry_run: bool = False,
) -> list[tuple[str, str]]:
    """Create all Silver Iceberg tables if they don't already exist.

    Args:
        catalog: PyIceberg catalog instance.
        dry_run: If True, log what would be created without creating.

    Returns:
        List of (namespace, table_name) tuples that were created (or would be).
    """
    partition_spec = _partition_spec()
    created: list[tuple[str, str]] = []

    for (namespace, table_name), (schema, sort_order) in SILVER_TABLES.items():
        full_name = f"{namespace}.{table_name}"

        if dry_run:
            logger.info("Would create table", table=full_name)
            created.append((namespace, table_name))
            continue

        # Ensure namespace exists
        try:
            catalog.create_namespace(namespace)
            logger.info("Created namespace", namespace=namespace)
        except Exception:
            # Namespace already exists — expected for idempotency
            pass

        # Create table if not exists
        identifier = (namespace, table_name)
        try:
            catalog.load_table(identifier)
            logger.info("Table already exists", table=full_name)
        except Exception:
            # Table doesn't exist — create it
            catalog.create_table(
                identifier=identifier,
                schema=schema,
                partition_spec=partition_spec,
                sort_order=sort_order,
                properties=TABLE_PROPERTIES,
            )
            logger.info("Created table", table=full_name)
            created.append((namespace, table_name))

    return created
