"""Tag-related Pydantic schemas."""

from pydantic import BaseModel, Field


class EventTagResponse(BaseModel):
    """Event tag information with counts.

    Event tags are labels like 'Sports', 'Politics', 'Crypto' that are
    associated with events in the prediction market platform.
    """

    label: str = Field(
        ...,
        description="Display label for the tag",
        json_schema_extra={"example": "Sports"},
    )
    slug: str = Field(
        ...,
        description="URL-friendly slug for the tag",
        json_schema_extra={"example": "sports"},
    )
    eventCount: int = Field(
        ...,
        description="Number of events with this tag",
        json_schema_extra={"example": 1250},
    )
