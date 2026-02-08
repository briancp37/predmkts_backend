"""Markets API routes."""

from typing import Literal

from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from prediction_data.api.clickhouse import get_clickhouse_client
from prediction_data.api.clob_client import ClobApiClient, get_clob_client
from prediction_data.api.markets.schemas import (
    MarketAdvancedListResponse,
    MarketAdvancedResponse,
    MarketListResponse,
    MarketResponse,
    PriceHistoryPoint,
    PriceHistoryResponse,
    TagResponse,
    TradeListResponse,
    TradeResponse,
)
from prediction_data.api.markets.service import (
    get_market_by_id,
    get_market_price_history,
    get_market_trades,
    get_markets,
    get_markets_advanced,
    get_markets_screener,
    get_tags,
)
from prediction_data.api.rate_limit import limiter, PUBLIC_RATE_LIMIT, CLOB_PROXY_RATE_LIMIT

router = APIRouter()


@router.get("", response_model=MarketListResponse)
@limiter.limit(PUBLIC_RATE_LIMIT)
async def list_markets(
    request: Request,
    category: str | None = Query(None, description="Filter by category (exact match)"),
    search: str | None = Query(None, description="Search in question and description"),
    resolved: bool | None = Query(None, description="Filter by resolved status"),
    limit: int = Query(50, ge=1, le=500, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    client: Client = Depends(get_clickhouse_client),
) -> MarketListResponse:
    """List markets with optional filtering and pagination.

    Returns a paginated list of markets with their outcomes. Markets are ordered
    by last update time (most recent first).

    - **category**: Filter by event category (exact match)
    - **search**: Search text in market question and description (case-insensitive)
    - **resolved**: Filter by resolved status (true/false)
    - **limit**: Maximum number of markets to return (1-500, default 50)
    - **offset**: Number of markets to skip for pagination
    """
    markets, total = await get_markets(
        client,
        category=category,
        search=search,
        resolved=resolved,
        limit=limit,
        offset=offset,
    )

    # Convert dicts to MarketResponse models
    items = [MarketResponse.model_validate(m) for m in markets]

    # Calculate page number (1-indexed)
    page = (offset // limit) + 1 if limit > 0 else 1

    return MarketListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/advanced", response_model=MarketAdvancedListResponse)
@limiter.limit(CLOB_PROXY_RATE_LIMIT)
async def list_markets_advanced(
    request: Request,
    category: str | None = Query(None, description="Filter by category (exact match)"),
    excludeCategories: str | None = Query(
        None,
        description="Comma-separated categories to exclude (e.g., 'Sports,Crypto')",
    ),
    search: str | None = Query(None, description="Search in question and description"),
    resolved: bool | None = Query(
        False,
        description="Filter by resolved status. Defaults to false to exclude resolved/expired markets.",
    ),
    activeOnly: bool = Query(
        False,
        description="Only show markets with recent trading activity. "
        "Defaults to false to show all non-resolved markets.",
    ),
    sortBy: Literal["volume", "liquidity", "spread", "priceChange"] = Query(
        "volume", description="Sort field"
    ),
    sortOrder: Literal["asc", "desc"] = Query("desc", description="Sort direction"),
    minVolume: float | None = Query(None, description="Minimum 24h volume in USD"),
    maxVolume: float | None = Query(None, description="Maximum 24h volume in USD"),
    minLiquidity: float | None = Query(None, description="Minimum liquidity"),
    maxLiquidity: float | None = Query(None, description="Maximum liquidity"),
    minSpread: float | None = Query(None, description="Minimum spread in cents"),
    maxSpread: float | None = Query(None, description="Maximum spread in cents"),
    minChange: float | None = Query(None, description="Minimum 24h price change"),
    maxChange: float | None = Query(None, description="Maximum 24h price change"),
    includeTags: str | None = Query(
        None,
        description="Comma-separated tags to include (e.g., 'Sports,Politics'). "
        "Markets must belong to events with at least one of these tags.",
    ),
    excludeTags: str | None = Query(
        None,
        description="Comma-separated tags to exclude (e.g., 'Crypto,NFT'). "
        "Markets will be excluded if their event has any of these tags.",
    ),
    limit: int = Query(50, ge=1, le=500, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    page: int | None = Query(None, ge=1, description="Page number (alternative to offset)"),
    client: Client = Depends(get_clickhouse_client),
    clob_client: ClobApiClient = Depends(get_clob_client),
) -> MarketAdvancedListResponse:
    """List markets with real-time CLOB bid/ask data.

    Returns a paginated list of markets enriched with order book data from
    the Polymarket CLOB API. This endpoint is suitable for advanced filtering
    and screening use cases.

    **Sort options:**
    - `volume`: Sort by 24-hour trading volume (default)
    - `liquidity`: Sort by estimated liquidity
    - `spread`: Sort by bid-ask spread
    - `priceChange`: Sort by 24-hour price change magnitude

    **Advanced filters:**
    - Volume range filters (minVolume, maxVolume)
    - Liquidity range filters (minLiquidity, maxLiquidity)
    - Spread range filters in cents (minSpread, maxSpread)
    - Price change filters (minChange, maxChange)

    **CLOB data fields:**
    - `bid`: Best bid price (0-1)
    - `ask`: Best ask price (0-1)
    - `spread`: Absolute spread (ask - bid)
    - `spreadPercent`: Spread as percentage of midpoint
    - `spreadCents`: Spread in cents
    - `volume24h`: 24-hour trading volume in USD
    - `priceChange24h`: 24-hour price change

    Note: CLOB data is cached for 30 seconds to reduce API calls.
    """
    # Handle page-based pagination
    effective_offset = offset
    if page is not None:
        effective_offset = (page - 1) * limit

    # Parse include tags if provided
    include_tag_list: list[str] | None = None
    if includeTags:
        include_tag_list = [t.strip() for t in includeTags.split(",") if t.strip()]

    # Parse exclude tags if provided
    exclude_tag_list: list[str] | None = None
    if excludeTags:
        exclude_tag_list = [t.strip() for t in excludeTags.split(",") if t.strip()]

    # Parse exclude categories if provided
    exclude_category_list: list[str] | None = None
    if excludeCategories:
        exclude_category_list = [c.strip() for c in excludeCategories.split(",") if c.strip()]

    markets, total = await get_markets_advanced(
        client,
        clob_client,
        category=category,
        exclude_categories=exclude_category_list,
        search=search,
        resolved=resolved,
        active_only=activeOnly,
        sort_by=sortBy,
        sort_order=sortOrder,
        min_volume=minVolume,
        max_volume=maxVolume,
        min_liquidity=minLiquidity,
        max_liquidity=maxLiquidity,
        min_spread=minSpread,
        max_spread=maxSpread,
        min_change=minChange,
        max_change=maxChange,
        include_tags=include_tag_list,
        exclude_tags=exclude_tag_list,
        limit=limit,
        offset=effective_offset,
    )

    # Convert dicts to MarketAdvancedResponse models
    items = [MarketAdvancedResponse.model_validate(m) for m in markets]

    # Calculate page number (1-indexed)
    current_page = (effective_offset // limit) + 1 if limit > 0 else 1

    return MarketAdvancedListResponse(
        items=items,
        total=total,
        page=current_page,
        limit=limit,
    )


@router.get("/screener", response_model=MarketAdvancedListResponse)
@limiter.limit(PUBLIC_RATE_LIMIT)
async def list_markets_screener(
    request: Request,
    timeWindow: Literal["6h", "12h", "24h", "7d"] = Query(
        "24h", description="Time window for volume and price change calculations"
    ),
    category: str | None = Query(None, description="Filter by category (exact match)"),
    search: str | None = Query(None, description="Search in question and description"),
    resolved: bool | None = Query(None, description="Filter by resolved status"),
    sortBy: Literal["volume", "priceChange"] = Query(
        "volume", description="Sort field (volume or priceChange)"
    ),
    sortOrder: Literal["asc", "desc"] = Query("desc", description="Sort direction"),
    minVolume: float | None = Query(
        None, description="Minimum volume in USD over the time window"
    ),
    maxVolume: float | None = Query(
        None, description="Maximum volume in USD over the time window"
    ),
    minPriceChange: float | None = Query(
        None, description="Minimum price change (e.g., -0.1 for -10%)"
    ),
    maxPriceChange: float | None = Query(
        None, description="Maximum price change (e.g., 0.1 for +10%)"
    ),
    limit: int = Query(50, ge=1, le=500, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    client: Client = Depends(get_clickhouse_client),
) -> MarketAdvancedListResponse:
    """Market screener with time-based filtering.

    Returns markets with aggregated price change and volume metrics calculated
    over a specified time window. This endpoint is optimized for screening
    markets based on recent performance.

    **Time windows:**
    - `6h`: Last 6 hours (uses daily data - hourly not yet available)
    - `12h`: Last 12 hours (uses daily data - hourly not yet available)
    - `24h`: Last 24 hours
    - `7d`: Last 7 days

    **Sort options:**
    - `volume`: Sort by trading volume over the time window
    - `priceChange`: Sort by absolute price change magnitude

    **Filters:**
    - Volume range filters (minVolume, maxVolume)
    - Price change filters as decimals (minPriceChange, maxPriceChange)
      - Use -0.1 for -10% and 0.1 for +10%

    **Response fields:**
    - `volume24h`: Volume over the selected time window (not necessarily 24h)
    - `priceChange24h`: Price change over the selected time window

    Note: Sub-daily time windows (6h, 12h) currently return daily data
    since hourly price marks are not yet available. This will be enhanced
    when hourly data is computed from Silver trades.
    """
    markets, total = await get_markets_screener(
        client,
        time_window=timeWindow,
        category=category,
        search=search,
        resolved=resolved,
        sort_by=sortBy,
        sort_order=sortOrder,
        min_volume=minVolume,
        max_volume=maxVolume,
        min_price_change=minPriceChange,
        max_price_change=maxPriceChange,
        limit=limit,
        offset=offset,
    )

    # Convert dicts to MarketAdvancedResponse models
    items = [MarketAdvancedResponse.model_validate(m) for m in markets]

    # Calculate page number (1-indexed)
    page = (offset // limit) + 1 if limit > 0 else 1

    return MarketAdvancedListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/tags", response_model=list[TagResponse])
@limiter.limit(PUBLIC_RATE_LIMIT)
async def list_tags(
    request: Request,
    client: Client = Depends(get_clickhouse_client),
) -> list[TagResponse]:
    """List all available tags (categories) for filtering markets.

    Returns a list of categories with their market counts, ordered by the number
    of markets in each category (highest first). These can be used to populate
    filter dropdowns in the frontend.

    **Response fields:**
    - `id`: Unique identifier for the tag (slug-based)
    - `name`: Display name of the category
    - `slug`: URL-friendly version of the name
    - `marketCount`: Number of markets in this category
    """
    tags = await get_tags(client)
    return [TagResponse.model_validate(t) for t in tags]


@router.get("/{market_id}", response_model=MarketResponse)
@limiter.limit(PUBLIC_RATE_LIMIT)
async def get_market(
    request: Request,
    market_id: str = Path(
        ...,
        description="Market identifier (can be internal ID, polymarketId, or slug)",
    ),
    client: Client = Depends(get_clickhouse_client),
) -> MarketResponse:
    """Get a single market by ID.

    The market_id can be any of:
    - Internal market ID (platform_market_id)
    - Polymarket ID (same as platform_market_id for Polymarket markets)
    - Market slug (URL-friendly identifier)

    Returns the market with all its outcome details.
    """
    market = await get_market_by_id(client, market_id)

    if market is None:
        raise HTTPException(status_code=404, detail=f"Market not found: {market_id}")

    return MarketResponse.model_validate(market)


@router.get("/{market_id}/trades", response_model=TradeListResponse)
@limiter.limit(PUBLIC_RATE_LIMIT)
async def list_market_trades(
    request: Request,
    market_id: str = Path(
        ...,
        description="Market identifier (can be internal ID, polymarketId, or slug)",
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    startDate: str | None = Query(
        None,
        description="Filter trades after this date (YYYY-MM-DD format)",
        alias="startDate",
    ),
    endDate: str | None = Query(
        None,
        description="Filter trades before this date (YYYY-MM-DD format)",
        alias="endDate",
    ),
    client: Client = Depends(get_clickhouse_client),
) -> TradeListResponse:
    """Get trades for a specific market.

    Returns a paginated list of trades for the specified market. Trades are
    ordered by timestamp (most recent first).

    The market_id can be any of:
    - Internal market ID (platform_market_id)
    - Polymarket ID (same as platform_market_id for Polymarket markets)
    - Market slug (URL-friendly identifier)

    - **limit**: Maximum number of trades to return (1-1000, default 100)
    - **offset**: Number of trades to skip for pagination
    - **startDate**: Filter trades after this date (inclusive)
    - **endDate**: Filter trades before this date (inclusive)
    """
    # First verify the market exists and resolve its ID
    market = await get_market_by_id(client, market_id)
    if market is None:
        raise HTTPException(status_code=404, detail=f"Market not found: {market_id}")

    # Use the resolved market ID for querying trades
    resolved_market_id = market["id"]

    trades, total = await get_market_trades(
        client,
        resolved_market_id,
        limit=limit,
        offset=offset,
        start_date=startDate,
        end_date=endDate,
    )

    # Convert dicts to TradeResponse models
    items = [TradeResponse.model_validate(t) for t in trades]

    # Calculate page number (1-indexed)
    page = (offset // limit) + 1 if limit > 0 else 1

    return TradeListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{market_id}/price-history", response_model=PriceHistoryResponse)
@limiter.limit(PUBLIC_RATE_LIMIT)
async def get_price_history(
    request: Request,
    market_id: str = Path(
        ...,
        description="Market identifier (can be internal ID, polymarketId, or slug)",
    ),
    interval: str = Query(
        "1d",
        description="Time interval for aggregation. Supported: 1h, 4h, 1d, 1w. "
        "Note: Currently only daily data is available, so 1h/4h return daily granularity.",
        pattern="^(1h|4h|1d|1w)$",
    ),
    startDate: str | None = Query(
        None,
        description="Start date filter (YYYY-MM-DD format)",
        alias="startDate",
    ),
    endDate: str | None = Query(
        None,
        description="End date filter (YYYY-MM-DD format)",
        alias="endDate",
    ),
    outcomeId: str | None = Query(
        None,
        description="Specific outcome ID. Defaults to YES outcome if not specified.",
        alias="outcomeId",
    ),
    client: Client = Depends(get_clickhouse_client),
) -> PriceHistoryResponse:
    """Get price history for a market.

    Returns historical price data for charting. Data points are returned in
    chronological order (oldest first).

    The market_id can be any of:
    - Internal market ID (platform_market_id)
    - Polymarket ID (same as platform_market_id for Polymarket markets)
    - Market slug (URL-friendly identifier)

    **Interval support:**
    - `1d`: Daily price points (recommended)
    - `1w`: Weekly aggregated price points
    - `1h`, `4h`: Currently return daily data (hourly data not yet available)

    **Response fields:**
    - `timestamp`: ISO date string
    - `price`: Mark price (VWAP or last trade price)
    - `volume`: Trading volume in USD for the period
    """
    # First verify the market exists and resolve its ID
    market = await get_market_by_id(client, market_id)
    if market is None:
        raise HTTPException(status_code=404, detail=f"Market not found: {market_id}")

    # Use the resolved market ID for querying price history
    resolved_market_id = market["id"]

    price_history = await get_market_price_history(
        client,
        resolved_market_id,
        interval=interval,
        start_date=startDate,
        end_date=endDate,
        outcome_id=outcomeId,
    )

    # Convert to PriceHistoryPoint models
    items = [PriceHistoryPoint.model_validate(p) for p in price_history]

    # Determine which outcome was used (for response metadata)
    used_outcome_id = outcomeId
    if not used_outcome_id and price_history:
        # If we auto-selected an outcome, we don't track it in the response
        # The caller can deduce it from the data or specify explicitly
        pass

    return PriceHistoryResponse(
        items=items,
        marketId=resolved_market_id,
        outcomeId=used_outcome_id,
        interval=interval,
        startDate=startDate,
        endDate=endDate,
    )


# All market endpoints implemented:
# - GET /markets (list with basic filtering)
# - GET /markets/advanced (with CLOB bid/ask data)
# - GET /markets/screener (time-based filtering)
# - GET /markets/{id} (single market)
# - GET /markets/{id}/trades (market trades)
# - GET /markets/{id}/price-history (price history for charting)
