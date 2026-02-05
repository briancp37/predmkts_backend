"""Traders API routes."""

from fastapi import APIRouter

router = APIRouter()


# Endpoints will be added in subsequent features:
# - GET /traders (list traders with search and sorting)
# - GET /traders/smart-scores (smart trader rankings)
# - GET /traders/{address} (single trader detail with positions)
# - GET /traders/{address}/trades (trades for a specific trader)
