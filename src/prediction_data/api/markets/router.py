"""Markets API routes."""

from fastapi import APIRouter

router = APIRouter()


# Endpoints will be added in subsequent features:
# - GET /markets (basic market listing)
# - GET /markets/advanced (with CLOB data)
# - GET /markets/screener (time-based filtering)
# - GET /markets/{id} (single market detail)
# - GET /markets/{id}/trades (market trades)
# - GET /markets/{id}/price-history (price history for charting)
