"""wallet_position_ledger: per-fill audit trail with before/after state.

For each fill processed through the accounting engine, records a ledger row
with the position state before and after the fill, along with the realized
PnL produced by that fill.

Downstream consumers:
- wallet_pnl.py reads (wallet, qty_delta, price, fees_usd, realized_pnl_this_fill_usd)
- on_demand.py reads (ts, platform, market_id, outcome_id, side, qty_delta, price,
  fees_usd, avg_cost_after, qty_after)
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any

import pyarrow as pa
import structlog

from prediction_data.gold.accounting import FillResult, PositionState
from prediction_data.gold.fill_splitter import Fill

logger = structlog.stdlib.get_logger(__name__)

LEDGER_SCHEMA = pa.schema(
    [
        pa.field("ts", pa.timestamp("us", tz="UTC")),
        pa.field("wallet", pa.string()),
        pa.field("platform", pa.string()),
        pa.field("market_id", pa.string()),
        pa.field("outcome_id", pa.string()),
        pa.field("side", pa.string()),
        pa.field("qty_delta", pa.float64()),
        pa.field("price", pa.float64()),
        pa.field("fees_usd", pa.float64()),
        pa.field("qty_before", pa.float64()),
        pa.field("qty_after", pa.float64()),
        pa.field("avg_cost_before", pa.float64()),
        pa.field("avg_cost_after", pa.float64()),
        pa.field("realized_pnl_this_fill_usd", pa.float64()),
    ]
)

LEDGER_COLUMNS = [f.name for f in LEDGER_SCHEMA]


@dataclasses.dataclass(slots=True, frozen=True)
class LedgerRow:
    """A single ledger entry recording before/after state for one fill."""

    ts: datetime
    wallet: str
    platform: str
    market_id: str
    outcome_id: str
    side: str
    qty_delta: float
    price: float
    fees_usd: float
    qty_before: float
    qty_after: float
    avg_cost_before: float
    avg_cost_after: float
    realized_pnl_this_fill_usd: float


def record_fill(
    position: PositionState,
    fill: Fill,
) -> tuple[FillResult, LedgerRow]:
    """Apply a fill to a position and record the ledger row.

    Captures the position state before the fill, applies the fill through
    the accounting engine, then captures the state after.

    Args:
        position: Mutable position state to apply the fill to.
        fill: The fill event to apply.

    Returns:
        A tuple of (FillResult, LedgerRow).
    """
    qty_before = position.qty
    avg_cost_before = position.avg_cost

    result = position.apply_fill(
        side=fill.side,
        qty_delta=fill.qty_delta,
        price=fill.price,
        fees=fill.fees_usd,
        ts=fill.ts,
    )

    return result, LedgerRow(
        ts=fill.ts,
        wallet=fill.wallet,
        platform=fill.platform,
        market_id=fill.market_id,
        outcome_id=fill.outcome_id,
        side=fill.side,
        qty_delta=fill.qty_delta,
        price=fill.price,
        fees_usd=fill.fees_usd,
        qty_before=qty_before,
        qty_after=position.qty,
        avg_cost_before=avg_cost_before,
        avg_cost_after=position.avg_cost,
        realized_pnl_this_fill_usd=result.realized_pnl,
    )


class LedgerWriter:
    """Accumulates ledger rows and writes them to S3 Gold Parquet and ClickHouse.

    Usage::

        writer = LedgerWriter()
        for fill in fills:
            key = (fill.wallet, fill.platform, fill.market_id, fill.outcome_id)
            position = positions.setdefault(key, PositionState(...))
            writer.record(position, fill)
        writer.flush(gold_bucket="my-bucket", day="2024-06-15")
    """

    def __init__(self) -> None:
        self._rows: list[LedgerRow] = []

    @property
    def rows(self) -> list[LedgerRow]:
        """Return accumulated ledger rows (read-only view)."""
        return list(self._rows)

    @property
    def count(self) -> int:
        """Number of accumulated ledger rows."""
        return len(self._rows)

    def record(
        self,
        position: PositionState,
        fill: Fill,
    ) -> tuple[FillResult, LedgerRow]:
        """Apply a fill, record the ledger row, and return both.

        Args:
            position: Mutable position state to apply the fill to.
            fill: The fill event to apply.

        Returns:
            A tuple of (FillResult, LedgerRow).
        """
        result, row = record_fill(position, fill)
        self._rows.append(row)
        return result, row

    def to_arrow(self) -> pa.Table:
        """Convert accumulated rows to a PyArrow Table.

        Returns:
            PyArrow table conforming to :data:`LEDGER_SCHEMA`.
        """
        if not self._rows:
            return pa.table(
                {col: [] for col in LEDGER_COLUMNS}, schema=LEDGER_SCHEMA
            )

        data: dict[str, list[Any]] = {col: [] for col in LEDGER_COLUMNS}
        for row in self._rows:
            data["ts"].append(row.ts)
            data["wallet"].append(row.wallet)
            data["platform"].append(row.platform)
            data["market_id"].append(row.market_id)
            data["outcome_id"].append(row.outcome_id)
            data["side"].append(row.side)
            data["qty_delta"].append(row.qty_delta)
            data["price"].append(row.price)
            data["fees_usd"].append(row.fees_usd)
            data["qty_before"].append(row.qty_before)
            data["qty_after"].append(row.qty_after)
            data["avg_cost_before"].append(row.avg_cost_before)
            data["avg_cost_after"].append(row.avg_cost_after)
            data["realized_pnl_this_fill_usd"].append(
                row.realized_pnl_this_fill_usd
            )

        return pa.table(data, schema=LEDGER_SCHEMA)

    def flush(
        self,
        *,
        gold_bucket: str | None = None,
        day: str,
        s3_client: Any | None = None,
        clickhouse_client: Any | None = None,
        dry_run: bool = False,
    ) -> int:
        """Write accumulated ledger rows to S3 Gold Parquet and ClickHouse.

        Args:
            gold_bucket: S3 bucket for Gold output. Skips S3 write when *None*.
            day: Partition day in ``YYYY-MM-DD`` format.
            s3_client: Optional boto3 S3 client.
            clickhouse_client: Optional ClickHouse client.
            dry_run: If *True*, log what would be written but don't persist.

        Returns:
            Number of rows written.
        """
        table = self.to_arrow()
        num_rows: int = table.num_rows

        logger.info("ledger_flush", day=day, rows=num_rows)

        if num_rows == 0:
            return 0

        if dry_run:
            logger.info("dry_run_ledger_flush", day=day, rows=num_rows)
            return num_rows

        if gold_bucket:
            from prediction_data.gold.s3_writer import write_gold_parquet

            write_gold_parquet(
                table,
                gold_bucket,
                "wallet_position_ledger",
                day,
                s3_client=s3_client,
            )

        if clickhouse_client is None:
            from prediction_data.gold.clickhouse import get_client

            clickhouse_client = get_client()

        clickhouse_client.insert(
            "wallet_position_ledger",
            data=table.to_pylist(),
            column_names=LEDGER_COLUMNS,
        )

        logger.info("ledger_flushed", day=day, rows=num_rows)
        return num_rows

    def clear(self) -> None:
        """Discard all accumulated rows."""
        self._rows.clear()


def build_ledger_for_day(
    fills: list[Fill],
    positions: dict[tuple[str, str, str, str], PositionState],
) -> tuple[LedgerWriter, dict[tuple[str, str, str, str], PositionState]]:
    """Process a list of fills through the accounting engine and build a ledger.

    Creates or reuses position states in *positions* (keyed by
    ``(wallet, platform, market_id, outcome_id)``), applies each fill,
    and records ledger rows.

    Args:
        fills: Fills sorted by timestamp. Must be pre-sorted.
        positions: Mutable dict of existing position states.
            New positions are created as needed.

    Returns:
        A tuple of (LedgerWriter with all rows, updated positions dict).
    """
    writer = LedgerWriter()

    for fill in fills:
        key = (fill.wallet, fill.platform, fill.market_id, fill.outcome_id)
        if key not in positions:
            positions[key] = PositionState(
                wallet=fill.wallet,
                platform=fill.platform,
                market_id=fill.market_id,
                outcome_id=fill.outcome_id,
            )
        writer.record(positions[key], fill)

    return writer, positions
