"""Health check endpoints for API monitoring and k8s probes.

Provides:
- GET /health - Comprehensive health check with dependency status
- GET /health/ready - Readiness probe for k8s (all dependencies must be healthy)
- GET /health/live - Liveness probe for k8s (app is running)
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from prediction_data.api.clickhouse import get_clickhouse_client, ping as clickhouse_ping
from prediction_data.db.session import async_session_factory

router = APIRouter(tags=["health"])

# API version - should match main.py FastAPI version
API_VERSION = "0.1.0"


class HealthStatus(str, Enum):
    """Overall health status values."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class DependencyStatus(str, Enum):
    """Individual dependency status values."""

    UP = "up"
    DOWN = "down"


class DependencyHealth(BaseModel):
    """Health status for a single dependency."""

    status: DependencyStatus
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Full health check response."""

    status: HealthStatus
    version: str
    dependencies: dict[str, DependencyHealth]


async def check_postgres() -> DependencyHealth:
    """Check PostgreSQL database connection.

    Returns:
        DependencyHealth with status and latency.
    """
    import time

    start = time.perf_counter()
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start) * 1000
        return DependencyHealth(status=DependencyStatus.UP, latency_ms=round(latency, 2))
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return DependencyHealth(
            status=DependencyStatus.DOWN,
            latency_ms=round(latency, 2),
            error=str(e),
        )


async def check_clickhouse() -> DependencyHealth:
    """Check ClickHouse database connection.

    Returns:
        DependencyHealth with status and latency.
    """
    import time

    start = time.perf_counter()
    try:
        is_up = await clickhouse_ping()
        latency = (time.perf_counter() - start) * 1000
        if is_up:
            return DependencyHealth(status=DependencyStatus.UP, latency_ms=round(latency, 2))
        else:
            return DependencyHealth(
                status=DependencyStatus.DOWN,
                latency_ms=round(latency, 2),
                error="ping returned false",
            )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return DependencyHealth(
            status=DependencyStatus.DOWN,
            latency_ms=round(latency, 2),
            error=str(e),
        )


def compute_overall_status(dependencies: dict[str, DependencyHealth]) -> HealthStatus:
    """Compute overall health status from dependencies.

    Args:
        dependencies: Map of dependency name to health status.

    Returns:
        HEALTHY if all up, DEGRADED if some down, UNHEALTHY if critical deps down.
    """
    # Critical dependencies - if these are down, service is unhealthy
    critical_deps = {"postgres"}

    all_up = True
    critical_down = False

    for name, health in dependencies.items():
        if health.status == DependencyStatus.DOWN:
            all_up = False
            if name in critical_deps:
                critical_down = True

    if critical_down:
        return HealthStatus.UNHEALTHY
    elif not all_up:
        return HealthStatus.DEGRADED
    else:
        return HealthStatus.HEALTHY


@router.get(
    "",
    response_model=HealthResponse,
    summary="Comprehensive health check",
    description="Check health of API and all dependencies. Returns status for each dependency.",
)
async def health_check() -> JSONResponse:
    """Comprehensive health check endpoint.

    Checks all dependencies (PostgreSQL, ClickHouse) and returns their status.
    Returns 200 if healthy or degraded, 503 if unhealthy.
    """
    # Check dependencies concurrently
    postgres_task = asyncio.create_task(check_postgres())
    clickhouse_task = asyncio.create_task(check_clickhouse())

    postgres_health, clickhouse_health = await asyncio.gather(
        postgres_task, clickhouse_task
    )

    dependencies = {
        "postgres": postgres_health,
        "clickhouse": clickhouse_health,
    }

    overall_status = compute_overall_status(dependencies)

    response = HealthResponse(
        status=overall_status,
        version=API_VERSION,
        dependencies=dependencies,
    )

    # Return 503 if unhealthy
    status_code = 503 if overall_status == HealthStatus.UNHEALTHY else 200

    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(),
    )


@router.get(
    "/ready",
    summary="Kubernetes readiness probe",
    description="Returns 200 if the service is ready to accept traffic. "
    "Checks all critical dependencies.",
)
async def readiness_probe() -> JSONResponse:
    """Readiness probe for Kubernetes.

    Returns 200 if all critical dependencies are healthy.
    Returns 503 if service is not ready to accept traffic.
    """
    # Check only critical dependencies for readiness
    postgres_health = await check_postgres()

    # For readiness, we only require PostgreSQL (user data store)
    # ClickHouse being down means degraded mode, not unready
    if postgres_health.status == DependencyStatus.UP:
        return JSONResponse(
            status_code=200,
            content={"status": "ready"},
        )
    else:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "reason": "postgres unavailable",
                "error": postgres_health.error,
            },
        )


@router.get(
    "/live",
    summary="Kubernetes liveness probe",
    description="Returns 200 if the service process is alive. "
    "Does not check dependencies.",
)
async def liveness_probe() -> dict[str, str]:
    """Liveness probe for Kubernetes.

    Returns 200 if the application is running.
    This is a simple check - if this endpoint responds, the app is alive.
    Does NOT check dependencies to avoid restart loops.
    """
    return {"status": "alive"}
