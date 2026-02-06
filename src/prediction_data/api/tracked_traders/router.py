"""Tracked traders API routes."""

from typing import Annotated
from uuid import UUID

from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from prediction_data.api.clickhouse import get_clickhouse_client
from prediction_data.api.deps import get_current_user
from prediction_data.api.exceptions import DuplicateError, NotFoundError, TierLimitExceededError
from prediction_data.api.rate_limit import AUTHENTICATED_RATE_LIMIT, limiter
from prediction_data.api.traders.schemas import TradeResponse
from prediction_data.db.models.user import User
from prediction_data.db.session import get_db

from .schemas import (
    TrackedTraderActivity,
    TrackedTraderCreate,
    TrackedTraderResponse,
    TrackedTraderUpdate,
    TrackedTradersListResponse,
    TrackedTraderWithStats,
)
from .service import (
    add_tracked_trader,
    check_tier_limit,
    get_tier_limit,
    get_tracked_addresses,
    get_tracked_count,
    get_tracked_trader_activity,
    get_tracked_trader_by_address,
    get_tracked_trader_by_id,
    get_trader_stats,
    get_user_tracked_traders,
    remove_tracked_trader,
    update_tracked_trader,
)

router = APIRouter()

# Dependency type aliases
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
CHClient = Annotated[Client, Depends(get_clickhouse_client)]

# Common error response schemas for OpenAPI documentation
ERROR_400 = {"description": "Bad request - trader already tracked or invalid address"}
ERROR_401 = {"description": "Unauthorized - missing or invalid access token"}
ERROR_403 = {"description": "Forbidden - tier limit exceeded for tracked traders"}
ERROR_404 = {"description": "Not found - tracked trader not found"}
ERROR_422 = {"description": "Validation error - invalid wallet address format"}
ERROR_429 = {"description": "Rate limit exceeded - max 200 requests/minute"}


@router.get(
    "",
    response_model=TrackedTradersListResponse,
    responses={401: ERROR_401, 429: ERROR_429},
    summary="List tracked traders",
)
@limiter.limit(AUTHENTICATED_RATE_LIMIT)
async def get_tracked_traders(
    request: Request,
    db: DbSession,
    ch: CHClient,
    current_user: CurrentUser,
) -> TrackedTradersListResponse:
    """Get all tracked traders with stats.

    Returns tracked traders with 30-day PnL, recent trade count, and smart score.
    Also includes the user's tier limit (free: 5, pro: 50, enterprise: unlimited).

    **Rate limit:** 200 requests/minute per user.
    """
    tracked = await get_user_tracked_traders(db, current_user.id)
    tier_limit = get_tier_limit(current_user.tier)

    if not tracked:
        return TrackedTradersListResponse(items=[], count=0, limit=tier_limit)

    # Get addresses for stats lookup
    addresses = [t.trader_address for t in tracked]

    # Fetch stats from ClickHouse
    stats = await get_trader_stats(ch, addresses)

    # Build enriched response
    items: list[TrackedTraderWithStats] = []
    for t in tracked:
        trader_stats = stats.get(t.trader_address.lower(), {})
        items.append(
            TrackedTraderWithStats(
                id=t.id,
                traderAddress=t.trader_address,
                customName=t.custom_name,
                createdAt=t.created_at,
                totalPnl=trader_stats.get("totalPnl", 0.0),
                recentTrades=trader_stats.get("recentTrades", 0),
                smartScore=trader_stats.get("smartScore"),
            )
        )

    return TrackedTradersListResponse(items=items, count=len(items), limit=tier_limit)


@router.post(
    "",
    response_model=TrackedTraderResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: ERROR_400, 401: ERROR_401, 403: ERROR_403, 422: ERROR_422, 429: ERROR_429},
    summary="Add tracked trader",
)
@limiter.limit(AUTHENTICATED_RATE_LIMIT)
async def add_tracked(
    request: Request,
    body: TrackedTraderCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> TrackedTraderResponse:
    """Add a trader to the tracked list.

    The wallet address must be a valid Ethereum address (0x + 40 hex chars).
    Returns 403 if you've reached your tier limit (free: 5, pro: 50).
    Returns 400 if the trader is already in your tracked list.

    **Rate limit:** 200 requests/minute per user.
    """
    # Check tier limit
    current_count = await get_tracked_count(db, current_user.id)
    tier_limit = get_tier_limit(current_user.tier)

    if not check_tier_limit(current_user.tier, current_count):
        raise TierLimitExceededError(
            message=f"Tracked traders limit reached ({tier_limit}). Upgrade to PRO for more.",
            limit=tier_limit,
            count=current_count,
        )

    # Normalize address
    address = body.traderAddress.lower()

    # Check for duplicate
    existing = await get_tracked_trader_by_address(db, current_user.id, address)
    if existing:
        raise DuplicateError(message="Trader already in tracked list")

    # Add tracked trader
    tracker = await add_tracked_trader(
        db, current_user.id, address, body.customName
    )

    return TrackedTraderResponse(
        id=tracker.id,
        traderAddress=tracker.trader_address,
        customName=tracker.custom_name,
        createdAt=tracker.created_at,
    )


@router.get(
    "/activity",
    response_model=list[TrackedTraderActivity],
    responses={401: ERROR_401, 422: ERROR_422, 429: ERROR_429},
    summary="Get activity feed",
)
@limiter.limit(AUTHENTICATED_RATE_LIMIT)
async def get_activity(
    request: Request,
    db: DbSession,
    ch: CHClient,
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200, description="Maximum activities to return"),
    start_date: str | None = Query(
        default=None, alias="startDate", description="Filter from date (YYYY-MM-DD)"
    ),
    end_date: str | None = Query(
        default=None, alias="endDate", description="Filter to date (YYYY-MM-DD)"
    ),
) -> list[TrackedTraderActivity]:
    """Get the activity feed from all tracked traders.

    Returns recent trades from your tracked traders, ordered by timestamp (newest first).
    Includes trader info, trade details, and can be filtered by date range.

    **Rate limit:** 200 requests/minute per user.
    """
    # Get tracked addresses
    tracked = await get_user_tracked_traders(db, current_user.id)
    if not tracked:
        return []

    addresses = [t.trader_address for t in tracked]

    # Build address to tracker mapping
    tracker_by_address = {t.trader_address.lower(): t for t in tracked}

    # Get activity from ClickHouse
    activities = await get_tracked_trader_activity(
        ch, addresses, limit, start_date, end_date
    )

    # Build response
    result: list[TrackedTraderActivity] = []
    for activity in activities:
        addr = activity["trader_address"].lower()
        tracker = tracker_by_address.get(addr)
        if not tracker:
            continue

        trade = TradeResponse(
            id=str(activity.get("trade_id", "")),
            traderAddress=activity["trader_address"],
            marketId=activity.get("market_id", ""),
            marketQuestion=activity.get("market_question", ""),
            outcomeId=activity.get("outcome_id", ""),
            outcomeName=activity.get("outcome_name", ""),
            side=activity.get("side", "BUY"),
            price=float(activity.get("price", 0) or 0),
            quantity=float(activity.get("quantity", 0) or 0),
            usdValue=float(activity.get("usd_value", 0) or 0),
            fees=float(activity.get("fees", 0) or 0),
            realizedPnl=float(activity.get("realized_pnl") or 0)
            if activity.get("realized_pnl") is not None
            else None,
            timestamp=str(activity.get("timestamp", "")),
        )

        timestamp = activity.get("timestamp")
        if timestamp is None:
            continue

        result.append(
            TrackedTraderActivity(
                traderId=tracker.id,
                traderAddress=tracker.trader_address,
                customName=tracker.custom_name,
                trade=trade,
                timestamp=timestamp,
            )
        )

    return result


@router.get(
    "/{tracker_id}",
    response_model=TrackedTraderWithStats,
    responses={401: ERROR_401, 404: ERROR_404, 429: ERROR_429},
    summary="Get tracked trader",
)
@limiter.limit(AUTHENTICATED_RATE_LIMIT)
async def get_tracked_trader(
    request: Request,
    tracker_id: UUID,
    db: DbSession,
    ch: CHClient,
    current_user: CurrentUser,
) -> TrackedTraderWithStats:
    """Get a single tracked trader with detailed stats.

    Returns the tracked trader with 30-day PnL, recent trade count, and smart score.
    Returns 404 if not found or not owned by the authenticated user.

    **Rate limit:** 200 requests/minute per user.
    """
    tracker = await get_tracked_trader_by_id(db, current_user.id, tracker_id)

    if not tracker:
        raise NotFoundError(message="Tracked trader not found")

    # Get stats from ClickHouse
    stats = await get_trader_stats(ch, [tracker.trader_address])
    trader_stats = stats.get(tracker.trader_address.lower(), {})

    return TrackedTraderWithStats(
        id=tracker.id,
        traderAddress=tracker.trader_address,
        customName=tracker.custom_name,
        createdAt=tracker.created_at,
        totalPnl=trader_stats.get("totalPnl", 0.0),
        recentTrades=trader_stats.get("recentTrades", 0),
        smartScore=trader_stats.get("smartScore"),
    )


@router.delete(
    "/{tracker_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: ERROR_401, 404: ERROR_404, 429: ERROR_429},
    summary="Remove tracked trader",
)
@limiter.limit(AUTHENTICATED_RATE_LIMIT)
async def delete_tracked_trader(
    request: Request,
    tracker_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> Response:
    """Remove a trader from the tracked list.

    Returns 204 No Content on success. Returns 404 if the tracker
    is not found or not owned by the authenticated user.

    **Rate limit:** 200 requests/minute per user.
    """
    deleted = await remove_tracked_trader(db, current_user.id, tracker_id)

    if not deleted:
        raise NotFoundError(message="Tracked trader not found")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/{tracker_id}",
    response_model=TrackedTraderResponse,
    responses={401: ERROR_401, 404: ERROR_404, 422: ERROR_422, 429: ERROR_429},
    summary="Update tracked trader",
)
@limiter.limit(AUTHENTICATED_RATE_LIMIT)
async def patch_tracked_trader(
    request: Request,
    tracker_id: UUID,
    body: TrackedTraderUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> TrackedTraderResponse:
    """Update a tracked trader's custom name.

    Use this to set or update the custom display name for a tracked trader.
    Returns 404 if the tracker is not found or not owned by the authenticated user.

    **Rate limit:** 200 requests/minute per user.
    """
    tracker = await update_tracked_trader(
        db, current_user.id, tracker_id, body.customName
    )

    if not tracker:
        raise NotFoundError(message="Tracked trader not found")

    return TrackedTraderResponse(
        id=tracker.id,
        traderAddress=tracker.trader_address,
        customName=tracker.custom_name,
        createdAt=tracker.created_at,
    )
