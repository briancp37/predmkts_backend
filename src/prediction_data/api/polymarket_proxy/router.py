"""FastAPI router for Polymarket proxy endpoints.

Provides proxy endpoints for accessing Polymarket API data with:
- Caching to reduce upstream load
- Rate limiting to stay under Polymarket limits
- Circuit breaker for failure protection
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from prediction_data.api.polymarket_proxy.client import (
    PolymarketProxyClient,
    get_proxy_client,
)
from prediction_data.api.polymarket_proxy.schemas import (
    ProxyHealthResponse,
    ProxyHealthStatus,
)
from prediction_data.api.rate_limit import CLOB_PROXY_RATE_LIMIT, limiter

router = APIRouter()

# Type alias for dependency injection
ProxyClient = Annotated[PolymarketProxyClient, Depends(get_proxy_client)]


@router.get(
    "/health",
    response_model=ProxyHealthResponse,
    summary="Check Polymarket API health",
    description="Check connectivity and health of all proxied Polymarket APIs.",
)
@limiter.limit(CLOB_PROXY_RATE_LIMIT)
async def health_check(
    request: Request,
    client: ProxyClient,
) -> ProxyHealthResponse:
    """Check health of Polymarket APIs.

    Returns health status for CLOB, Data, and Gamma APIs, along with
    cache statistics and circuit breaker status.
    """
    health = await client.health_check()

    return ProxyHealthResponse(
        clob=ProxyHealthStatus(**health["clob"]),
        data=ProxyHealthStatus(**health["data"]),
        gamma=ProxyHealthStatus(**health["gamma"]),
        cache_stats=client.get_cache_stats(),
        circuit_status=client.get_circuit_status(),
    )
