"""Pydantic schemas for event data."""

from pydantic import BaseModel, Field

from prediction_data.api.markets.schemas import MarketBase


class EventResponse(BaseModel):
    """Event response with associated markets."""

    id: str
    polymarketEventId: str
    title: str
    description: str | None = None
    slug: str
    status: str
    category: str | None = None
    markets: list[MarketBase] = Field(default_factory=list)


class EventListResponse(BaseModel):
    """Paginated event list response."""

    items: list[EventResponse]
    total: int
    page: int
    limit: int
