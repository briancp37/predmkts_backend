"""Pydantic schemas for global trades endpoints.

Note: SmartTradeResponse and WhaleTradeResponse are defined in traders/schemas.py
and re-exported here for convenience.
"""

from prediction_data.api.traders.schemas import (
    SmartTradeFilters,
    SmartTradeResponse,
    TradeResponse,
    WhaleTradeFilters,
    WhaleTradeResponse,
)

__all__ = [
    "SmartTradeFilters",
    "SmartTradeResponse",
    "TradeResponse",
    "WhaleTradeFilters",
    "WhaleTradeResponse",
]
