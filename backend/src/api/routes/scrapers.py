"""Scraper management API endpoints.

Allows listing available scrapers and triggering them manually via the API.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import get_db
from src.scrapers import SCRAPER_REGISTRY
from src.services.event_service import create_event

router = APIRouter()


class ScraperInfo(BaseModel):
    """Summary info about a registered scraper."""

    name: str


class ScraperRunResult(BaseModel):
    """Result of running a scraper."""

    scraper: str
    events_found: int
    events_created: int


@router.get("", response_model=list[ScraperInfo])
async def list_scrapers() -> list[ScraperInfo]:
    """List all registered scrapers."""
    return [ScraperInfo(name=name) for name in SCRAPER_REGISTRY]


@router.post("/{name}/run", response_model=ScraperRunResult)
async def run_scraper(
    name: str,
    db: AsyncSession = Depends(get_db),
) -> ScraperRunResult:
    """Trigger a scraper by name and save discovered events.

    Args:
        name: Registered scraper name.
        db: Database session.

    Returns:
        Summary of scraper results.
    """
    scraper = SCRAPER_REGISTRY.get(name)
    if scraper is None:
        raise HTTPException(
            status_code=404,
            detail=f"Scraper '{name}' not found. Available: {list(SCRAPER_REGISTRY.keys())}",
        )

    events_data = await scraper.run()
    created_count = 0
    for event_in in events_data:
        event = await create_event(db, event_in)
        # If the event was freshly created (not a dedup match), count it
        if event.created_at == event.updated_at:
            created_count += 1

    return ScraperRunResult(
        scraper=name,
        events_found=len(events_data),
        events_created=created_count,
    )
