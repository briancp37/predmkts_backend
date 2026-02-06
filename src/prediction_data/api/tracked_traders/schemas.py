"""Pydantic schemas for tracked traders API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from prediction_data.api.traders.schemas import TradeResponse
from prediction_data.api.validators import (
    DateString,
    EthereumAddress,
    validate_date_range,
)


class TrackedTraderBase(BaseModel):
    """Base tracked trader schema."""

    traderAddress: EthereumAddress
    customName: str | None = None


class TrackedTraderCreate(BaseModel):
    """Request body for adding a tracked trader."""

    traderAddress: EthereumAddress
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
    startDate: DateString | None = None
    endDate: DateString | None = None

    @model_validator(mode="after")
    def validate_date_range_order(self) -> "ActivityFilters":
        """Ensure startDate <= endDate when both are provided."""
        validate_date_range(self.startDate, self.endDate)
        return self
