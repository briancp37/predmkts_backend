"""Tags API routes."""

from clickhouse_connect.driver.client import Client
from fastapi import APIRouter, Depends, Request

from prediction_data.api.clickhouse import get_clickhouse_client
from prediction_data.api.rate_limit import PUBLIC_RATE_LIMIT, limiter
from prediction_data.api.tags.schemas import EventTagResponse
from prediction_data.api.tags.service import get_event_tags

router = APIRouter()


@router.get("", response_model=list[EventTagResponse])
@limiter.limit(PUBLIC_RATE_LIMIT)
async def list_tags(
    request: Request,
    client: Client = Depends(get_clickhouse_client),
) -> list[EventTagResponse]:
    """List all available event tags with their event counts.

    Returns a list of tags that are associated with events in the platform.
    Tags are labels like 'Sports', 'Politics', 'Crypto', etc.

    Tags are ordered by event count (highest first), making it easy to
    show the most popular tags first in filter UIs.

    **Response fields:**
    - `label`: Display label for the tag (e.g., "Sports")
    - `slug`: URL-friendly slug (e.g., "sports")
    - `eventCount`: Number of events with this tag

    **Caching:** Results are cached for 5 minutes since tags change infrequently.
    """
    tags = await get_event_tags(client)
    return [EventTagResponse.model_validate(t) for t in tags]
