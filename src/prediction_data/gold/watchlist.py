"""Gold watchlist: selective wallet tracking for MTM and snapshot computation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from prediction_data.gold.clickhouse import get_client

logger = structlog.stdlib.get_logger(__name__)

TABLE = "gold_watchlist"


def add_wallet(
    wallet_address: str,
    *,
    notes: str = "",
    clickhouse_client: Any | None = None,
) -> None:
    """Add a wallet address to the watchlist.

    Uses ReplacingMergeTree semantics — re-inserting an existing address
    updates its ``added_at`` timestamp and reactivates it.
    """
    ch = clickhouse_client or get_client()
    now = datetime.now(timezone.utc)
    ch.insert(
        TABLE,
        data=[[wallet_address, now, notes, True]],
        column_names=["wallet_address", "added_at", "notes", "active"],
    )
    logger.info("watchlist_add", wallet=wallet_address)


def remove_wallet(
    wallet_address: str,
    *,
    clickhouse_client: Any | None = None,
) -> None:
    """Deactivate a wallet on the watchlist.

    Inserts a new row with ``active=false`` so the ReplacingMergeTree
    keeps only the latest version.
    """
    ch = clickhouse_client or get_client()
    now = datetime.now(timezone.utc)
    ch.insert(
        TABLE,
        data=[[wallet_address, now, "", False]],
        column_names=["wallet_address", "added_at", "notes", "active"],
    )
    logger.info("watchlist_remove", wallet=wallet_address)


def list_wallets(
    *,
    active_only: bool = True,
    clickhouse_client: Any | None = None,
) -> list[dict[str, Any]]:
    """Return watchlist entries.

    Args:
        active_only: If *True* (default), return only active wallets.
        clickhouse_client: Optional ClickHouse client.

    Returns:
        List of dicts with keys: wallet_address, added_at, notes, active.
    """
    ch = clickhouse_client or get_client()
    where = "WHERE active = true" if active_only else ""
    # FINAL forces ReplacingMergeTree deduplication at read time.
    query = f"SELECT wallet_address, added_at, notes, active FROM {TABLE} FINAL {where} ORDER BY wallet_address"
    result = ch.query(query)
    rows: list[dict[str, Any]] = []
    for row in result.result_rows:
        rows.append({
            "wallet_address": row[0],
            "added_at": row[1],
            "notes": row[2],
            "active": row[3],
        })
    logger.info("watchlist_list", count=len(rows), active_only=active_only)
    return rows
