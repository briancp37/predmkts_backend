"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from prediction_data.api.auth.router import router as auth_router
from prediction_data.api.markets.router import router as markets_router
from prediction_data.db.session import create_tables


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    # Startup: create database tables
    await create_tables()
    yield
    # Shutdown: cleanup if needed


app = FastAPI(
    title="Prediction Markets API",
    description="REST API for prediction market data and user features",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware - allow all origins in development
# In production, restrict to your frontend domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(markets_router, prefix="/api/v1/markets", tags=["markets"])


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
