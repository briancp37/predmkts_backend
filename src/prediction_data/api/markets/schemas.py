"""Pydantic schemas for market data."""

from typing import Literal

from pydantic import BaseModel, Field


class MarketOutcome(BaseModel):
    """Outcome details for a market."""

    id: str = Field(
        ...,
        description="Unique outcome identifier",
        json_schema_extra={"example": "outcome-yes-123"},
    )
    tokenId: str = Field(
        ...,
        description="CLOB token ID for this outcome",
        json_schema_extra={
            "example": "71321045679252212594626385532706912750332728571942532289631379312455583286595"
        },
    )
    outcomeName: str = Field(
        ...,
        description="Human-readable outcome name",
        json_schema_extra={"example": "Yes"},
    )
    currentPrice: float = Field(
        ...,
        description="Current price (0.0 to 1.0)",
        json_schema_extra={"example": 0.65},
    )
    volume: float = Field(
        ...,
        description="Total volume traded on this outcome in USD",
        json_schema_extra={"example": 125000.50},
    )


class MarketBase(BaseModel):
    """Base market information."""

    id: str = Field(
        ...,
        description="Internal market identifier",
        json_schema_extra={"example": "market-12345"},
    )
    polymarketId: str = Field(
        ...,
        description="Polymarket market ID",
        json_schema_extra={"example": "0x1234567890abcdef"},
    )
    conditionId: str | None = Field(
        default=None,
        description="Polymarket condition ID (64 hex chars with 0x prefix)",
        json_schema_extra={
            "example": "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        },
    )
    slug: str | None = Field(
        default=None,
        description="URL-friendly market slug",
        json_schema_extra={"example": "will-bitcoin-reach-100k-by-2025"},
    )
    eventSlug: str | None = Field(
        default=None,
        description="URL-friendly event slug for navigation to event detail page",
        json_schema_extra={"example": "us-presidential-election-2024"},
    )
    question: str = Field(
        ...,
        description="Market question",
        json_schema_extra={"example": "Will Bitcoin reach $100,000 by end of 2025?"},
    )
    description: str | None = Field(
        default=None,
        description="Detailed market description and resolution criteria",
    )
    category: str | None = Field(
        default=None,
        description="Market category",
        json_schema_extra={"example": "Crypto"},
    )
    endDate: str | None = Field(
        default=None,
        description="Market resolution deadline (ISO 8601)",
        json_schema_extra={"example": "2025-12-31T23:59:59Z"},
    )
    resolved: bool = Field(
        ...,
        description="Whether the market has been resolved",
        json_schema_extra={"example": False},
    )
    totalVolume: float = Field(
        ...,
        description="Total trading volume in USD",
        json_schema_extra={"example": 1250000.00},
    )
    liquidity: float = Field(
        ...,
        description="Current liquidity in USD",
        json_schema_extra={"example": 50000.00},
    )
    createdAt: str = Field(
        ...,
        description="Market creation timestamp (ISO 8601)",
        json_schema_extra={"example": "2024-01-15T10:30:00Z"},
    )
    imageUrl: str | None = Field(
        default=None,
        description="Market cover image URL",
    )


class MarketResponse(MarketBase):
    """Market response with outcomes."""

    outcomes: list[MarketOutcome] = Field(
        default_factory=list,
        description="List of possible outcomes for this market",
    )


class MarketAdvancedResponse(MarketResponse):
    """Market response with CLOB bid/ask data from Polymarket."""

    bid: float | None = Field(
        default=None,
        description="Current best bid price (0.0 to 1.0)",
        json_schema_extra={"example": 0.64},
    )
    ask: float | None = Field(
        default=None,
        description="Current best ask price (0.0 to 1.0)",
        json_schema_extra={"example": 0.66},
    )
    spread: float | None = Field(
        default=None,
        description="Bid-ask spread (ask - bid)",
        json_schema_extra={"example": 0.02},
    )
    spreadPercent: float | None = Field(
        default=None,
        description="Spread as percentage of midpoint price",
        json_schema_extra={"example": 3.08},
    )
    spreadCents: float | None = Field(
        default=None,
        description="Spread in cents (spread * 100)",
        json_schema_extra={"example": 2.0},
    )
    volume24h: float = Field(
        default=0.0,
        description="Trading volume in last 24 hours (USD)",
        json_schema_extra={"example": 15000.00},
    )
    priceChange24h: float = Field(
        default=0.0,
        description="Price change in last 24 hours (absolute)",
        json_schema_extra={"example": 0.05},
    )


class MarketListResponse(BaseModel):
    """Paginated market list response."""

    items: list[MarketResponse] = Field(..., description="List of markets")
    total: int = Field(
        ..., description="Total number of matching markets", json_schema_extra={"example": 150}
    )
    page: int = Field(..., description="Current page number", json_schema_extra={"example": 1})
    limit: int = Field(..., description="Results per page", json_schema_extra={"example": 50})


class MarketAdvancedListResponse(BaseModel):
    """Paginated advanced market list response."""

    items: list[MarketAdvancedResponse] = Field(
        ..., description="List of markets with CLOB data"
    )
    total: int = Field(..., description="Total number of matching markets")
    page: int = Field(..., description="Current page number")
    limit: int = Field(..., description="Results per page")


class TradeResponse(BaseModel):
    """Trade record for a market."""

    id: str = Field(
        ...,
        description="Unique trade identifier",
        json_schema_extra={"example": "trade-abc123"},
    )
    traderAddress: str = Field(
        ...,
        description="Ethereum wallet address of the trader (lowercase)",
        json_schema_extra={"example": "0x1234567890abcdef1234567890abcdef12345678"},
    )
    marketId: str = Field(
        ...,
        description="Market this trade belongs to",
        json_schema_extra={"example": "market-12345"},
    )
    outcomeId: str = Field(
        ...,
        description="Outcome being traded",
        json_schema_extra={"example": "outcome-yes-123"},
    )
    outcomeName: str = Field(
        ...,
        description="Name of the outcome",
        json_schema_extra={"example": "Yes"},
    )
    side: Literal["BUY", "SELL"] = Field(
        ...,
        description="Trade side (BUY or SELL)",
        json_schema_extra={"example": "BUY"},
    )
    price: float = Field(
        ...,
        description="Execution price (0.0 to 1.0)",
        json_schema_extra={"example": 0.65},
    )
    amount: float = Field(
        ...,
        description="Number of shares traded",
        json_schema_extra={"example": 1000.0},
    )
    usdValue: float = Field(
        ...,
        description="USD value of the trade (amount * price)",
        json_schema_extra={"example": 650.00},
    )
    txHash: str | None = Field(
        default=None,
        description="Blockchain transaction hash",
        json_schema_extra={"example": "0xabc123..."},
    )
    timestamp: str = Field(
        ...,
        description="Trade execution timestamp (ISO 8601)",
        json_schema_extra={"example": "2024-01-15T10:30:00Z"},
    )


class TradeListResponse(BaseModel):
    """Paginated trade list response."""

    items: list[TradeResponse] = Field(..., description="List of trades")
    total: int = Field(..., description="Total number of matching trades")
    page: int = Field(..., description="Current page number")
    limit: int = Field(..., description="Results per page")


class PriceHistoryPoint(BaseModel):
    """Single point in price history."""

    timestamp: str = Field(
        ...,
        description="Timestamp for this data point (ISO 8601)",
        json_schema_extra={"example": "2024-01-15T00:00:00Z"},
    )
    price: float = Field(
        ...,
        description="Price at this timestamp (0.0 to 1.0)",
        json_schema_extra={"example": 0.65},
    )
    volume: float = Field(
        ...,
        description="Volume during this interval (USD)",
        json_schema_extra={"example": 5000.00},
    )


class MarketFilters(BaseModel):
    """Query parameters for filtering markets."""

    category: str | None = Field(
        default=None,
        description="Filter by category slug",
        json_schema_extra={"example": "politics"},
    )
    search: str | None = Field(
        default=None,
        description="Search in market question/description",
        json_schema_extra={"example": "bitcoin"},
    )
    resolved: bool | None = Field(
        default=None,
        description="Filter by resolution status (true=resolved, false=active)",
    )
    limit: int = Field(
        default=50, ge=1, le=500, description="Maximum results to return (1-500)"
    )
    offset: int = Field(default=0, ge=0, description="Number of results to skip")


class PriceHistoryResponse(BaseModel):
    """Response for price history endpoint."""

    items: list[PriceHistoryPoint] = Field(..., description="Price history data points")
    marketId: str = Field(..., description="Market ID for this history")
    outcomeId: str | None = Field(default=None, description="Specific outcome ID if filtered")
    interval: str = Field(
        ...,
        description="Time interval (daily, hourly)",
        json_schema_extra={"example": "daily"},
    )
    startDate: str | None = Field(default=None, description="Start of date range")
    endDate: str | None = Field(default=None, description="End of date range")


class TagResponse(BaseModel):
    """Tag (category) information for filtering markets."""

    id: str = Field(
        ...,
        description="Unique tag identifier",
        json_schema_extra={"example": "politics"},
    )
    name: str = Field(
        ...,
        description="Display name",
        json_schema_extra={"example": "Politics"},
    )
    slug: str = Field(
        ...,
        description="URL-friendly slug",
        json_schema_extra={"example": "politics"},
    )
    marketCount: int = Field(
        ...,
        description="Number of markets with this tag",
        json_schema_extra={"example": 250},
    )
