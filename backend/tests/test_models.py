"""Tests for SQLAlchemy ORM models.

Verifies model creation, field defaults, and unique constraint on dedup_key.
"""

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.models.event import Event, EventCategory


class TestEventModel:
    """Test suite for the Event ORM model."""

    @pytest.mark.asyncio
    async def test_create_event(self, db_session) -> None:
        """An event can be created with required fields."""
        event = Event(
            title="Spring Fling",
            start_time=datetime(2025, 5, 10, 12, 0),
            category=EventCategory.SOCIAL,
            dedup_key="abc123",
        )
        db_session.add(event)
        await db_session.commit()

        result = await db_session.execute(select(Event).where(Event.id == event.id))
        saved = result.scalar_one()
        assert saved.title == "Spring Fling"
        assert saved.category == EventCategory.SOCIAL

    @pytest.mark.asyncio
    async def test_event_optional_fields(self, db_session) -> None:
        """Optional fields default to None."""
        event = Event(
            title="Quick Talk",
            start_time=datetime(2025, 5, 10, 12, 0),
            dedup_key="quick123",
        )
        db_session.add(event)
        await db_session.commit()

        result = await db_session.execute(select(Event).where(Event.id == event.id))
        saved = result.scalar_one()
        assert saved.description is None
        assert saved.end_time is None
        assert saved.location is None
        assert saved.source_url is None
        assert saved.image_url is None

    @pytest.mark.asyncio
    async def test_dedup_key_unique(self, db_session) -> None:
        """Two events with the same dedup_key violate the unique constraint."""
        event1 = Event(
            title="Event A",
            start_time=datetime(2025, 5, 10, 12, 0),
            dedup_key="duplicate_key",
        )
        event2 = Event(
            title="Event B",
            start_time=datetime(2025, 5, 11, 12, 0),
            dedup_key="duplicate_key",
        )
        db_session.add(event1)
        await db_session.commit()

        db_session.add(event2)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_event_category_default(self, db_session) -> None:
        """Category defaults to OTHER when not specified."""
        event = Event(
            title="Mystery Event",
            start_time=datetime(2025, 5, 10, 12, 0),
            dedup_key="mystery123",
        )
        db_session.add(event)
        await db_session.commit()

        result = await db_session.execute(select(Event).where(Event.id == event.id))
        saved = result.scalar_one()
        assert saved.category == EventCategory.OTHER

    @pytest.mark.asyncio
    async def test_event_repr(self, db_session) -> None:
        """Event __repr__ includes id, title, and start time."""
        event = Event(
            title="A" * 50,
            start_time=datetime(2025, 5, 10, 12, 0),
            dedup_key="repr123",
        )
        db_session.add(event)
        await db_session.commit()
        assert "Event" in repr(event)
        assert "id=" in repr(event)
