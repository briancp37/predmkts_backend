"""TagTemplate model for user-saved tag filter templates."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator

from prediction_data.db.base import Base


class StringArrayType(TypeDecorator[list[str]]):
    """Cross-database array type.

    Uses PostgreSQL ARRAY(String) in production, JSON in SQLite for tests.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(String))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: list[str] | None, dialect: Any) -> Any:
        if value is None:
            return []
        return value

    def process_result_value(self, value: Any, dialect: Any) -> list[str]:
        if value is None:
            return []
        return list(value)


class TagTemplate(Base):
    """User's saved tag filter template."""

    __tablename__ = "tag_templates"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_template_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    include_tags: Mapped[list[str]] = mapped_column(
        StringArrayType(),
        nullable=False,
        default=list,
    )
    exclude_tags: Mapped[list[str]] = mapped_column(
        StringArrayType(),
        nullable=False,
        default=list,
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User",
        back_populates="tag_templates",
    )
