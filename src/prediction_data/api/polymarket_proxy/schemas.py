"""Pydantic schemas for Polymarket proxy layer responses."""

from pydantic import BaseModel, Field


class ProxyHealthStatus(BaseModel):
    """Health status for a single API."""

    status: str = Field(
        ...,
        description="Health status: healthy, degraded, or unhealthy",
        json_schema_extra={"example": "healthy"},
    )
    status_code: int | None = Field(
        None,
        description="HTTP status code from health check",
        json_schema_extra={"example": 200},
    )
    latency_ms: float | None = Field(
        None,
        description="Response latency in milliseconds",
        json_schema_extra={"example": 45.2},
    )
    error: str | None = Field(
        None,
        description="Error message if unhealthy",
    )


class ProxyHealthResponse(BaseModel):
    """Health status for all proxied Polymarket APIs."""

    clob: ProxyHealthStatus = Field(
        ...,
        description="CLOB API health status",
    )
    data: ProxyHealthStatus = Field(
        ...,
        description="Data API health status",
    )
    gamma: ProxyHealthStatus = Field(
        ...,
        description="Gamma API health status",
    )
    cache_stats: dict[str, int | float | str] = Field(
        ...,
        description="Cache statistics (size, hits, misses, hit_rate, backend)",
        json_schema_extra={
            "example": {
                "size": 100,
                "hits": 500,
                "misses": 50,
                "hit_rate": 91.0,
                "backend": "memory",
            }
        },
    )
    circuit_status: dict[str, str] = Field(
        ...,
        description="Circuit breaker status for each API",
        json_schema_extra={"example": {"clob": "closed", "data": "closed", "gamma": "closed"}},
    )


class ProxyErrorResponse(BaseModel):
    """Error response from proxy layer."""

    detail: str = Field(
        ...,
        description="Error description",
        json_schema_extra={"example": "Circuit breaker open for clob API"},
    )
    code: str = Field(
        ...,
        description="Error code",
        json_schema_extra={"example": "PROXY_ERROR"},
    )
    upstream_status: int | None = Field(
        None,
        description="HTTP status from upstream API if available",
    )
    retry_after: int | None = Field(
        None,
        description="Seconds to wait before retrying (for rate limit errors)",
    )


class TokenInfo(BaseModel):
    """Token information for a market outcome."""

    outcome_id: str = Field(
        ...,
        description="Internal outcome ID (market_id_index)",
        json_schema_extra={"example": "0x123abc_0"},
    )
    token_id: str = Field(
        ...,
        description="Polymarket CLOB token ID for this outcome",
        json_schema_extra={"example": "71321045679252212594626385532706912750332728571942532289631379312455583286914"},
    )
    side: str = Field(
        ...,
        description="Token side (token1 = Yes, token2 = No)",
        json_schema_extra={"example": "token1"},
    )
    outcome_label: str = Field(
        ...,
        description="Human-readable outcome label",
        json_schema_extra={"example": "Yes"},
    )


class MarketTokensResponse(BaseModel):
    """Token ID mappings for a market."""

    market_id: str = Field(
        ...,
        description="Our platform_market_id",
        json_schema_extra={"example": "0x123abc456def"},
    )
    tokens: list[TokenInfo] = Field(
        ...,
        description="List of token IDs for each outcome",
    )
    yes_token_id: str | None = Field(
        None,
        description="Token ID for the YES outcome (convenience field)",
        json_schema_extra={"example": "71321045679252212594626385532706912750332728571942532289631379312455583286914"},
    )
    no_token_id: str | None = Field(
        None,
        description="Token ID for the NO outcome (convenience field)",
        json_schema_extra={"example": "48331043779252212594626385532706912750332728571942532289631379312455583286915"},
    )


class TokenResolverStats(BaseModel):
    """Statistics for the token resolver cache."""

    cache_size: int = Field(
        ...,
        description="Number of market mappings cached",
        json_schema_extra={"example": 1000},
    )
    cache_hits: int = Field(
        ...,
        description="Number of cache hits",
        json_schema_extra={"example": 5000},
    )
    cache_misses: int = Field(
        ...,
        description="Number of cache misses",
        json_schema_extra={"example": 200},
    )
    hit_rate: float = Field(
        ...,
        description="Cache hit rate percentage",
        json_schema_extra={"example": 96.2},
    )


class PricePoint(BaseModel):
    """Single price point in timeseries data."""

    timestamp: int = Field(
        ...,
        description="Unix timestamp (UTC)",
        json_schema_extra={"example": 1697875200},
    )
    price: float = Field(
        ...,
        description="Price at this timestamp (0-1 for probability)",
        json_schema_extra={"example": 0.65},
    )


class PriceHistoryResponse(BaseModel):
    """Price history timeseries response."""

    token_id: str = Field(
        ...,
        description="Polymarket CLOB token ID",
        json_schema_extra={"example": "71321045679252212594626385532706912750332728571942532289631379312455583286914"},
    )
    interval: str | None = Field(
        None,
        description="Interval used for the query (1m, 1h, 6h, 1d, 1w, max)",
        json_schema_extra={"example": "1h"},
    )
    fidelity: int | None = Field(
        None,
        description="Resolution of the data in minutes",
        json_schema_extra={"example": 15},
    )
    start_ts: int | None = Field(
        None,
        description="Start timestamp if date range was specified",
        json_schema_extra={"example": 1697788800},
    )
    end_ts: int | None = Field(
        None,
        description="End timestamp if date range was specified",
        json_schema_extra={"example": 1697875200},
    )
    history: list[PricePoint] = Field(
        ...,
        description="List of price points in chronological order",
    )
    cache_status: str = Field(
        ...,
        description="Cache status: HIT, MISS, or STALE",
        json_schema_extra={"example": "HIT"},
    )


class OrderLevel(BaseModel):
    """Single price level in the order book."""

    price: str = Field(
        ...,
        description="Price at this level (0-1 for probability)",
        json_schema_extra={"example": "0.65"},
    )
    size: str = Field(
        ...,
        description="Total quantity available at this price",
        json_schema_extra={"example": "1500.50"},
    )


class OrderBookResponse(BaseModel):
    """Order book (L2) response for a token."""

    token_id: str = Field(
        ...,
        description="Polymarket CLOB token ID",
        json_schema_extra={"example": "71321045679252212594626385532706912750332728571942532289631379312455583286914"},
    )
    market: str = Field(
        ...,
        description="Market condition ID",
        json_schema_extra={"example": "0x1b6f76e5b8587ee896c35847e12d11e75290a8c3934c5952e8a9d6e4c6f03cfa"},
    )
    timestamp: str = Field(
        ...,
        description="Snapshot timestamp (ISO 8601 format)",
        json_schema_extra={"example": "2023-10-01T12:00:00Z"},
    )
    bids: list[OrderLevel] = Field(
        ...,
        description="Bid levels sorted by price descending (best bid first)",
    )
    asks: list[OrderLevel] = Field(
        ...,
        description="Ask levels sorted by price ascending (best ask first)",
    )
    spread: str | None = Field(
        None,
        description="Bid-ask spread (best ask - best bid)",
        json_schema_extra={"example": "0.02"},
    )
    mid_price: str | None = Field(
        None,
        description="Mid price ((best bid + best ask) / 2)",
        json_schema_extra={"example": "0.66"},
    )
    best_bid: str | None = Field(
        None,
        description="Best (highest) bid price",
        json_schema_extra={"example": "0.65"},
    )
    best_ask: str | None = Field(
        None,
        description="Best (lowest) ask price",
        json_schema_extra={"example": "0.67"},
    )
    tick_size: str = Field(
        ...,
        description="Minimum price increment",
        json_schema_extra={"example": "0.01"},
    )
    min_order_size: str = Field(
        ...,
        description="Minimum tradeable quantity",
        json_schema_extra={"example": "0.001"},
    )
    cache_status: str = Field(
        ...,
        description="Cache status: HIT, MISS, or STALE",
        json_schema_extra={"example": "MISS"},
    )


class Trade(BaseModel):
    """Single trade from the activity feed."""

    id: str = Field(
        ...,
        description="Unique trade identifier (transaction hash)",
        json_schema_extra={"example": "0x1234567890abcdef"},
    )
    price: str = Field(
        ...,
        description="Trade price (0-1 for probability)",
        json_schema_extra={"example": "0.65"},
    )
    size: str = Field(
        ...,
        description="Trade size in tokens",
        json_schema_extra={"example": "100.50"},
    )
    side: str = Field(
        ...,
        description="Trade side (BUY or SELL)",
        json_schema_extra={"example": "BUY"},
    )
    timestamp: int = Field(
        ...,
        description="Unix timestamp in milliseconds",
        json_schema_extra={"example": 1697875200000},
    )
    maker_address: str | None = Field(
        None,
        description="Wallet address of the maker",
        json_schema_extra={"example": "0xabc123..."},
    )
    outcome: str | None = Field(
        None,
        description="Outcome name (e.g., 'Yes', 'No')",
        json_schema_extra={"example": "Yes"},
    )
    outcome_index: int | None = Field(
        None,
        description="Outcome index (0 for Yes, 1 for No)",
        json_schema_extra={"example": 0},
    )


class RecentTradesResponse(BaseModel):
    """Response for recent trades query."""

    token_id: str = Field(
        ...,
        description="Polymarket CLOB token ID or condition ID",
        json_schema_extra={"example": "0x123abc"},
    )
    trades: list[Trade] = Field(
        ...,
        description="List of recent trades, most recent first",
    )
    count: int = Field(
        ...,
        description="Number of trades returned",
        json_schema_extra={"example": 50},
    )
    has_more: bool = Field(
        ...,
        description="Whether more trades exist beyond the limit",
        json_schema_extra={"example": True},
    )
    cache_status: str = Field(
        ...,
        description="Cache status: HIT, MISS, or STALE",
        json_schema_extra={"example": "MISS"},
    )


class TokenPrice(BaseModel):
    """Price information for a single token/outcome."""

    token_id: str = Field(
        ...,
        description="Polymarket CLOB token ID",
        json_schema_extra={"example": "71321045679252212594626385532706912750332728571942532289631379312455583286914"},
    )
    outcome: str = Field(
        ...,
        description="Outcome label (e.g., 'Yes', 'No', or custom)",
        json_schema_extra={"example": "Yes"},
    )
    price: float = Field(
        ...,
        description="Current price (0-1 for probability)",
        json_schema_extra={"example": 0.65},
    )
    winner: bool | None = Field(
        None,
        description="Whether this outcome won (None if not resolved)",
        json_schema_extra={"example": False},
    )


class MarketInfoResponse(BaseModel):
    """Real-time market information including prices, volume, and liquidity."""

    condition_id: str = Field(
        ...,
        description="Polymarket condition ID (market identifier)",
        json_schema_extra={"example": "0x1b6f76e5b8587ee896c35847e12d11e75290a8c3934c5952e8a9d6e4c6f03cfa"},
    )
    question: str | None = Field(
        None,
        description="Market question text",
        json_schema_extra={"example": "Will Bitcoin reach $100k by end of 2024?"},
    )
    tokens: list[TokenPrice] = Field(
        ...,
        description="Current prices for each outcome token",
    )
    active: bool = Field(
        ...,
        description="Whether the market is active for trading",
        json_schema_extra={"example": True},
    )
    closed: bool = Field(
        ...,
        description="Whether the market has been resolved/closed",
        json_schema_extra={"example": False},
    )
    accepting_orders: bool = Field(
        ...,
        description="Whether the market is currently accepting orders",
        json_schema_extra={"example": True},
    )
    volume_24h: float | None = Field(
        None,
        description="24-hour trading volume in USD",
        json_schema_extra={"example": 150000.50},
    )
    liquidity: float | None = Field(
        None,
        description="Market liquidity metric",
        json_schema_extra={"example": 75000.00},
    )
    minimum_order_size: float = Field(
        ...,
        description="Minimum order size for this market",
        json_schema_extra={"example": 15.0},
    )
    minimum_tick_size: float = Field(
        ...,
        description="Minimum price increment",
        json_schema_extra={"example": 0.01},
    )
    data_source: str = Field(
        ...,
        description="Data source: 'clob' for real-time or 'fallback' for cached dim_market",
        json_schema_extra={"example": "clob"},
    )
    cache_status: str = Field(
        ...,
        description="Cache status: HIT, MISS, or STALE",
        json_schema_extra={"example": "MISS"},
    )


class TopHolder(BaseModel):
    """Single holder in the top holders list."""

    wallet_address: str = Field(
        ...,
        description="Wallet address of the holder (proxy wallet)",
        json_schema_extra={"example": "0x1234567890abcdef1234567890abcdef12345678"},
    )
    amount: str = Field(
        ...,
        description="Token balance held",
        json_schema_extra={"example": "15000.50"},
    )
    pseudonym: str | None = Field(
        None,
        description="User pseudonym if available",
        json_schema_extra={"example": "crypto_whale_99"},
    )
    name: str | None = Field(
        None,
        description="User display name if public",
        json_schema_extra={"example": "John Doe"},
    )
    profile_image: str | None = Field(
        None,
        description="URL to user profile image",
        json_schema_extra={"example": "https://polymarket.com/images/profile/123.jpg"},
    )
    outcome_index: int | None = Field(
        None,
        description="Outcome index for this position (0 for Yes, 1 for No)",
        json_schema_extra={"example": 0},
    )


class TopHoldersResponse(BaseModel):
    """Response for top holders query."""

    condition_id: str = Field(
        ...,
        description="Polymarket market condition ID",
        json_schema_extra={"example": "0x1b6f76e5b8587ee896c35847e12d11e75290a8c3934c5952e8a9d6e4c6f03cfa"},
    )
    token_id: str | None = Field(
        None,
        description="Token ID if querying specific outcome (None if querying full market)",
        json_schema_extra={"example": "71321045679252212594626385532706912750332728571942532289631379312455583286914"},
    )
    holders: list[TopHolder] = Field(
        ...,
        description="List of top holders sorted by balance descending",
    )
    count: int = Field(
        ...,
        description="Number of holders returned",
        json_schema_extra={"example": 20},
    )
    cache_status: str = Field(
        ...,
        description="Cache status: HIT, MISS, or STALE",
        json_schema_extra={"example": "MISS"},
    )
