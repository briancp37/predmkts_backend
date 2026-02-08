"""Tag template service layer for database operations."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult

from prediction_data.db.models.tag_template import TagTemplate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def get_user_tag_templates(
    db: AsyncSession, user_id: uuid.UUID
) -> list[TagTemplate]:
    """Get all tag templates for a user."""
    result = await db.execute(
        select(TagTemplate)
        .where(TagTemplate.user_id == user_id)
        .order_by(TagTemplate.created_at.desc())
    )
    return list(result.scalars().all())


async def get_tag_template_by_id(
    db: AsyncSession, user_id: uuid.UUID, template_id: uuid.UUID
) -> TagTemplate | None:
    """Get a specific tag template by ID for a user."""
    result = await db.execute(
        select(TagTemplate).where(
            TagTemplate.id == template_id,
            TagTemplate.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_tag_template_by_name(
    db: AsyncSession, user_id: uuid.UUID, name: str
) -> TagTemplate | None:
    """Get a tag template by name for a user."""
    result = await db.execute(
        select(TagTemplate).where(
            TagTemplate.user_id == user_id,
            TagTemplate.name == name,
        )
    )
    return result.scalar_one_or_none()


async def create_tag_template(
    db: AsyncSession,
    user_id: uuid.UUID,
    name: str,
    include_tags: list[str],
    exclude_tags: list[str],
    is_default: bool = False,
) -> TagTemplate:
    """Create a new tag template for a user.

    If is_default is True, unsets any existing default template first.
    """
    if is_default:
        await unset_default_template(db, user_id)

    template = TagTemplate(
        user_id=user_id,
        name=name,
        include_tags=include_tags,
        exclude_tags=exclude_tags,
        is_default=is_default,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template


async def update_tag_template(
    db: AsyncSession,
    user_id: uuid.UUID,
    template_id: uuid.UUID,
    name: str | None = None,
    include_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
    is_default: bool | None = None,
) -> TagTemplate | None:
    """Update a tag template.

    If is_default is True, unsets any existing default template first.
    Returns None if template not found.
    """
    # Build update values
    values: dict[str, Any] = {}
    if name is not None:
        values["name"] = name
    if include_tags is not None:
        values["include_tags"] = include_tags
    if exclude_tags is not None:
        values["exclude_tags"] = exclude_tags
    if is_default is not None:
        if is_default:
            await unset_default_template(db, user_id)
        values["is_default"] = is_default

    if not values:
        # No updates provided, return existing template
        return await get_tag_template_by_id(db, user_id, template_id)

    result = await db.execute(
        update(TagTemplate)
        .where(
            TagTemplate.id == template_id,
            TagTemplate.user_id == user_id,
        )
        .values(**values)
        .returning(TagTemplate)
    )
    return result.scalar_one_or_none()


async def delete_tag_template(
    db: AsyncSession, user_id: uuid.UUID, template_id: uuid.UUID
) -> bool:
    """Delete a tag template. Returns True if deleted."""
    result = await db.execute(
        delete(TagTemplate).where(
            TagTemplate.id == template_id,
            TagTemplate.user_id == user_id,
        )
    )
    cursor_result = cast(CursorResult[Any], result)
    return cursor_result.rowcount > 0


async def unset_default_template(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Unset any existing default template for a user."""
    await db.execute(
        update(TagTemplate)
        .where(
            TagTemplate.user_id == user_id,
            TagTemplate.is_default == True,  # noqa: E712
        )
        .values(is_default=False)
    )


async def count_user_templates(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Count the number of templates for a user."""
    result = await db.execute(
        select(TagTemplate).where(TagTemplate.user_id == user_id)
    )
    return len(list(result.scalars().all()))
