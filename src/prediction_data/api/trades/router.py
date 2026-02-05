"""Global trades API routes."""

from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends, Query

from prediction_data.api.clickhouse import get_clickhouse_client
from prediction_data.api.trades.schemas import (
    SmartTradeResponse,
    WhaleTradeResponse,
)
from prediction_data.api.trades.service import get_smart_trades, get_whale_trades

router = APIRouter()


@router.get("/smart", response_model=list[SmartTradeResponse])
async def list_smart_trades(
    minScore: float = Query(
        70.0, ge=0, le=100, description="Minimum smart score (0-100)"
    ),
    minAmount: float | None = Query(
        None, ge=0, description="Minimum USD value of trade"
    ),
    limit: int = Query(50, ge=1, le=200, description="Maximum results to return"),
    client: Client = Depends(get_clickhouse_client),
) -> list[SmartTradeResponse]:
    """Get recent trades from smart traders.

    Returns recent trades from traders with high smart scores (based on
    historical performance). Smart score is computed from PnL performance,
    with top traders scoring closer to 100.

    - **minScore**: Minimum smart score threshold (0-100, default 70)
    - **minAmount**: Optional minimum USD value filter
    - **limit**: Maximum number of trades to return (1-200, default 50)

    Each trade includes the trader's smart score in addition to trade details.
    """
    trades = await get_smart_trades(
        client,
        min_score=minScore,
        min_amount=minAmount,
        limit=limit,
    )

    return [SmartTradeResponse.model_validate(t) for t in trades]


@router.get("/whales", response_model=list[WhaleTradeResponse])
async def list_whale_trades(
    minAmount: float = Query(
        10000.0, ge=0, description="Minimum USD value of trade"
    ),
    limit: int = Query(50, ge=1, le=200, description="Maximum results to return"),
    client: Client = Depends(get_clickhouse_client),
) -> list[WhaleTradeResponse]:
    """Get recent large trades (whale trades).

    Returns recent trades with USD value at or above the minimum amount,
    ordered by timestamp descending (newest first).

    - **minAmount**: Minimum USD value threshold (default $10,000)
    - **limit**: Maximum number of trades to return (1-200, default 50)

    Each trade includes the trader's total portfolio value when available.
    """
    trades = await get_whale_trades(
        client,
        min_amount=minAmount,
        limit=limit,
    )

    return [WhaleTradeResponse.model_validate(t) for t in trades]
