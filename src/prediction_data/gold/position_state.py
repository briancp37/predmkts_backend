"""wallet_position_state: current open positions in ClickHouse.

Maintains a ReplacingMergeTree table of current position states, keyed by
(wallet, platform, market_id, outcome_id). After processing fills through
the accounting engine, open positions are upserted into ClickHouse and
closed positions (qty=0) are written with a final timestamp so
ReplacingMergeTree can collapse them.

Downstream consumers:
- wallet_mtm.py queries ``wallet_position_state WHERE qty != 0``
- wallet_position_snapshot.py queries ``wallet_position_state WHERE qty != 0``
"""

from __future__ import annotations

from typing import Any

import pyarrow as pa
import structlog

from prediction_data.gold.accounting import PositionState

logger = structlog.stdlib.get_logger(__name__)

POSITION_STATE_SCHEMA = pa.schema(
    [
        pa.field("wallet", pa.string()),
        pa.field("platform", pa.string()),
        pa.field("market_id", pa.string()),
        pa.field("outcome_id", pa.string()),
        pa.field("qty", pa.float64()),
        pa.field("avg_cost", pa.float64()),
        pa.field("cost_basis_usd", pa.float64()),
        pa.field("last_fill_ts", pa.timestamp("us", tz="UTC")),
        pa.field("first_open_ts", pa.timestamp("us", tz="UTC")),
    ]
)

POSITION_STATE_COLUMNS = [f.name for f in POSITION_STATE_SCHEMA]


def positions_to_arrow(
    positions: dict[tuple[str, str, str, str], PositionState],
) -> pa.Table:
    """Convert a positions dict to a PyArrow Table.

    Includes all positions (open and closed). Closed positions (qty=0)
    are included so that ReplacingMergeTree can overwrite stale rows
    in ClickHouse. Downstream queries filter with ``qty != 0``.

    Args:
        positions: Dict keyed by (wallet, platform, market_id, outcome_id).

    Returns:
        PyArrow table conforming to :data:`POSITION_STATE_SCHEMA`.
    """
    if not positions:
        return pa.table(
            {col: [] for col in POSITION_STATE_COLUMNS},
            schema=POSITION_STATE_SCHEMA,
        )

    data: dict[str, list[Any]] = {col: [] for col in POSITION_STATE_COLUMNS}
    for pos in positions.values():
        if pos.last_fill_ts is None:
            continue
        data["wallet"].append(pos.wallet)
        data["platform"].append(pos.platform)
        data["market_id"].append(pos.market_id)
        data["outcome_id"].append(pos.outcome_id)
        data["qty"].append(pos.qty)
        data["avg_cost"].append(pos.avg_cost)
        data["cost_basis_usd"].append(pos.cost_basis_usd)
        data["last_fill_ts"].append(pos.last_fill_ts)
        data["first_open_ts"].append(pos.first_open_ts)

    return pa.table(data, schema=POSITION_STATE_SCHEMA)


def write_position_states(
    positions: dict[tuple[str, str, str, str], PositionState],
    *,
    clickhouse_client: Any | None = None,
    dry_run: bool = False,
) -> int:
    """Write current position states to ClickHouse.

    All positions that have been touched (have a ``last_fill_ts``) are
    written. Closed positions (qty=0) are included so
    ReplacingMergeTree collapses previous open rows.  Downstream
    queries use ``WHERE qty != 0`` to exclude them.

    Args:
        positions: Dict keyed by (wallet, platform, market_id, outcome_id).
        clickhouse_client: Optional ClickHouse client.
        dry_run: If *True*, log what would be written but don't persist.

    Returns:
        Number of rows written.
    """
    table = positions_to_arrow(positions)
    num_rows: int = table.num_rows

    logger.info("position_state_write", rows=num_rows)

    if num_rows == 0:
        return 0

    if dry_run:
        logger.info("dry_run_position_state_write", rows=num_rows)
        return num_rows

    if clickhouse_client is None:
        from prediction_data.gold.clickhouse import get_client

        clickhouse_client = get_client()

    clickhouse_client.insert(
        "wallet_position_state",
        data=table.to_pylist(),
        column_names=POSITION_STATE_COLUMNS,
    )

    logger.info("position_state_written", rows=num_rows)
    return num_rows


def read_position_states(
    *,
    clickhouse_client: Any | None = None,
) -> dict[tuple[str, str, str, str], PositionState]:
    """Load current open positions from ClickHouse.

    Reads from ``wallet_position_state FINAL`` and returns a dict of
    :class:`PositionState` objects keyed by
    ``(wallet, platform, market_id, outcome_id)``.

    Only positions with ``qty != 0`` are returned.

    Args:
        clickhouse_client: Optional ClickHouse client.

    Returns:
        Dict of open positions.
    """
    if clickhouse_client is None:
        from prediction_data.gold.clickhouse import get_client

        clickhouse_client = get_client()

    result = clickhouse_client.query(
        "SELECT wallet, platform, market_id, outcome_id, "
        "qty, avg_cost, cost_basis_usd, last_fill_ts, first_open_ts "
        "FROM wallet_position_state FINAL "
        "WHERE qty != 0"
    )

    positions: dict[tuple[str, str, str, str], PositionState] = {}
    for row in result.result_rows:
        key = (row[0], row[1], row[2], row[3])
        positions[key] = PositionState(
            wallet=row[0],
            platform=row[1],
            market_id=row[2],
            outcome_id=row[3],
            qty=float(row[4]),
            avg_cost=float(row[5]),
            cost_basis_usd=float(row[6]),
            last_fill_ts=row[7],
            first_open_ts=row[8],
        )

    logger.info("position_state_read", positions=len(positions))
    return positions
