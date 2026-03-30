"""Event business logic: CRUD operations with deduplication and filtering.

All database operations go through this service layer so that routes
remain thin and logic is testable independently.
"""

import math
import re
from datetime import datetime, timedelta

from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.event import Event, EventCategory
from src.schemas.event import EventCreate, EventList, EventRead, EventUpdate
from src.services.dedup import generate_dedup_key


def _normalize_title(title: str) -> str:
    """Normalize a title for fuzzy comparison."""
    t = title.lower().strip()
    # Remove common prefixes/noise
    t = re.sub(r'^(fwd:|re:|fw:)\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\[.*?\]\s*', '', t)
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


async def _find_fuzzy_duplicate(
    db: AsyncSession,
    title: str,
    start_time: datetime,
) -> Event | None:
    """Check if a similar event already exists (same title + close date).

    Catches duplicates from Re:/Fwd: email chains where the LLM extracts
    slightly different location strings but the same event.

    Args:
        db: Async database session.
        title: Event title to match.
        start_time: Event start time to match (±1 day window).

    Returns:
        Existing Event if a fuzzy match is found, else None.
    """
    norm_title = _normalize_title(title)
    if not norm_title:
        return None

    # Query events within ±1 day of the start time
    window_start = start_time - timedelta(days=1)
    window_end = start_time + timedelta(days=1)

    result = await db.execute(
        select(Event).where(
            Event.start_time >= window_start,
            Event.start_time <= window_end,
        )
    )
    candidates = result.scalars().all()

    for candidate in candidates:
        if _normalize_title(candidate.title) == norm_title:
            return candidate

    return None


async def create_event(db: AsyncSession, event_in: EventCreate) -> Event:
    """Create a new event with dedup check.

    Uses two-tier dedup:
    1. Exact dedup_key match (SHA-256 of title+time+location)
    2. Fuzzy match (normalized title + ±1 day window) to catch
       Re:/Fwd: chain duplicates with slightly different locations

    If a match is found at either level, the existing record is returned.

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

    # Tier 1: Exact dedup key match
    result = await db.execute(select(Event).where(Event.dedup_key == dedup_key))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    # Tier 2: Fuzzy title + date match
    fuzzy_match = await _find_fuzzy_duplicate(db, event_in.title, event_in.start_time)
    if fuzzy_match is not None:
        return fuzzy_match

    event = Event(
        **event_in.model_dump(),
        dedup_key=dedup_key,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)
    return event


# PlanIt Purple events that are explicitly restricted to faculty/grad students
_ACADEMIC_EXCLUSION_KEYWORDS = [
    "faculty only",           # explicitly restricted
    "faculty candidate",      # hiring talks, not student events
    "for instructors",        # instructor-only workshops
    "graduate student seminar",  # grad-only seminars
    "town hall meeting for",  # grad-year-specific meetings
    "grad-faculty symposium", # grad+faculty only
]

_FITNESS_KEYWORDS = [
    "fitness", "yoga", "pilates", "bodypump", "body pump", "cycling",
    "zumba", "hiit", "barre", "bootcamp", "cardio", "spinning",
    "kickboxing", "tai chi", "aqua fitness", "strength training",
    "workout",
]


async def list_events(
    db: AsyncSession,
    *,
    category: EventCategory | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    search: str | None = None,
    include_school: bool = False,
    include_fitness: bool = False,
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
    # Default: exclude past events (before start of today)
    if date_from is not None:
        query = query.where(Event.start_time >= date_from)
    else:
        query = query.where(Event.start_time >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0))
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

    # Exclude PlanIt Purple (school) events unless toggled on
    if not include_school:
        query = query.where(Event.source_name != "PlanIt Purple")
    else:
        # Even with school on, exclude faculty/grad-only events
        academic_conditions = [Event.title.ilike(f"%{kw}%") for kw in _ACADEMIC_EXCLUSION_KEYWORDS]
        desc_conditions = [Event.description.ilike(f"%{kw}%") for kw in [
            "for instructors new to",     # instructor onboarding
            "faculty are invited to join", # faculty-only invites
        ]]
        query = query.where(
            not_(
                and_(
                    Event.source_name == "PlanIt Purple",
                    or_(*academic_conditions, *desc_conditions),
                )
            )
        )

    # Exclude PlanIt Purple fitness/rec events unless toggled on
    if not include_fitness:
        fitness_conditions = [Event.title.ilike(f"%{kw}%") for kw in _FITNESS_KEYWORDS]
        query = query.where(
            not_(
                and_(
                    Event.source_name == "PlanIt Purple",
                    or_(*fitness_conditions),
                )
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
