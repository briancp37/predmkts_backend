"""Pydantic schemas for trader data."""

from typing import Literal

from pydantic import BaseModel, Field


class TraderPosition(BaseModel):
    """Current position held by a trader."""

    marketId: str
    marketQuestion: str
    outcomeId: str
    outcomeName: str
    quantity: float
    avgCost: float
    currentPrice: float
    unrealizedPnl: float
    realizedPnl: float


class TraderBase(BaseModel):
    """Base trader information."""

    address: str
    username: str | None = None
    firstSeen: str
    totalPnl: float
    realizedPnl: float
    totalTrades: int
    winCount: int
    lossCount: int


class TraderResponse(TraderBase):
    """Trader response with additional metadata."""

    id: str
    smartScore: float | None = None
    createdAt: str
    updatedAt: str


class TraderDetailResponse(TraderResponse):
    """Detailed trader response with positions and stats."""

    positions: list[TraderPosition] = Field(default_factory=list)
    tradeCount: int
    winRate: float


class TraderListResponse(BaseModel):
    """Paginated list of traders."""

    items: list[TraderResponse]
    total: int
    page: int
    limit: int


class SmartScoreComponents(BaseModel):
    """Components that make up a smart score."""

    accuracy: float
    consistency: float
    sizing: float
    timing: float


class SmartScoreResponse(BaseModel):
    """Smart score response for a trader."""

    address: str
    smartScore: float
    components: SmartScoreComponents


class SmartScoreListResponse(BaseModel):
    """List of smart scores."""

    items: list[SmartScoreResponse]
    timeWindow: str
    generatedAt: str


class SmartScoreFilters(BaseModel):
    """Query parameters for smart scores endpoint."""

    minScore: float = Field(default=0, ge=0, le=100)
    limit: int = Field(default=100, ge=1, le=500)
    timeWindow: Literal["7d", "30d", "90d", "all"] = "30d"


class TraderFilters(BaseModel):
    """Query parameters for filtering traders."""

    search: str | None = None
    sortBy: Literal["smartScore", "totalPnl", "totalTrades", "winRate"] = "totalPnl"
    sortOrder: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class TradeResponse(BaseModel):
    """Trade record for a trader."""

    id: str
    traderAddress: str
    marketId: str
    marketQuestion: str
    outcomeId: str
    outcomeName: str
    side: Literal["BUY", "SELL"]
    price: float
    quantity: float
    usdValue: float
    fees: float
    realizedPnl: float | None = None
    timestamp: str


class TradeListResponse(BaseModel):
    """Paginated list of trades."""

    items: list[TradeResponse]
    total: int
    page: int
    limit: int


class TradeFilters(BaseModel):
    """Query parameters for filtering trades."""

    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    startDate: str | None = None
    endDate: str | None = None
    marketId: str | None = None


class LeaderboardEntry(BaseModel):
    """Entry in the PnL leaderboard."""

    rank: int
    traderAddress: str
    pnl: float
    tradeCount: int
    winRate: float


class LeaderboardResponse(BaseModel):
    """Leaderboard response with entries."""

    period: str
    entries: list[LeaderboardEntry]
    generatedAt: str


class LeaderboardFilters(BaseModel):
    """Query parameters for leaderboard."""

    period: Literal["1d", "7d", "30d", "all"] = "7d"
    limit: int = Field(default=100, ge=1, le=500)


class SmartTradeResponse(TradeResponse):
    """Trade response with smart score of the trader."""

    smartScore: float


class SmartTradeFilters(BaseModel):
    """Query parameters for smart trades."""

    minScore: float = Field(default=70, ge=0, le=100)
    minAmount: float | None = None
    limit: int = Field(default=50, ge=1, le=200)


class WhaleTradeResponse(TradeResponse):
    """Trade response with whale metadata."""

    totalWalletValue: float


class WhaleTradeFilters(BaseModel):
    """Query parameters for whale trades."""

    minAmount: float = Field(default=10000, ge=0)
    limit: int = Field(default=50, ge=1, le=200)
