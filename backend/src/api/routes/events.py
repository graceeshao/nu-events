"""Event CRUD API endpoints.

Provides listing (with filters), detail, creation, and deletion of events.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import get_db
from src.models.event import EventCategory
from src.schemas.event import EventCreate, EventList, EventRead, EventUpdate
from src.services.event_service import create_event, delete_event, get_event, list_events, update_event

router = APIRouter()


@router.get("", response_model=EventList)
async def list_events_endpoint(
    category: EventCategory | None = Query(None, description="Filter by category"),
    date_from: datetime | None = Query(None, description="Events starting on or after"),
    date_to: datetime | None = Query(None, description="Events starting on or before"),
    search: str | None = Query(None, description="Search title and description"),
    include_school: bool = Query(False, description="Include PlanIt Purple (school) events"),
    include_fitness: bool = Query(False, description="Include PlanIt Purple fitness/rec events"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> EventList:
    """List events with optional filters and pagination."""
    return await list_events(
        db,
        category=category,
        date_from=date_from,
        date_to=date_to,
        search=search,
        include_school=include_school,
        include_fitness=include_fitness,
        page=page,
        page_size=page_size,
    )


@router.get("/{event_id}", response_model=EventRead)
async def get_event_endpoint(
    event_id: int,
    db: AsyncSession = Depends(get_db),
) -> EventRead:
    """Get a single event by ID."""
    event = await get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return EventRead.model_validate(event)


@router.post("", response_model=EventRead, status_code=201)
async def create_event_endpoint(
    event_in: EventCreate,
    db: AsyncSession = Depends(get_db),
) -> EventRead:
    """Create a new event (manual add)."""
    event = await create_event(db, event_in)
    return EventRead.model_validate(event)


@router.patch("/{event_id}", response_model=EventRead)
async def update_event_endpoint(
    event_id: int,
    event_in: EventUpdate,
    db: AsyncSession = Depends(get_db),
) -> EventRead:
    """Partially update an event by ID."""
    event = await update_event(db, event_id, event_in)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return EventRead.model_validate(event)


@router.delete("/{event_id}", status_code=204)
async def delete_event_endpoint(
    event_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an event by ID."""
    deleted = await delete_event(db, event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Event not found")
