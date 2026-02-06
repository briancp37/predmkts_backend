"""Pydantic schemas for event data."""

from pydantic import BaseModel, Field

from prediction_data.api.markets.schemas import MarketBase, MarketOutcome


class EventMarketOutcome(MarketOutcome):
    """Outcome with price change data for event detail view."""

    priceChange24h: float = Field(
        default=0.0,
        description="Price change in last 24 hours (absolute, e.g., 0.05 = 5 cents)",
        json_schema_extra={"example": 0.05},
    )


class EventMarketResponse(MarketBase):
    """Market response with outcomes and price changes for event detail view."""

    outcomes: list[EventMarketOutcome] = Field(
        default_factory=list,
        description="List of outcomes with current prices and 24h price changes",
    )
    volume24h: float = Field(
        default=0.0,
        description="Total trading volume across all outcomes in last 24 hours (USD)",
        json_schema_extra={"example": 15000.00},
    )


class EventResponse(BaseModel):
    """Event response with associated markets."""

    id: str = Field(
        ...,
        description="Internal event identifier",
        json_schema_extra={"example": "event-12345"},
    )
    polymarketEventId: str = Field(
        ...,
        description="Polymarket event ID",
        json_schema_extra={"example": "12345"},
    )
    title: str = Field(
        ...,
        description="Event title",
        json_schema_extra={"example": "2024 US Presidential Election"},
    )
    description: str | None = Field(
        default=None,
        description="Detailed event description",
    )
    slug: str = Field(
        ...,
        description="URL-friendly event slug",
        json_schema_extra={"example": "2024-us-presidential-election"},
    )
    status: str = Field(
        ...,
        description="Event status (active, resolved, etc.)",
        json_schema_extra={"example": "active"},
    )
    category: str | None = Field(
        default=None,
        description="Event category",
        json_schema_extra={"example": "Politics"},
    )
    markets: list[EventMarketResponse] = Field(
        default_factory=list,
        description="Markets associated with this event, with outcomes and price data",
    )


class EventListResponse(BaseModel):
    """Paginated event list response."""

    items: list[EventResponse] = Field(..., description="List of events")
    total: int = Field(
        ..., description="Total number of matching events", json_schema_extra={"example": 50}
    )
    page: int = Field(..., description="Current page number", json_schema_extra={"example": 1})
    limit: int = Field(..., description="Results per page", json_schema_extra={"example": 20})
