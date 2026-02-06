"""Pydantic schemas for tracked traders API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from prediction_data.api.traders.schemas import TradeResponse
from prediction_data.api.validators import (
    DateString,
    EthereumAddress,
    validate_date_range,
)


class TrackedTraderBase(BaseModel):
    """Base tracked trader schema."""

    traderAddress: EthereumAddress = Field(
        ...,
        description="Ethereum wallet address to track (0x + 40 hex chars)",
        json_schema_extra={"example": "0x1234567890abcdef1234567890abcdef12345678"},
    )
    customName: str | None = Field(
        default=None,
        description="Custom display name for this trader",
        json_schema_extra={"example": "Whale Watcher"},
    )


class TrackedTraderCreate(BaseModel):
    """Request body for adding a tracked trader."""

    traderAddress: EthereumAddress = Field(
        ...,
        description="Ethereum wallet address to track (0x + 40 hex chars)",
        json_schema_extra={"example": "0x1234567890abcdef1234567890abcdef12345678"},
    )
    customName: str | None = Field(
        default=None,
        description="Custom display name for this trader",
        json_schema_extra={"example": "Smart Money Alpha"},
    )


class TrackedTraderUpdate(BaseModel):
    """Request body for updating a tracked trader."""

    customName: str | None = Field(
        default=None,
        description="New custom display name",
        json_schema_extra={"example": "Updated Name"},
    )


class TrackedTraderResponse(TrackedTraderBase):
    """Tracked trader response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(
        ...,
        description="Unique tracker entry identifier",
        json_schema_extra={"example": "550e8400-e29b-41d4-a716-446655440000"},
    )
    createdAt: datetime = Field(
        ...,
        description="When tracking started",
        json_schema_extra={"example": "2024-01-15T10:30:00Z"},
    )


class TrackedTraderWithStats(TrackedTraderResponse):
    """Tracked trader with stats from ClickHouse."""

    totalPnl: float = Field(
        default=0.0,
        description="Total profit/loss in USD (30-day window)",
        json_schema_extra={"example": 15000.50},
    )
    recentTrades: int = Field(
        default=0,
        description="Number of trades in last 7 days",
        json_schema_extra={"example": 12},
    )
    smartScore: float | None = Field(
        default=None,
        description="Trader's smart score (0-100). Null if <5 trades.",
        json_schema_extra={"example": 78.5},
    )


class TrackedTraderActivity(BaseModel):
    """Activity feed item for a tracked trader."""

    traderId: uuid.UUID = Field(
        ...,
        description="Tracker entry ID",
        json_schema_extra={"example": "550e8400-e29b-41d4-a716-446655440000"},
    )
    traderAddress: str = Field(
        ...,
        description="Trader wallet address",
        json_schema_extra={"example": "0x1234567890abcdef1234567890abcdef12345678"},
    )
    customName: str | None = Field(
        default=None,
        description="Custom name if set",
        json_schema_extra={"example": "Smart Money Alpha"},
    )
    trade: TradeResponse = Field(..., description="Trade details")
    timestamp: datetime = Field(
        ...,
        description="Activity timestamp",
        json_schema_extra={"example": "2024-01-15T10:30:00Z"},
    )


class TrackedTradersListResponse(BaseModel):
    """Response for tracked traders listing."""

    items: list[TrackedTraderWithStats] = Field(
        ..., description="List of tracked traders with stats"
    )
    count: int = Field(
        ...,
        description="Current number of tracked traders",
        json_schema_extra={"example": 3},
    )
    limit: int = Field(
        ...,
        description="Tier limit for tracked traders (free: 5, pro: 50, enterprise: unlimited)",
        json_schema_extra={"example": 5},
    )


class ActivityFilters(BaseModel):
    """Query parameters for activity feed."""

    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum activities to return",
    )
    startDate: DateString | None = Field(
        default=None,
        description="Filter activities on or after this date (YYYY-MM-DD)",
        json_schema_extra={"example": "2024-01-01"},
    )
    endDate: DateString | None = Field(
        default=None,
        description="Filter activities on or before this date (YYYY-MM-DD)",
        json_schema_extra={"example": "2024-01-31"},
    )

    @model_validator(mode="after")
    def validate_date_range_order(self) -> "ActivityFilters":
        """Ensure startDate <= endDate when both are provided."""
        validate_date_range(self.startDate, self.endDate)
        return self
