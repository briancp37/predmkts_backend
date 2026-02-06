"""FastAPI router for Polymarket proxy endpoints.

Provides proxy endpoints for accessing Polymarket API data with:
- Caching to reduce upstream load
- Rate limiting to stay under Polymarket limits
- Circuit breaker for failure protection
- Token ID resolution from our database
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from prediction_data.api.polymarket_proxy.client import (
    PolymarketProxyClient,
    get_proxy_client,
)
from prediction_data.api.polymarket_proxy.schemas import (
    MarketTokensResponse,
    ProxyHealthResponse,
    ProxyHealthStatus,
    TokenInfo,
    TokenResolverStats,
)
from prediction_data.api.polymarket_proxy.token_resolver import (
    TokenResolver,
    get_token_resolver,
)
from prediction_data.api.rate_limit import CLOB_PROXY_RATE_LIMIT, PUBLIC_RATE_LIMIT, limiter

router = APIRouter()

# Type aliases for dependency injection
ProxyClient = Annotated[PolymarketProxyClient, Depends(get_proxy_client)]
TokenResolverDep = Annotated[TokenResolver, Depends(get_token_resolver)]


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


@router.get(
    "/markets/{market_id}/tokens",
    response_model=MarketTokensResponse,
    summary="Get token IDs for a market",
    description=(
        "Get Polymarket CLOB token IDs for a market's outcomes. "
        "Token IDs are required for CLOB API calls (order book, price history, etc.). "
        "Results are cached since token IDs don't change."
    ),
    responses={
        404: {
            "description": "Market not found or has no token mappings",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "No token mappings found for market",
                        "code": "NOT_FOUND",
                        "status": 404,
                    }
                }
            },
        }
    },
)
@limiter.limit(PUBLIC_RATE_LIMIT)
async def get_market_tokens(
    request: Request,
    market_id: str,
    resolver: TokenResolverDep,
) -> MarketTokensResponse:
    """Get token ID mappings for a market.

    Maps our market_id (platform_market_id) to Polymarket CLOB token IDs.
    Binary markets have two tokens (Yes and No outcomes).
    Multi-outcome markets may have more tokens.

    Token IDs are needed for:
    - Order book queries (GET /book?token_id=...)
    - Price history (GET /prices-history?market=...)
    - Trade queries (GET /trades?asset_id=...)
    """
    market_tokens = await resolver.get_tokens(market_id)

    if not market_tokens or not market_tokens.tokens:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "No token mappings found for market",
                "code": "NOT_FOUND",
                "market_id": market_id,
            },
        )

    tokens = [
        TokenInfo(
            outcome_id=t["outcome_id"],
            token_id=t["token_id"],
            side=t["side"],
            outcome_label=t["outcome_label"],
        )
        for t in market_tokens.tokens
    ]

    return MarketTokensResponse(
        market_id=market_id,
        tokens=tokens,
        yes_token_id=market_tokens.yes_token_id,
        no_token_id=market_tokens.no_token_id,
    )


@router.get(
    "/tokens/stats",
    response_model=TokenResolverStats,
    summary="Get token resolver cache statistics",
    description="Returns cache hit/miss statistics for the token resolver.",
)
@limiter.limit(CLOB_PROXY_RATE_LIMIT)
async def get_token_resolver_stats(
    request: Request,
    resolver: TokenResolverDep,
) -> TokenResolverStats:
    """Get statistics for the token resolver cache.

    Useful for monitoring cache efficiency and debugging.
    """
    stats = resolver.get_stats()
    return TokenResolverStats(
        cache_size=int(stats["cache_size"]),
        cache_hits=int(stats["cache_hits"]),
        cache_misses=int(stats["cache_misses"]),
        hit_rate=float(stats["hit_rate"]),
    )
