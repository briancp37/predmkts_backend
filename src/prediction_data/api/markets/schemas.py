"""Pydantic schemas for market data."""

from typing import Literal

from pydantic import BaseModel, Field


class MarketOutcome(BaseModel):
    """Outcome details for a market."""

    id: str
    tokenId: str
    outcomeName: str
    currentPrice: float
    volume: float


class MarketBase(BaseModel):
    """Base market information."""

    id: str
    polymarketId: str
    conditionId: str | None = None
    slug: str | None = None
    question: str
    description: str | None = None
    category: str | None = None
    endDate: str | None = None
    resolved: bool
    totalVolume: float
    liquidity: float
    createdAt: str
    imageUrl: str | None = None


class MarketResponse(MarketBase):
    """Market response with outcomes."""

    outcomes: list[MarketOutcome] = Field(default_factory=list)


class MarketAdvancedResponse(MarketResponse):
    """Market response with CLOB bid/ask data."""

    bid: float | None = None
    ask: float | None = None
    spread: float | None = None
    spreadPercent: float | None = None
    spreadCents: float | None = None
    volume24h: float = 0.0
    priceChange24h: float = 0.0


class MarketListResponse(BaseModel):
    """Paginated market list response."""

    items: list[MarketResponse]
    total: int
    page: int
    limit: int


class MarketAdvancedListResponse(BaseModel):
    """Paginated advanced market list response."""

    items: list[MarketAdvancedResponse]
    total: int
    page: int
    limit: int


class TradeResponse(BaseModel):
    """Trade record for a market."""

    id: str
    traderAddress: str
    marketId: str
    outcomeId: str
    outcomeName: str
    side: Literal["BUY", "SELL"]
    price: float
    amount: float
    usdValue: float
    txHash: str | None = None
    timestamp: str


class TradeListResponse(BaseModel):
    """Paginated trade list response."""

    items: list[TradeResponse]
    total: int
    page: int
    limit: int


class PriceHistoryPoint(BaseModel):
    """Single point in price history."""

    timestamp: str
    price: float
    volume: float


class MarketFilters(BaseModel):
    """Query parameters for filtering markets."""

    category: str | None = None
    search: str | None = None
    resolved: bool | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class PriceHistoryResponse(BaseModel):
    """Response for price history endpoint."""

    items: list[PriceHistoryPoint]
    marketId: str
    outcomeId: str | None = None
    interval: str
    startDate: str | None = None
    endDate: str | None = None


class TagResponse(BaseModel):
    """Tag (category) information for filtering markets."""

    id: str
    name: str
    slug: str
    marketCount: int
