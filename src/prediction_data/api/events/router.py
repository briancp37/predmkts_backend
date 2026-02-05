"""Events API routes."""

from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from prediction_data.api.clickhouse import get_clickhouse_client
from prediction_data.api.events.schemas import (
    EventListResponse,
    EventResponse,
)
from prediction_data.api.events.service import (
    get_event_by_id,
    get_events,
)

router = APIRouter()


@router.get("", response_model=EventListResponse)
async def list_events(
    category: str | None = Query(None, description="Filter by category (exact match)"),
    search: str | None = Query(None, description="Search in title and description"),
    status: str | None = Query(None, description="Filter by status (e.g., 'active', 'resolved')"),
    limit: int = Query(50, ge=1, le=500, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    client: Client = Depends(get_clickhouse_client),
) -> EventListResponse:
    """List events with optional filtering and pagination.

    Returns a paginated list of events. Events are ordered by last update time
    (most recent first).

    - **category**: Filter by event category (exact match)
    - **search**: Search text in event title and description (case-insensitive)
    - **status**: Filter by event status (e.g., 'active', 'resolved')
    - **limit**: Maximum number of events to return (1-500, default 50)
    - **offset**: Number of events to skip for pagination
    """
    events, total = await get_events(
        client,
        category=category,
        search=search,
        status=status,
        limit=limit,
        offset=offset,
    )

    # Convert dicts to EventResponse models
    items = [EventResponse.model_validate(e) for e in events]

    # Calculate page number (1-indexed)
    page = (offset // limit) + 1 if limit > 0 else 1

    return EventListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: str = Path(
        ...,
        description="Event identifier (can be platform_event_id or slug)",
    ),
    client: Client = Depends(get_clickhouse_client),
) -> EventResponse:
    """Get a single event by ID with associated markets.

    The event_id can be any of:
    - Platform event ID (platform_event_id)
    - Event slug (URL-friendly identifier)

    Returns the event with all its associated markets.
    """
    event = await get_event_by_id(client, event_id)

    if event is None:
        raise HTTPException(status_code=404, detail=f"Event not found: {event_id}")

    return EventResponse.model_validate(event)
