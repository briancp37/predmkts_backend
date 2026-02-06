"""FastAPI router for Polymarket proxy endpoints.

Provides proxy endpoints for accessing Polymarket API data with:
- Caching to reduce upstream load
- Rate limiting to stay under Polymarket limits
- Circuit breaker for failure protection
- Token ID resolution from our database
- Proper error handling with structured responses
"""

from enum import Enum
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Query, Request

from prediction_data.api.polymarket_proxy.client import (
    PolymarketProxyClient,
    get_proxy_client,
)
from prediction_data.api.polymarket_proxy.exceptions import (
    CircuitOpenError,
    ProxyError,
    UpstreamNotFoundError,
    UpstreamRateLimitError,
)
from prediction_data.api.polymarket_proxy.schemas import (
    MarketTokensResponse,
    OrderBookResponse,
    OrderLevel,
    PriceHistoryResponse,
    PricePoint,
    ProxyHealthResponse,
    ProxyHealthStatus,
    RecentTradesResponse,
    TokenInfo,
    TokenResolverStats,
    Trade,
)
from prediction_data.api.polymarket_proxy.token_resolver import (
    TokenResolver,
    get_token_resolver,
)
from prediction_data.api.rate_limit import CLOB_PROXY_RATE_LIMIT, PUBLIC_RATE_LIMIT, limiter
from prediction_data.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Type aliases for dependency injection
ProxyClient = Annotated[PolymarketProxyClient, Depends(get_proxy_client)]
TokenResolverDep = Annotated[TokenResolver, Depends(get_token_resolver)]


class TimeseriesInterval(str, Enum):
    """Valid interval options for timeseries queries."""

    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    ONE_HOUR = "1h"
    SIX_HOURS = "6h"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"
    MAX = "max"


# Cache TTL mapping based on interval volatility
# More granular intervals = shorter cache TTL
INTERVAL_CACHE_TTL: dict[str, int] = {
    "1m": 30,     # 30 seconds for 1-minute data
    "5m": 60,     # 1 minute for 5-minute data
    "15m": 120,   # 2 minutes for 15-minute data
    "1h": 300,    # 5 minutes for hourly data
    "6h": 600,    # 10 minutes for 6-hour data
    "1d": 3600,   # 1 hour for daily data
    "1w": 3600,   # 1 hour for weekly data
    "max": 3600,  # 1 hour for max range
}

# Default TTL for date range queries (no interval)
DATE_RANGE_CACHE_TTL = 60


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
    "/markets/{token_id}/timeseries",
    response_model=PriceHistoryResponse,
    summary="Get price history for a token",
    description=(
        "Get historical price data for a Polymarket CLOB token. "
        "Use either interval (1m, 5m, 15m, 1h, 6h, 1d, 1w, max) OR startTs/endTs for date range. "
        "Response is cached with TTL based on interval granularity."
    ),
    responses={
        502: {
            "description": "Upstream Polymarket API error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Polymarket API request failed",
                        "code": "PROXY_ERROR",
                        "status": 502,
                    }
                }
            },
        },
        503: {
            "description": "Circuit breaker open",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Circuit breaker open for clob API",
                        "code": "SERVICE_UNAVAILABLE",
                        "retry_after": 30,
                    }
                }
            },
        },
    },
)
@limiter.limit(CLOB_PROXY_RATE_LIMIT)
async def get_timeseries(
    request: Request,
    token_id: str,
    client: ProxyClient,
    interval: TimeseriesInterval | None = Query(
        None,
        description="Time interval for data points. Mutually exclusive with startTs/endTs.",
    ),
    fidelity: int | None = Query(
        None,
        ge=1,
        le=60,
        description="Resolution in minutes (1-60). Controls data granularity.",
    ),
    start_ts: int | None = Query(
        None,
        alias="startTs",
        description="Start Unix timestamp (UTC). Use with endTs for custom date range.",
    ),
    end_ts: int | None = Query(
        None,
        alias="endTs",
        description="End Unix timestamp (UTC). Use with startTs for custom date range.",
    ),
) -> PriceHistoryResponse:
    """Get price history timeseries for a token.

    Proxies to Polymarket CLOB `/prices-history` endpoint with caching.

    **Usage modes:**
    1. **Interval mode:** Specify `interval` (1m, 5m, 15m, 1h, 6h, 1d, 1w, max)
    2. **Date range mode:** Specify `startTs` and `endTs` timestamps

    The `fidelity` parameter controls data resolution in minutes. Higher values
    return fewer data points. Use lower fidelity for broader time ranges.

    **Cache TTL by interval:**
    - 1m: 30s, 5m: 60s, 15m: 2min, 1h: 5min, 6h/1d/1w/max: 1h
    - Date range queries: 60s
    """
    # Build query params for upstream
    params: dict[str, str | int] = {"market": token_id}

    if interval is not None:
        params["interval"] = interval.value
    if fidelity is not None:
        params["fidelity"] = fidelity
    if start_ts is not None:
        params["startTs"] = start_ts
    if end_ts is not None:
        params["endTs"] = end_ts

    # Determine cache TTL
    if interval is not None:
        cache_ttl = INTERVAL_CACHE_TTL.get(interval.value, DATE_RANGE_CACHE_TTL)
    else:
        cache_ttl = DATE_RANGE_CACHE_TTL

    try:
        data, cache_status = await client.get_clob(
            "/prices-history",
            params,
            cache_ttl=cache_ttl,
        )
    except (CircuitOpenError, UpstreamRateLimitError) as e:
        # These exceptions already have proper status codes and details
        logger.warning(
            "Timeseries proxy error",
            token_id=token_id,
            interval=interval.value if interval else None,
            error_type=type(e).__name__,
        )
        raise
    except ProxyError as e:
        logger.error(
            "Timeseries proxy upstream failure",
            token_id=token_id,
            interval=interval.value if interval else None,
            error=str(e),
        )
        raise
    except httpx.HTTPStatusError as e:
        logger.error(
            "Timeseries proxy HTTP error",
            token_id=token_id,
            status_code=e.response.status_code,
        )
        raise ProxyError(
            message="Polymarket CLOB API request failed",
            upstream_status=e.response.status_code,
            api="clob",
            endpoint="/prices-history",
        )

    # Transform response
    history = [
        PricePoint(timestamp=point["t"], price=point["p"])
        for point in data.get("history", [])
    ]

    return PriceHistoryResponse(
        token_id=token_id,
        interval=interval.value if interval else None,
        fidelity=fidelity,
        start_ts=start_ts,
        end_ts=end_ts,
        history=history,
        cache_status=cache_status,
    )


# Order book cache TTL - very short since order book is volatile
ORDERBOOK_CACHE_TTL = 5  # 5 seconds


@router.get(
    "/markets/{token_id}/orderbook",
    response_model=OrderBookResponse,
    summary="Get L2 order book for a token",
    description=(
        "Get the current order book (L2) for a Polymarket CLOB token. "
        "Returns bid and ask levels with aggregated sizes. "
        "Order book data is volatile so cache TTL is short (5s)."
    ),
    responses={
        404: {
            "description": "Token not found or no order book exists",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "No orderbook exists for the requested token id",
                        "code": "NOT_FOUND",
                        "status": 404,
                    }
                }
            },
        },
        502: {
            "description": "Upstream Polymarket API error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Polymarket API request failed",
                        "code": "PROXY_ERROR",
                        "status": 502,
                    }
                }
            },
        },
        503: {
            "description": "Circuit breaker open",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Circuit breaker open for clob API",
                        "code": "SERVICE_UNAVAILABLE",
                        "retry_after": 30,
                    }
                }
            },
        },
    },
)
@limiter.limit(CLOB_PROXY_RATE_LIMIT)
async def get_orderbook(
    request: Request,
    token_id: str,
    client: ProxyClient,
    depth: int | None = Query(
        None,
        ge=1,
        le=100,
        description="Maximum number of bid/ask levels to return. Default returns all levels.",
    ),
) -> OrderBookResponse:
    """Get the L2 order book for a token.

    Proxies to Polymarket CLOB `/book` endpoint with caching.

    The order book shows current bids (buy orders) and asks (sell orders)
    aggregated by price level. Use the `depth` parameter to limit the
    number of levels returned (useful for reducing payload size).

    **Response includes computed fields:**
    - `spread`: Difference between best ask and best bid
    - `mid_price`: Average of best bid and best ask
    - `best_bid`, `best_ask`: Top-of-book prices

    **Cache TTL:** 5 seconds (order book is highly volatile)
    """
    params: dict[str, str] = {"token_id": token_id}

    try:
        data, cache_status = await client.get_clob(
            "/book",
            params,
            cache_ttl=ORDERBOOK_CACHE_TTL,
        )
    except (CircuitOpenError, UpstreamRateLimitError) as e:
        logger.warning(
            "Orderbook proxy error",
            token_id=token_id,
            error_type=type(e).__name__,
        )
        raise
    except ProxyError as e:
        logger.error(
            "Orderbook proxy upstream failure",
            token_id=token_id,
            error=str(e),
        )
        raise
    except httpx.HTTPStatusError as e:
        # Handle 404 from upstream
        if e.response.status_code == 404:
            raise UpstreamNotFoundError(
                message="No orderbook exists for the requested token id",
                resource_type="orderbook",
                resource_id=token_id,
            )
        logger.error(
            "Orderbook proxy HTTP error",
            token_id=token_id,
            status_code=e.response.status_code,
        )
        raise ProxyError(
            message="Polymarket CLOB API request failed",
            upstream_status=e.response.status_code,
            api="clob",
            endpoint="/book",
        )

    # Transform bids and asks
    bids = [OrderLevel(price=b["price"], size=b["size"]) for b in data.get("bids", [])]
    asks = [OrderLevel(price=a["price"], size=a["size"]) for a in data.get("asks", [])]

    # Apply depth limit if specified
    if depth is not None:
        bids = bids[:depth]
        asks = asks[:depth]

    # Compute derived fields
    best_bid: str | None = None
    best_ask: str | None = None
    spread: str | None = None
    mid_price: str | None = None

    if bids:
        best_bid = bids[0].price
    if asks:
        best_ask = asks[0].price

    if best_bid is not None and best_ask is not None:
        bid_val = float(best_bid)
        ask_val = float(best_ask)
        spread = f"{ask_val - bid_val:.6f}".rstrip("0").rstrip(".")
        mid_price = f"{(bid_val + ask_val) / 2:.6f}".rstrip("0").rstrip(".")

    return OrderBookResponse(
        token_id=token_id,
        market=data.get("market", ""),
        timestamp=data.get("timestamp", ""),
        bids=bids,
        asks=asks,
        spread=spread,
        mid_price=mid_price,
        best_bid=best_bid,
        best_ask=best_ask,
        tick_size=data.get("tick_size", "0.01"),
        min_order_size=data.get("min_order_size", "0.001"),
        cache_status=cache_status,
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
        raise UpstreamNotFoundError(
            message="No token mappings found for market",
            resource_type="market_tokens",
            resource_id=market_id,
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


# Trades cache TTL - moderate since trades update frequently but not as volatile as orderbook
TRADES_CACHE_TTL = 30  # 30 seconds


class TradeSide(str, Enum):
    """Valid trade side filter values."""

    BUY = "BUY"
    SELL = "SELL"


@router.get(
    "/markets/{condition_id}/trades",
    response_model=RecentTradesResponse,
    summary="Get recent trades for a market",
    description=(
        "Get recent trades for a Polymarket market by condition ID. "
        "Useful for activity feeds and trade history. "
        "Results are cached for 30 seconds."
    ),
    responses={
        502: {
            "description": "Upstream Polymarket API error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Polymarket API request failed",
                        "code": "PROXY_ERROR",
                        "status": 502,
                    }
                }
            },
        },
        503: {
            "description": "Circuit breaker open",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Circuit breaker open for data API",
                        "code": "SERVICE_UNAVAILABLE",
                        "retry_after": 30,
                    }
                }
            },
        },
    },
)
@limiter.limit(CLOB_PROXY_RATE_LIMIT)
async def get_trades(
    request: Request,
    condition_id: str,
    client: ProxyClient,
    limit: int = Query(
        50,
        ge=1,
        le=100,
        description="Maximum number of trades to return (1-100).",
    ),
    side: TradeSide | None = Query(
        None,
        description="Filter by trade side (BUY or SELL).",
    ),
    maker: str | None = Query(
        None,
        description="Filter by maker wallet address.",
    ),
) -> RecentTradesResponse:
    """Get recent trades for a market.

    Proxies to Polymarket Data API `/trades` endpoint with caching.

    Returns trades for the specified market condition ID, sorted by
    timestamp descending (most recent first).

    **Query parameters:**
    - `limit`: Maximum trades to return (default 50, max 100)
    - `side`: Filter by BUY or SELL
    - `maker`: Filter by specific maker wallet address

    **Cache TTL:** 30 seconds
    """
    # Build query params for upstream
    params: dict[str, str | int] = {
        "market": condition_id,
        "limit": limit,
    }

    if side is not None:
        params["side"] = side.value
    if maker is not None:
        params["user"] = maker

    try:
        data, cache_status = await client.get_data(
            "/trades",
            params,
            cache_ttl=TRADES_CACHE_TTL,
        )
    except (CircuitOpenError, UpstreamRateLimitError) as e:
        logger.warning(
            "Trades proxy error",
            condition_id=condition_id,
            error_type=type(e).__name__,
        )
        raise
    except ProxyError as e:
        logger.error(
            "Trades proxy upstream failure",
            condition_id=condition_id,
            error=str(e),
        )
        raise
    except httpx.HTTPStatusError as e:
        logger.error(
            "Trades proxy HTTP error",
            condition_id=condition_id,
            status_code=e.response.status_code,
        )
        raise ProxyError(
            message="Polymarket Data API request failed",
            upstream_status=e.response.status_code,
            api="data",
            endpoint="/trades",
        )

    # Data API returns an array directly
    trades_data: list[dict[str, Any]] = data if isinstance(data, list) else []

    # Transform response
    trades: list[Trade] = []
    for t in trades_data:
        trade = Trade(
            id=str(t.get("transactionHash", "")),
            price=str(t.get("price", "0")),
            size=str(t.get("size", "0")),
            side=str(t.get("side", "BUY")),
            timestamp=int(t.get("timestamp", 0)),
            maker_address=str(t["proxyWallet"]) if t.get("proxyWallet") else None,
            outcome=str(t["outcome"]) if t.get("outcome") else None,
            outcome_index=int(t["outcomeIndex"]) if t.get("outcomeIndex") is not None else None,
        )
        trades.append(trade)

    return RecentTradesResponse(
        token_id=condition_id,
        trades=trades,
        count=len(trades),
        has_more=len(trades) >= limit,
        cache_status=cache_status,
    )
