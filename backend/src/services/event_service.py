"""Event business logic: CRUD operations with deduplication and filtering.

All database operations go through this service layer so that routes
remain thin and logic is testable independently.
"""

import math
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.event import Event, EventCategory
from src.schemas.event import EventCreate, EventList, EventRead, EventUpdate
from src.services.dedup import generate_dedup_key


async def create_event(db: AsyncSession, event_in: EventCreate) -> Event:
    """Create a new event with dedup check.

    If an event with the same dedup_key already exists, the existing
    record is returned instead of creating a duplicate.

    Args:
        db: Async database session.
        event_in: Validated event data.

    Returns:
        The created or existing Event ORM instance.
    """
    dedup_key = generate_dedup_key(
        title=event_in.title,
        start_time=event_in.start_time,
        location=event_in.location,
    )

    # Check for existing event with same dedup key
    result = await db.execute(select(Event).where(Event.dedup_key == dedup_key))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    event = Event(
        **event_in.model_dump(),
        dedup_key=dedup_key,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)
    return event


async def list_events(
    db: AsyncSession,
    *,
    category: EventCategory | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> EventList:
    """List events with optional filters and pagination.

    Args:
        db: Async database session.
        category: Filter by event category.
        date_from: Only events starting on or after this datetime.
        date_to: Only events starting on or before this datetime.
        search: Free-text search across title and description.
        page: Page number (1-indexed).
        page_size: Number of results per page.

    Returns:
        EventList with items, total count, and pagination metadata.
    """
    query = select(Event)

    if category is not None:
        query = query.where(Event.category == category)
    if date_from is not None:
        query = query.where(Event.start_time >= date_from)
    if date_to is not None:
        query = query.where(Event.start_time <= date_to)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                Event.title.ilike(pattern),
                Event.description.ilike(pattern),
            )
        )

    # Total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Paginate
    query = query.order_by(Event.start_time.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    events = result.scalars().all()

    return EventList(
        items=[EventRead.model_validate(e) for e in events],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, math.ceil(total / page_size)),
    )


async def get_event(db: AsyncSession, event_id: int) -> Event | None:
    """Get a single event by ID.

    Args:
        db: Async database session.
        event_id: Primary key of the event.

    Returns:
        The Event if found, else None.
    """
    result = await db.execute(select(Event).where(Event.id == event_id))
    return result.scalar_one_or_none()


async def update_event(
    db: AsyncSession, event_id: int, event_in: EventUpdate
) -> Event | None:
    """Partially update an event by ID.

    Only fields explicitly set (not None) in event_in are updated.

    Args:
        db: Async database session.
        event_id: Primary key of the event to update.
        event_in: Partial update data.

    Returns:
        The updated Event if found, else None.
    """
    event = await get_event(db, event_id)
    if event is None:
        return None

    update_data = event_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(event, field, value)

    await db.flush()
    await db.refresh(event)
    return event


async def delete_event(db: AsyncSession, event_id: int) -> bool:
    """Delete an event by ID.

    Args:
        db: Async database session.
        event_id: Primary key of the event to delete.

    Returns:
        True if the event was deleted, False if not found.
    """
    event = await get_event(db, event_id)
    if event is None:
        return False
    await db.delete(event)
    await db.flush()
    return True
