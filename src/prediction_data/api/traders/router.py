"""Traders API routes."""

from typing import Literal

from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends, Query

from prediction_data.api.clickhouse import get_clickhouse_client
from prediction_data.api.traders.schemas import TraderListResponse, TraderResponse
from prediction_data.api.traders.service import get_traders

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


# Future endpoints:
# - GET /traders/smart-scores (smart trader rankings)
# - GET /traders/{address} (single trader detail with positions)
# - GET /traders/{address}/trades (trades for a specific trader)
