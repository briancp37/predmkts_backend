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
