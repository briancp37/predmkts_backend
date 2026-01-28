"""Polymarket data ingestion submodule."""

from prediction_data.bronze.polymarket.client import (
    DATA_API_BASE_URL,
    GAMMA_API_BASE_URL,
    PaginationState,
    PolymarketClient,
)
from prediction_data.bronze.polymarket.ingest import (
    ingest_events,
    ingest_markets,
    ingest_trades,
    run_ingest_events,
    run_ingest_markets,
    run_ingest_trades,
)

__all__ = [
    "DATA_API_BASE_URL",
    "GAMMA_API_BASE_URL",
    "PaginationState",
    "PolymarketClient",
    "ingest_events",
    "ingest_markets",
    "ingest_trades",
    "run_ingest_events",
    "run_ingest_markets",
    "run_ingest_trades",
]
