"""Tag template schemas for API request/response models."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TagTemplateCreate(BaseModel):
    """Request schema for creating a tag template."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Template name",
        json_schema_extra={"example": "Sports Only"},
    )
    includeTags: list[str] = Field(
        default_factory=list,
        description="Tags to include in filter",
        json_schema_extra={"example": ["Sports", "Basketball"]},
    )
    excludeTags: list[str] = Field(
        default_factory=list,
        description="Tags to exclude from filter",
        json_schema_extra={"example": ["Politics"]},
    )
    isDefault: bool = Field(
        default=False,
        description="Whether this is the user's default template",
    )


class TagTemplateUpdate(BaseModel):
    """Request schema for updating a tag template."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Template name",
        json_schema_extra={"example": "Sports Only"},
    )
    includeTags: list[str] | None = Field(
        default=None,
        description="Tags to include in filter",
        json_schema_extra={"example": ["Sports", "Basketball"]},
    )
    excludeTags: list[str] | None = Field(
        default=None,
        description="Tags to exclude from filter",
        json_schema_extra={"example": ["Politics"]},
    )
    isDefault: bool | None = Field(
        default=None,
        description="Whether this is the user's default template",
    )


class TagTemplateResponse(BaseModel):
    """Response schema for a tag template."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(
        ...,
        description="Unique template identifier",
        json_schema_extra={"example": "550e8400-e29b-41d4-a716-446655440000"},
    )
    name: str = Field(
        ...,
        description="Template name",
        json_schema_extra={"example": "Sports Only"},
    )
    includeTags: list[str] = Field(
        ...,
        description="Tags to include in filter",
        json_schema_extra={"example": ["Sports", "Basketball"]},
    )
    excludeTags: list[str] = Field(
        ...,
        description="Tags to exclude from filter",
        json_schema_extra={"example": ["Politics"]},
    )
    isDefault: bool = Field(
        ...,
        description="Whether this is the user's default template",
    )
    createdAt: datetime = Field(
        ...,
        description="When the template was created",
    )
    updatedAt: datetime = Field(
        ...,
        description="When the template was last updated",
    )

    @classmethod
    def from_model(cls, model: "TagTemplate") -> "TagTemplateResponse":  # type: ignore[name-defined]  # noqa: F821
        """Convert SQLAlchemy model to response schema."""
        return cls(
            id=model.id,
            name=model.name,
            includeTags=model.include_tags,
            excludeTags=model.exclude_tags,
            isDefault=model.is_default,
            createdAt=model.created_at,
            updatedAt=model.updated_at,
        )


class TagTemplateListResponse(BaseModel):
    """Response schema for listing tag templates."""

    items: list[TagTemplateResponse] = Field(
        ...,
        description="List of tag templates",
    )
    count: int = Field(
        ...,
        description="Total number of templates",
        json_schema_extra={"example": 5},
    )
