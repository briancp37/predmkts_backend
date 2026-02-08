"""Tag templates API router."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from prediction_data.api.deps import get_current_user
from prediction_data.db.session import get_db
from prediction_data.api.exceptions import DuplicateError, NotFoundError
from prediction_data.api.rate_limit import AUTHENTICATED_RATE_LIMIT, limiter
from prediction_data.api.tag_templates.schemas import (
    TagTemplateCreate,
    TagTemplateListResponse,
    TagTemplateResponse,
    TagTemplateUpdate,
)
from prediction_data.api.tag_templates.service import (
    count_user_templates,
    create_tag_template,
    delete_tag_template,
    get_tag_template_by_id,
    get_tag_template_by_name,
    get_user_tag_templates,
    update_tag_template,
)
from prediction_data.db.models.user import User

router = APIRouter()

# Type aliases for dependency injection
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

# Error response descriptions for OpenAPI docs
ERROR_400 = {"description": "Bad request - template name already exists"}
ERROR_401 = {"description": "Unauthorized - missing or invalid access token"}
ERROR_404 = {"description": "Not found - template does not exist"}
ERROR_429 = {"description": "Rate limit exceeded"}


@router.get(
    "",
    response_model=TagTemplateListResponse,
    responses={401: ERROR_401, 429: ERROR_429},
    summary="List tag templates",
)
@limiter.limit(AUTHENTICATED_RATE_LIMIT)
async def list_tag_templates(
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
) -> TagTemplateListResponse:
    """Get all tag templates for the authenticated user.

    Returns templates ordered by creation date (newest first).
    """
    templates = await get_user_tag_templates(db, current_user.id)
    return TagTemplateListResponse(
        items=[TagTemplateResponse.from_model(t) for t in templates],
        count=len(templates),
    )


@router.post(
    "",
    response_model=TagTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: ERROR_400, 401: ERROR_401, 429: ERROR_429},
    summary="Create tag template",
)
@limiter.limit(AUTHENTICATED_RATE_LIMIT)
async def create_template(
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    body: TagTemplateCreate,
) -> TagTemplateResponse:
    """Create a new tag template.

    Template names must be unique per user. If isDefault is true,
    any existing default template will be unset.
    """
    # Check for duplicate name
    existing = await get_tag_template_by_name(db, current_user.id, body.name)
    if existing:
        raise DuplicateError(message=f"Template '{body.name}' already exists")

    template = await create_tag_template(
        db,
        user_id=current_user.id,
        name=body.name,
        include_tags=body.includeTags,
        exclude_tags=body.excludeTags,
        is_default=body.isDefault,
    )
    await db.commit()
    return TagTemplateResponse.from_model(template)


@router.get(
    "/{template_id}",
    response_model=TagTemplateResponse,
    responses={401: ERROR_401, 404: ERROR_404, 429: ERROR_429},
    summary="Get tag template",
)
@limiter.limit(AUTHENTICATED_RATE_LIMIT)
async def get_template(
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    template_id: uuid.UUID,
) -> TagTemplateResponse:
    """Get a specific tag template by ID."""
    template = await get_tag_template_by_id(db, current_user.id, template_id)
    if not template:
        raise NotFoundError(message="Tag template not found")
    return TagTemplateResponse.from_model(template)


@router.put(
    "/{template_id}",
    response_model=TagTemplateResponse,
    responses={400: ERROR_400, 401: ERROR_401, 404: ERROR_404, 429: ERROR_429},
    summary="Update tag template",
)
@limiter.limit(AUTHENTICATED_RATE_LIMIT)
async def update_template(
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    template_id: uuid.UUID,
    body: TagTemplateUpdate,
) -> TagTemplateResponse:
    """Update a tag template.

    All fields are optional. If isDefault is true, any existing default
    template will be unset. If name is changed, it must be unique.
    """
    # Check template exists
    existing = await get_tag_template_by_id(db, current_user.id, template_id)
    if not existing:
        raise NotFoundError(message="Tag template not found")

    # Check for duplicate name if name is being changed
    if body.name is not None and body.name != existing.name:
        duplicate = await get_tag_template_by_name(db, current_user.id, body.name)
        if duplicate:
            raise DuplicateError(message=f"Template '{body.name}' already exists")

    template = await update_tag_template(
        db,
        user_id=current_user.id,
        template_id=template_id,
        name=body.name,
        include_tags=body.includeTags,
        exclude_tags=body.excludeTags,
        is_default=body.isDefault,
    )
    await db.commit()

    if not template:
        raise NotFoundError(message="Tag template not found")
    return TagTemplateResponse.from_model(template)


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: ERROR_401, 404: ERROR_404, 429: ERROR_429},
    summary="Delete tag template",
)
@limiter.limit(AUTHENTICATED_RATE_LIMIT)
async def delete_template(
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    template_id: uuid.UUID,
) -> None:
    """Delete a tag template."""
    deleted = await delete_tag_template(db, current_user.id, template_id)
    if not deleted:
        raise NotFoundError(message="Tag template not found")
    await db.commit()
