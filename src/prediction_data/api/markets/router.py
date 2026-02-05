"""Markets API routes."""

from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from prediction_data.api.clickhouse import get_clickhouse_client
from prediction_data.api.markets.schemas import (
    MarketListResponse,
    MarketResponse,
    PriceHistoryPoint,
    PriceHistoryResponse,
    TradeListResponse,
    TradeResponse,
)
from prediction_data.api.markets.service import (
    get_market_by_id,
    get_market_price_history,
    get_market_trades,
    get_markets,
)

router = APIRouter()


@router.get("", response_model=MarketListResponse)
async def list_markets(
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


@router.get("/{market_id}", response_model=MarketResponse)
async def get_market(
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
async def list_market_trades(
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
async def get_price_history(
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


# Future endpoints:
# - GET /markets/advanced (with CLOB data)
# - GET /markets/screener (time-based filtering)
