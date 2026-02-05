"""Pydantic schemas for tracked traders API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from prediction_data.api.traders.schemas import TradeResponse


class TrackedTraderBase(BaseModel):
    """Base tracked trader schema."""

    traderAddress: str
    customName: str | None = None


class TrackedTraderCreate(BaseModel):
    """Request body for adding a tracked trader."""

    traderAddress: str
    customName: str | None = None


class TrackedTraderUpdate(BaseModel):
    """Request body for updating a tracked trader."""

    customName: str | None = None


class TrackedTraderResponse(TrackedTraderBase):
    """Tracked trader response."""

    id: uuid.UUID
    createdAt: datetime

    model_config = {"from_attributes": True}


class TrackedTraderWithStats(TrackedTraderResponse):
    """Tracked trader with stats from ClickHouse."""

    totalPnl: float = 0.0
    recentTrades: int = 0
    smartScore: float | None = None


class TrackedTraderActivity(BaseModel):
    """Activity feed item for a tracked trader."""

    traderId: uuid.UUID
    traderAddress: str
    customName: str | None = None
    trade: TradeResponse
    timestamp: datetime


class TrackedTradersListResponse(BaseModel):
    """Response for tracked traders listing."""

    items: list[TrackedTraderWithStats]
    count: int
    limit: int = Field(description="Tier limit for tracked traders")


class ActivityFilters(BaseModel):
    """Query parameters for activity feed."""

    limit: int = Field(default=50, ge=1, le=200)
    startDate: str | None = None
    endDate: str | None = None
