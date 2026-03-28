"""SQLAlchemy model for campus events.

The Event model stores aggregated event data from all scraped sources.
A unique dedup_key prevents duplicate entries from repeated scraper runs.
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Index, JSON, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    pass


class EventCategory(str, enum.Enum):
    """Allowed event categories."""

    ACADEMIC = "academic"
    SOCIAL = "social"
    CAREER = "career"
    ARTS = "arts"
    SPORTS = "sports"
    OTHER = "other"


class Event(Base):
    """A campus event aggregated from an external source or added manually."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[EventCategory] = mapped_column(
        Enum(EventCategory), default=EventCategory.OTHER, nullable=False
    )
    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    rsvp_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    has_free_food: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dedup_key: Mapped[str] = mapped_column(
        String(500), unique=True, nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_events_start_time", "start_time"),
        Index("ix_events_category", "category"),
    )

    def __repr__(self) -> str:
        return f"<Event(id={self.id}, title='{self.title[:40]}', start={self.start_time})>"
