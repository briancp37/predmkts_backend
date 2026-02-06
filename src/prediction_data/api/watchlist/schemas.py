"""Pydantic schemas for watchlist API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from prediction_data.api.validators import MarketId


class WatchlistItem(BaseModel):
    """Base watchlist item schema."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(
        ...,
        description="Unique watchlist entry identifier",
        json_schema_extra={"example": "550e8400-e29b-41d4-a716-446655440000"},
    )
    marketId: str = Field(
        ...,
        description="Market ID being watched",
        json_schema_extra={
            "example": "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        },
    )
    createdAt: datetime = Field(
        ...,
        description="When the market was added to watchlist",
        json_schema_extra={"example": "2024-01-15T10:30:00Z"},
    )


class WatchlistItemWithMarket(WatchlistItem):
    """Watchlist item enriched with market details."""

    marketQuestion: str = Field(
        ...,
        description="Market question text",
        json_schema_extra={"example": "Will Bitcoin reach $100k by 2025?"},
    )
    marketCategory: str | None = Field(
        default=None,
        description="Market category",
        json_schema_extra={"example": "Crypto"},
    )
    currentPrice: float = Field(
        ...,
        description="Current Yes price (0.0 to 1.0)",
        json_schema_extra={"example": 0.65},
    )
    priceChange24h: float = Field(
        ...,
        description="Price change in last 24 hours (absolute)",
        json_schema_extra={"example": 0.05},
    )
    resolved: bool = Field(
        ...,
        description="Whether the market has been resolved",
        json_schema_extra={"example": False},
    )


class WatchlistAddRequest(BaseModel):
    """Request body for adding a market to the watchlist."""

    marketId: MarketId = Field(
        ...,
        description="Market condition ID to add (0x + 64 hex chars)",
        json_schema_extra={
            "example": "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        },
    )


class WatchlistResponse(BaseModel):
    """Response for watchlist listing."""

    items: list[WatchlistItemWithMarket] = Field(
        ..., description="Watchlist items with market details"
    )
    count: int = Field(
        ...,
        description="Total number of items in watchlist",
        json_schema_extra={"example": 5},
    )
