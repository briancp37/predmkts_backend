"""User model for authentication."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prediction_data.db.base import Base


class UserTier(str, enum.Enum):
    """User subscription tier."""

    FREE = "FREE"
    PRO = "PRO"


class User(Base):
    """User account model."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tier: Mapped[UserTier] = mapped_column(
        Enum(UserTier),
        default=UserTier.FREE,
        nullable=False,
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
    watchlists: Mapped[list["Watchlist"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Watchlist",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    tracked_traders: Mapped[list["TrackedTrader"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "TrackedTrader",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    tag_templates: Mapped[list["TagTemplate"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "TagTemplate",
        back_populates="user",
        cascade="all, delete-orphan",
    )
