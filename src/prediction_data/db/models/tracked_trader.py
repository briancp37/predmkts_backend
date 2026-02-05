"""TrackedTrader model for user's tracked wallet addresses."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prediction_data.db.base import Base


class TrackedTrader(Base):
    """User's tracked trader entry."""

    __tablename__ = "tracked_traders"
    __table_args__ = (
        UniqueConstraint("user_id", "trader_address", name="uq_user_trader"),
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
    trader_address: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    custom_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User",
        back_populates="tracked_traders",
    )
