"""Pydantic schemas for watchlist API."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class WatchlistItem(BaseModel):
    """Base watchlist item schema."""

    id: uuid.UUID
    marketId: str
    createdAt: datetime

    model_config = {"from_attributes": True}


class WatchlistItemWithMarket(WatchlistItem):
    """Watchlist item with market details."""

    marketQuestion: str
    marketCategory: str | None = None
    currentPrice: float
    priceChange24h: float
    resolved: bool


class WatchlistAddRequest(BaseModel):
    """Request body for adding to watchlist."""

    marketId: str


class WatchlistResponse(BaseModel):
    """Response for watchlist listing."""

    items: list[WatchlistItemWithMarket]
    count: int
