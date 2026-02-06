"""Pydantic schemas for trader data."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from prediction_data.api.validators import DateString, validate_date_range


class TraderPosition(BaseModel):
    """Current position held by a trader."""

    marketId: str = Field(
        ...,
        description="Market ID for this position",
        json_schema_extra={"example": "market-12345"},
    )
    marketQuestion: str = Field(
        ...,
        description="Market question text",
        json_schema_extra={"example": "Will Bitcoin reach $100k by 2025?"},
    )
    outcomeId: str = Field(
        ...,
        description="Outcome ID",
        json_schema_extra={"example": "outcome-yes-123"},
    )
    outcomeName: str = Field(
        ...,
        description="Outcome name",
        json_schema_extra={"example": "Yes"},
    )
    quantity: float = Field(
        ...,
        description="Number of shares held",
        json_schema_extra={"example": 1500.0},
    )
    avgCost: float = Field(
        ...,
        description="Average cost basis per share (0.0 to 1.0)",
        json_schema_extra={"example": 0.45},
    )
    currentPrice: float = Field(
        ...,
        description="Current market price per share",
        json_schema_extra={"example": 0.65},
    )
    unrealizedPnl: float = Field(
        ...,
        description="Unrealized profit/loss in USD",
        json_schema_extra={"example": 300.00},
    )
    realizedPnl: float = Field(
        ...,
        description="Realized profit/loss in USD",
        json_schema_extra={"example": 150.00},
    )


class TraderBase(BaseModel):
    """Base trader information."""

    address: str = Field(
        ...,
        description="Ethereum wallet address (lowercase, 0x + 40 hex chars)",
        json_schema_extra={"example": "0x1234567890abcdef1234567890abcdef12345678"},
    )
    username: str | None = Field(
        default=None,
        description="Polymarket username if linked",
        json_schema_extra={"example": "cryptotrader42"},
    )
    firstSeen: str = Field(
        ...,
        description="First trade timestamp (ISO 8601)",
        json_schema_extra={"example": "2023-06-15T10:30:00Z"},
    )
    totalPnl: float = Field(
        ...,
        description="Total profit/loss (realized + unrealized) in USD",
        json_schema_extra={"example": 15000.50},
    )
    realizedPnl: float = Field(
        ...,
        description="Realized profit/loss in USD",
        json_schema_extra={"example": 8000.00},
    )
    totalTrades: int = Field(
        ...,
        description="Total number of trades executed",
        json_schema_extra={"example": 342},
    )
    winCount: int = Field(
        ...,
        description="Number of winning trades",
        json_schema_extra={"example": 185},
    )
    lossCount: int = Field(
        ...,
        description="Number of losing trades",
        json_schema_extra={"example": 157},
    )


class TraderResponse(TraderBase):
    """Trader response with additional metadata."""

    id: str = Field(
        ...,
        description="Internal trader identifier",
        json_schema_extra={"example": "trader-abc123"},
    )
    smartScore: float | None = Field(
        default=None,
        description="Smart score (0-100) based on trading performance. Null if <5 trades.",
        json_schema_extra={"example": 78.5},
    )
    createdAt: str = Field(
        ...,
        description="Record creation timestamp",
        json_schema_extra={"example": "2024-01-15T10:30:00Z"},
    )
    updatedAt: str = Field(
        ...,
        description="Last update timestamp",
        json_schema_extra={"example": "2024-01-20T14:00:00Z"},
    )


class TraderDetailResponse(TraderResponse):
    """Detailed trader response with positions and stats."""

    positions: list[TraderPosition] = Field(
        default_factory=list,
        description="Current open positions",
    )
    tradeCount: int = Field(
        ...,
        description="Total trade count",
        json_schema_extra={"example": 342},
    )
    winRate: float = Field(
        ...,
        description="Win rate as decimal (0.0 to 1.0)",
        json_schema_extra={"example": 0.54},
    )


class TraderListResponse(BaseModel):
    """Paginated list of traders."""

    items: list[TraderResponse] = Field(..., description="List of traders")
    total: int = Field(..., description="Total number of matching traders")
    page: int = Field(..., description="Current page number")
    limit: int = Field(..., description="Results per page")


class SmartScoreComponents(BaseModel):
    """Components that make up a smart score.

    Weighted: 30% accuracy, 25% consistency, 25% sizing, 20% timing.
    """

    accuracy: float = Field(
        ...,
        description="Accuracy score (0-100) - based on win rate",
        json_schema_extra={"example": 82.0},
    )
    consistency: float = Field(
        ...,
        description="Consistency score (0-100) - based on stable returns",
        json_schema_extra={"example": 75.0},
    )
    sizing: float = Field(
        ...,
        description="Sizing score (0-100) - based on proper position sizing",
        json_schema_extra={"example": 68.0},
    )
    timing: float = Field(
        ...,
        description="Timing score (0-100) - based on entry/exit timing",
        json_schema_extra={"example": 72.0},
    )


class SmartScoreResponse(BaseModel):
    """Smart score response for a trader."""

    address: str = Field(
        ...,
        description="Trader wallet address",
        json_schema_extra={"example": "0x1234567890abcdef1234567890abcdef12345678"},
    )
    smartScore: float = Field(
        ...,
        description="Overall smart score (0-100)",
        json_schema_extra={"example": 78.5},
    )
    components: SmartScoreComponents = Field(
        ..., description="Individual score components"
    )


class SmartScoreListResponse(BaseModel):
    """List of smart scores."""

    items: list[SmartScoreResponse] = Field(..., description="List of smart scores")
    timeWindow: str = Field(
        ...,
        description="Time window used for calculation",
        json_schema_extra={"example": "30d"},
    )
    generatedAt: str = Field(
        ...,
        description="When scores were calculated",
        json_schema_extra={"example": "2024-01-20T00:00:00Z"},
    )


class SmartScoreFilters(BaseModel):
    """Query parameters for smart scores endpoint."""

    minScore: float = Field(
        default=0,
        ge=0,
        le=100,
        description="Minimum smart score to include",
        json_schema_extra={"example": 70},
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=500,
        description="Maximum results to return",
    )
    timeWindow: Literal["7d", "30d", "90d", "all"] = Field(
        default="30d",
        description="Time window for score calculation",
        json_schema_extra={"example": "30d"},
    )


class TraderFilters(BaseModel):
    """Query parameters for filtering traders."""

    search: str | None = Field(
        default=None,
        description="Search by address or username",
        json_schema_extra={"example": "0x1234"},
    )
    sortBy: Literal["smartScore", "totalPnl", "totalTrades", "winRate"] = Field(
        default="totalPnl",
        description="Field to sort by",
    )
    sortOrder: Literal["asc", "desc"] = Field(
        default="desc",
        description="Sort order (asc or desc)",
    )
    limit: int = Field(
        default=50, ge=1, le=500, description="Maximum results to return"
    )
    offset: int = Field(default=0, ge=0, description="Number of results to skip")


class TradeResponse(BaseModel):
    """Trade record for a trader."""

    id: str = Field(
        ...,
        description="Unique trade identifier",
        json_schema_extra={"example": "trade-abc123"},
    )
    traderAddress: str = Field(
        ...,
        description="Trader wallet address",
        json_schema_extra={"example": "0x1234567890abcdef1234567890abcdef12345678"},
    )
    marketId: str = Field(
        ...,
        description="Market ID",
        json_schema_extra={"example": "market-12345"},
    )
    marketQuestion: str = Field(
        ...,
        description="Market question text",
        json_schema_extra={"example": "Will Bitcoin reach $100k by 2025?"},
    )
    outcomeId: str = Field(
        ...,
        description="Outcome ID",
        json_schema_extra={"example": "outcome-yes-123"},
    )
    outcomeName: str = Field(
        ...,
        description="Outcome name",
        json_schema_extra={"example": "Yes"},
    )
    side: Literal["BUY", "SELL"] = Field(
        ...,
        description="Trade side",
        json_schema_extra={"example": "BUY"},
    )
    price: float = Field(
        ...,
        description="Execution price (0.0 to 1.0)",
        json_schema_extra={"example": 0.65},
    )
    quantity: float = Field(
        ...,
        description="Number of shares traded",
        json_schema_extra={"example": 1000.0},
    )
    usdValue: float = Field(
        ...,
        description="USD value of trade",
        json_schema_extra={"example": 650.00},
    )
    fees: float = Field(
        ...,
        description="Trading fees in USD",
        json_schema_extra={"example": 1.30},
    )
    realizedPnl: float | None = Field(
        default=None,
        description="Realized PnL if closing position",
        json_schema_extra={"example": 50.00},
    )
    timestamp: str = Field(
        ...,
        description="Trade timestamp (ISO 8601)",
        json_schema_extra={"example": "2024-01-15T10:30:00Z"},
    )


class TradeListResponse(BaseModel):
    """Paginated list of trades."""

    items: list[TradeResponse] = Field(..., description="List of trades")
    total: int = Field(..., description="Total number of matching trades")
    page: int = Field(..., description="Current page number")
    limit: int = Field(..., description="Results per page")


class TradeFilters(BaseModel):
    """Query parameters for filtering trades."""

    limit: int = Field(
        default=100, ge=1, le=1000, description="Maximum results to return"
    )
    offset: int = Field(default=0, ge=0, description="Number of results to skip")
    startDate: DateString | None = Field(
        default=None,
        description="Filter trades on or after this date (YYYY-MM-DD)",
        json_schema_extra={"example": "2024-01-01"},
    )
    endDate: DateString | None = Field(
        default=None,
        description="Filter trades on or before this date (YYYY-MM-DD)",
        json_schema_extra={"example": "2024-01-31"},
    )
    marketId: str | None = Field(
        default=None,
        description="Filter by specific market ID",
    )

    @model_validator(mode="after")
    def validate_date_range_order(self) -> "TradeFilters":
        """Ensure startDate <= endDate when both are provided."""
        validate_date_range(self.startDate, self.endDate)
        return self


class LeaderboardEntry(BaseModel):
    """Entry in the PnL leaderboard."""

    rank: int = Field(
        ...,
        description="Position on the leaderboard (1-indexed)",
        json_schema_extra={"example": 1},
    )
    traderAddress: str = Field(
        ...,
        description="Trader wallet address",
        json_schema_extra={"example": "0x1234567890abcdef1234567890abcdef12345678"},
    )
    pnl: float = Field(
        ...,
        description="Total PnL for the period in USD",
        json_schema_extra={"example": 25000.00},
    )
    tradeCount: int = Field(
        ...,
        description="Number of trades in the period",
        json_schema_extra={"example": 45},
    )
    winRate: float = Field(
        ...,
        description="Win rate as decimal (0.0 to 1.0)",
        json_schema_extra={"example": 0.62},
    )


class LeaderboardResponse(BaseModel):
    """Leaderboard response with entries."""

    period: str = Field(
        ...,
        description="Time period for the leaderboard",
        json_schema_extra={"example": "7d"},
    )
    entries: list[LeaderboardEntry] = Field(..., description="Leaderboard entries")
    generatedAt: str = Field(
        ...,
        description="When the leaderboard was generated",
        json_schema_extra={"example": "2024-01-20T00:00:00Z"},
    )


class LeaderboardFilters(BaseModel):
    """Query parameters for leaderboard."""

    period: Literal["1d", "7d", "30d", "all"] = Field(
        default="7d",
        description="Time period for rankings",
        json_schema_extra={"example": "7d"},
    )
    limit: int = Field(
        default=100, ge=1, le=500, description="Maximum entries to return"
    )


class SmartTradeResponse(TradeResponse):
    """Trade response with smart score of the trader."""

    smartScore: float = Field(
        ...,
        description="Trader's smart score at time of trade",
        json_schema_extra={"example": 85.0},
    )


class SmartTradeFilters(BaseModel):
    """Query parameters for smart trades."""

    minScore: float = Field(
        default=70,
        ge=0,
        le=100,
        description="Minimum smart score threshold (traders below this are excluded)",
        json_schema_extra={"example": 70},
    )
    minAmount: float | None = Field(
        default=None,
        description="Minimum trade USD value",
        json_schema_extra={"example": 1000},
    )
    limit: int = Field(
        default=50, ge=1, le=200, description="Maximum results to return"
    )


class WhaleTradeResponse(TradeResponse):
    """Trade response with whale metadata."""

    totalWalletValue: float = Field(
        ...,
        description="Total portfolio value of the whale trader in USD",
        json_schema_extra={"example": 500000.00},
    )


class WhaleTradeFilters(BaseModel):
    """Query parameters for whale trades."""

    minAmount: float = Field(
        default=10000,
        ge=0,
        description="Minimum trade USD value to qualify as whale trade",
        json_schema_extra={"example": 10000},
    )
    limit: int = Field(
        default=50, ge=1, le=200, description="Maximum results to return"
    )
