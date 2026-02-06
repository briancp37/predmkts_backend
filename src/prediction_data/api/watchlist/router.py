"""Watchlist API routes."""

from typing import Annotated

from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from prediction_data.api.clickhouse import get_clickhouse_client
from prediction_data.api.deps import get_current_user
from prediction_data.api.exceptions import DuplicateError, NotFoundError, ValidationError
from prediction_data.api.rate_limit import limiter, AUTHENTICATED_RATE_LIMIT
from prediction_data.db.models.user import User
from prediction_data.db.session import get_db

from .schemas import (
    WatchlistAddRequest,
    WatchlistItem,
    WatchlistItemWithMarket,
    WatchlistResponse,
)
from .service import (
    add_to_watchlist,
    get_market_details,
    get_user_watchlist,
    is_in_watchlist,
    market_exists,
    remove_from_watchlist,
)

router = APIRouter()

# Dependency type aliases
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
CHClient = Annotated[Client, Depends(get_clickhouse_client)]


@router.get("", response_model=WatchlistResponse)
@limiter.limit(AUTHENTICATED_RATE_LIMIT)
async def get_watchlist(
    request: Request,
    db: DbSession,
    ch: CHClient,
    current_user: CurrentUser,
) -> WatchlistResponse:
    """Get user's watchlist with market details.

    Returns all markets in the user's watchlist, enriched with current
    market information including price and 24h change.
    """
    watchlist_items = await get_user_watchlist(db, current_user.id)

    if not watchlist_items:
        return WatchlistResponse(items=[], count=0)

    # Get market IDs for enrichment
    market_ids = [item.market_id for item in watchlist_items]

    # Fetch market details from ClickHouse
    market_details = await get_market_details(ch, market_ids)

    # Build enriched response
    items: list[WatchlistItemWithMarket] = []
    for item in watchlist_items:
        details = market_details.get(item.market_id, {})
        items.append(
            WatchlistItemWithMarket(
                id=item.id,
                marketId=item.market_id,
                createdAt=item.created_at,
                marketQuestion=details.get("marketQuestion", ""),
                marketCategory=details.get("marketCategory"),
                currentPrice=details.get("currentPrice", 0.5),
                priceChange24h=details.get("priceChange24h", 0.0),
                resolved=details.get("resolved", False),
            )
        )

    return WatchlistResponse(items=items, count=len(items))


@router.post("", response_model=WatchlistItem, status_code=status.HTTP_201_CREATED)
@limiter.limit(AUTHENTICATED_RATE_LIMIT)
async def add_market_to_watchlist(
    request: Request,
    body: WatchlistAddRequest,
    db: DbSession,
    ch: CHClient,
    current_user: CurrentUser,
) -> WatchlistItem:
    """Add a market to user's watchlist.

    Returns the created watchlist item. Returns 400 if already in watchlist.
    """
    # Validate market exists in ClickHouse
    if not await market_exists(ch, body.marketId):
        raise ValidationError(message="Market not found")

    # Check if already in watchlist
    if await is_in_watchlist(db, current_user.id, body.marketId):
        raise DuplicateError(message="Market already in watchlist")

    # Add to watchlist
    watchlist = await add_to_watchlist(db, current_user.id, body.marketId)

    return WatchlistItem(
        id=watchlist.id,
        marketId=watchlist.market_id,
        createdAt=watchlist.created_at,
    )


@router.delete("/{market_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(AUTHENTICATED_RATE_LIMIT)
async def remove_market_from_watchlist(
    request: Request,
    market_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> Response:
    """Remove a market from user's watchlist.

    Returns 204 No Content on success, 404 if not in watchlist.
    """
    deleted = await remove_from_watchlist(db, current_user.id, market_id)

    if not deleted:
        raise NotFoundError(message="Market not found in watchlist")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
