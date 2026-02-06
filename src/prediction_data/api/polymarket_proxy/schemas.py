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
    cache_stats: dict[str, int] = Field(
        ...,
        description="Cache statistics (size, hits, misses, hit_rate)",
        json_schema_extra={"example": {"size": 100, "hits": 500, "misses": 50, "hit_rate": 91}},
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
