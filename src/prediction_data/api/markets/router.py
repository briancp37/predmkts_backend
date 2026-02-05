"""Markets API routes."""

from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from prediction_data.api.clickhouse import get_clickhouse_client
from prediction_data.api.markets.schemas import MarketListResponse, MarketResponse
from prediction_data.api.markets.service import get_market_by_id, get_markets

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


# Future endpoints:
# - GET /markets/advanced (with CLOB data)
# - GET /markets/screener (time-based filtering)
# - GET /markets/{id}/trades (market trades)
# - GET /markets/{id}/price-history (price history for charting)
