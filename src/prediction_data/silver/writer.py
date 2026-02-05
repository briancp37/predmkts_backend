"""Iceberg writer for Silver processing pipeline.

Supports both append and upsert (merge) writes to Iceberg tables via
PyIceberg.  Upsert uses ``Table.upsert()`` with entity-specific join keys
to deduplicate across writes — existing rows matching on join keys are
updated, new rows are inserted.

Write properties (ZSTD compression, 256 MB target file size) are configured
at table creation time in ``silver.tables``.
"""

from __future__ import annotations

import dataclasses
import time
from typing import TYPE_CHECKING, Any

import pyarrow as pa
from pyiceberg.io.pyarrow import schema_to_pyarrow

from prediction_data.core.logging import get_logger
from prediction_data.silver.tables import SILVER_TABLES

if TYPE_CHECKING:
    from pyiceberg.catalog import Catalog
    from pyiceberg.schema import Schema
    from pyiceberg.table import Table

logger = get_logger(__name__)


class IcebergWriteError(Exception):
    """Raised when writing to an Iceberg table fails."""


@dataclasses.dataclass(slots=True)
class WriteResult:
    """Metadata returned after a successful Iceberg write."""

    namespace: str
    table_name: str
    rows_written: int
    snapshot_id: int
    duration_seconds: float
    rows_inserted: int = 0
    rows_updated: int = 0


def _to_arrow_table(
    records: list[dict[str, Any]],
    iceberg_schema: Schema,
) -> pa.Table:
    """Convert a list of normalized dicts to a PyArrow Table.

    Args:
        records: Normalized Silver dicts — keys must match Iceberg field names.
        iceberg_schema: The PyIceberg schema for the target table.

    Returns:
        A PyArrow Table with schema derived from the Iceberg schema.

    Raises:
        IcebergWriteError: If conversion fails (e.g. type mismatch).
    """
    arrow_schema = schema_to_pyarrow(iceberg_schema)
    columns: dict[str, list[Any]] = {field.name: [] for field in arrow_schema}

    for rec in records:
        for col_name in columns:
            columns[col_name].append(rec.get(col_name))

    try:
        return pa.table(columns, schema=arrow_schema)
    except (pa.ArrowInvalid, pa.ArrowTypeError, pa.ArrowNotImplementedError) as exc:
        msg = f"Failed to convert {len(records)} records to Arrow: {exc}"
        raise IcebergWriteError(msg) from exc


def _resolve_table(
    catalog: Catalog,
    namespace: str,
    table_name: str,
) -> Table:
    """Load an Iceberg table, raising a clear error if it doesn't exist."""
    identifier = (namespace, table_name)
    try:
        return catalog.load_table(identifier)
    except Exception as exc:
        msg = f"Table {namespace}.{table_name} not found in catalog"
        raise IcebergWriteError(msg) from exc


def write_to_iceberg(
    records: list[dict[str, Any]],
    catalog: Catalog,
    namespace: str,
    table_name: str,
) -> WriteResult:
    """Write normalized records to an Iceberg table.

    Converts *records* to a PyArrow Table using the Iceberg schema registered
    in ``SILVER_TABLES``, appends via PyIceberg, and returns metadata
    including the new snapshot ID.

    Args:
        records: Normalized Silver dicts ready for writing.
        catalog: PyIceberg catalog instance.
        namespace: Iceberg namespace (e.g. ``"silver_polymarket"``).
        table_name: Iceberg table name (e.g. ``"trades"``).

    Returns:
        A :class:`WriteResult` with write metadata.

    Raises:
        IcebergWriteError: On empty input, schema mismatch, or write failure.
        KeyError: If ``(namespace, table_name)`` is not in ``SILVER_TABLES``.
    """
    if not records:
        msg = "Cannot write empty record batch"
        raise IcebergWriteError(msg)

    schema, _sort_order = SILVER_TABLES[(namespace, table_name)]

    logger.info(
        "iceberg_write_start",
        namespace=namespace,
        table=table_name,
        rows=len(records),
    )

    t0 = time.monotonic()

    arrow_table = _to_arrow_table(records, schema)
    table = _resolve_table(catalog, namespace, table_name)

    try:
        table.append(arrow_table)
    except Exception as exc:
        msg = f"Iceberg append failed for {namespace}.{table_name}: {exc}"
        raise IcebergWriteError(msg) from exc

    snapshot = table.current_snapshot()
    snapshot_id = snapshot.snapshot_id if snapshot else -1

    duration = time.monotonic() - t0

    logger.info(
        "iceberg_write_done",
        namespace=namespace,
        table=table_name,
        rows=len(records),
        snapshot_id=snapshot_id,
        duration_s=round(duration, 2),
    )

    return WriteResult(
        namespace=namespace,
        table_name=table_name,
        rows_written=len(records),
        snapshot_id=snapshot_id,
        duration_seconds=duration,
    )


def overwrite_to_iceberg(
    records: list[dict[str, Any]],
    catalog: Catalog,
    namespace: str,
    table_name: str,
) -> WriteResult:
    """Replace all data in an Iceberg table with new records.

    Uses PyIceberg's ``Table.overwrite()`` to atomically replace the entire
    table contents.  Much faster than upsert for full catalog snapshots
    (markets, events) because it skips reading existing data for merge.

    Args:
        records: Normalized Silver dicts ready for writing.
        catalog: PyIceberg catalog instance.
        namespace: Iceberg namespace (e.g. ``"silver_polymarket"``).
        table_name: Iceberg table name (e.g. ``"markets"``).

    Returns:
        A :class:`WriteResult` with write metadata.

    Raises:
        IcebergWriteError: On empty input, schema mismatch, or write failure.
        KeyError: If ``(namespace, table_name)`` is not in ``SILVER_TABLES``.
    """
    if not records:
        msg = "Cannot overwrite with empty record batch"
        raise IcebergWriteError(msg)

    schema, _sort_order = SILVER_TABLES[(namespace, table_name)]

    logger.info(
        "iceberg_overwrite_start",
        namespace=namespace,
        table=table_name,
        rows=len(records),
    )

    t0 = time.monotonic()

    arrow_table = _to_arrow_table(records, schema)
    table = _resolve_table(catalog, namespace, table_name)

    try:
        table.overwrite(arrow_table)
    except Exception as exc:
        msg = f"Iceberg overwrite failed for {namespace}.{table_name}: {exc}"
        raise IcebergWriteError(msg) from exc

    snapshot = table.current_snapshot()
    snapshot_id = snapshot.snapshot_id if snapshot else -1

    duration = time.monotonic() - t0

    logger.info(
        "iceberg_overwrite_done",
        namespace=namespace,
        table=table_name,
        rows=len(records),
        snapshot_id=snapshot_id,
        duration_s=round(duration, 2),
    )

    return WriteResult(
        namespace=namespace,
        table_name=table_name,
        rows_written=len(records),
        snapshot_id=snapshot_id,
        duration_seconds=duration,
    )


def merge_to_iceberg(
    records: list[dict[str, Any]],
    catalog: Catalog,
    namespace: str,
    table_name: str,
    join_cols: list[str],
) -> WriteResult:
    """Upsert normalized records into an Iceberg table.

    Uses PyIceberg's ``Table.upsert()`` to merge records: rows matching
    on *join_cols* are updated, new rows are inserted.  This provides
    cross-write deduplication — the same logical record written by
    different Bronze runs will be merged rather than duplicated.

    Args:
        records: Normalized Silver dicts ready for writing.
        catalog: PyIceberg catalog instance.
        namespace: Iceberg namespace (e.g. ``"silver_polymarket"``).
        table_name: Iceberg table name (e.g. ``"trades"``).
        join_cols: Column names to match on for upsert (entity merge keys).

    Returns:
        A :class:`WriteResult` with write and merge metadata.

    Raises:
        IcebergWriteError: On empty input, schema mismatch, or write failure.
        KeyError: If ``(namespace, table_name)`` is not in ``SILVER_TABLES``.
    """
    if not records:
        msg = "Cannot merge empty record batch"
        raise IcebergWriteError(msg)

    schema, _sort_order = SILVER_TABLES[(namespace, table_name)]

    logger.info(
        "iceberg_merge_start",
        namespace=namespace,
        table=table_name,
        rows=len(records),
        join_cols=join_cols,
    )

    t0 = time.monotonic()

    arrow_table = _to_arrow_table(records, schema)
    table = _resolve_table(catalog, namespace, table_name)

    try:
        upsert_result = table.upsert(arrow_table, join_cols=join_cols)
    except Exception as exc:
        msg = f"Iceberg merge failed for {namespace}.{table_name}: {exc}"
        raise IcebergWriteError(msg) from exc

    snapshot = table.current_snapshot()
    snapshot_id = snapshot.snapshot_id if snapshot else -1

    duration = time.monotonic() - t0

    logger.info(
        "iceberg_merge_done",
        namespace=namespace,
        table=table_name,
        rows=len(records),
        rows_inserted=upsert_result.rows_inserted,
        rows_updated=upsert_result.rows_updated,
        snapshot_id=snapshot_id,
        duration_s=round(duration, 2),
    )

    return WriteResult(
        namespace=namespace,
        table_name=table_name,
        rows_written=len(records),
        snapshot_id=snapshot_id,
        duration_seconds=duration,
        rows_inserted=upsert_result.rows_inserted,
        rows_updated=upsert_result.rows_updated,
    )
