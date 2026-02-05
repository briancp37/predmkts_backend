"""Traders API routes."""

from typing import Literal

from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from prediction_data.api.clickhouse import get_clickhouse_client
from prediction_data.api.traders.schemas import (
    TradeListResponse,
    TradeResponse,
    TraderDetailResponse,
    TraderListResponse,
    TraderResponse,
)
from prediction_data.api.traders.service import (
    get_trader_by_address,
    get_trader_trades,
    get_traders,
)

router = APIRouter()


@router.get("", response_model=TraderListResponse)
async def list_traders(
    search: str | None = Query(
        None, description="Search by wallet address prefix (case-insensitive)"
    ),
    sortBy: Literal["smartScore", "totalPnl", "totalTrades", "winRate"] = Query(
        "totalPnl", description="Field to sort by"
    ),
    sortOrder: Literal["asc", "desc"] = Query("desc", description="Sort direction"),
    limit: int = Query(50, ge=1, le=500, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    client: Client = Depends(get_clickhouse_client),
) -> TraderListResponse:
    """List traders with optional search and sorting.

    Returns a paginated list of traders with their aggregated PnL and trade statistics.
    Traders are joined with their historical PnL data from wallet_pnl_daily.

    - **search**: Search by wallet address prefix (case-insensitive ILIKE)
    - **sortBy**: Field to sort by (smartScore, totalPnl, totalTrades, winRate)
    - **sortOrder**: Sort direction (asc or desc, default desc)
    - **limit**: Maximum number of traders to return (1-500, default 50)
    - **offset**: Number of traders to skip for pagination
    """
    traders, total = await get_traders(
        client,
        search=search,
        sort_by=sortBy,
        sort_order=sortOrder,
        limit=limit,
        offset=offset,
    )

    # Convert dicts to TraderResponse models
    items = [TraderResponse.model_validate(t) for t in traders]

    # Calculate page number (1-indexed)
    page = (offset // limit) + 1 if limit > 0 else 1

    return TraderListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{address}", response_model=TraderDetailResponse)
async def get_trader(
    address: str = Path(
        ...,
        description="Wallet address (case-insensitive, normalized to lowercase)",
        min_length=10,
    ),
    client: Client = Depends(get_clickhouse_client),
) -> TraderDetailResponse:
    """Get detailed information about a specific trader.

    Returns trader metadata, current open positions with market details,
    and aggregated PnL statistics.

    - **address**: Wallet address (normalized to lowercase)

    Positions include:
    - Market question and outcome name
    - Quantity held and average cost
    - Current price from latest market marks
    - Unrealized PnL based on current price vs avg cost

    Returns 404 if the trader is not found.
    """
    trader = await get_trader_by_address(client, address)

    if trader is None:
        raise HTTPException(
            status_code=404,
            detail=f"Trader with address '{address}' not found",
        )

    return TraderDetailResponse.model_validate(trader)


@router.get("/{address}/trades", response_model=TradeListResponse)
async def list_trader_trades(
    address: str = Path(
        ...,
        description="Wallet address (case-insensitive, normalized to lowercase)",
        min_length=10,
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    startDate: str | None = Query(
        None, description="Filter trades on or after this date (YYYY-MM-DD)"
    ),
    endDate: str | None = Query(
        None, description="Filter trades on or before this date (YYYY-MM-DD)"
    ),
    marketId: str | None = Query(None, description="Filter to a specific market"),
    client: Client = Depends(get_clickhouse_client),
) -> TradeListResponse:
    """Get trades for a specific trader.

    Returns a paginated list of trades from the trader's transaction history,
    ordered by timestamp descending (newest first).

    - **address**: Wallet address (normalized to lowercase)
    - **limit**: Maximum number of trades to return (1-1000, default 100)
    - **offset**: Number of trades to skip for pagination
    - **startDate**: Filter trades on or after this date (YYYY-MM-DD)
    - **endDate**: Filter trades on or before this date (YYYY-MM-DD)
    - **marketId**: Filter to trades in a specific market

    Each trade includes:
    - Market question and outcome name
    - Side (BUY/SELL), price, quantity, USD value
    - Fees and realized PnL (if position was closed)
    """
    trades, total = await get_trader_trades(
        client,
        address,
        limit=limit,
        offset=offset,
        start_date=startDate,
        end_date=endDate,
        market_id=marketId,
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


# Future endpoints:
# - GET /traders/smart-scores (smart trader rankings)
