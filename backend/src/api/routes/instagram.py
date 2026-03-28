"""API routes for Instagram scraping."""

import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from src.config import settings
from src.database.session import async_session_factory
from src.models.organization import Organization
from src.services.instagram_scraper import scrape_all_orgs, scrape_org_instagram

logger = logging.getLogger(__name__)

router = APIRouter(tags=["instagram"])


class ScrapeResult(BaseModel):
    """Response for a single org scrape."""
    handle: str
    posts_checked: int
    events_created: int


class BulkScrapeResult(BaseModel):
    """Response for bulk scrape."""
    status: str
    orgs_queued: int
    orgs_scraped: int = 0
    orgs_failed: int = 0
    total_posts_checked: int = 0
    total_events_created: int = 0


class HandleUpdate(BaseModel):
    """Request to update an org's Instagram handle."""
    org_id: int
    handle: str


class BulkHandleUpdate(BaseModel):
    """Request to update multiple org handles at once."""
    updates: list[HandleUpdate]


@router.post("/scrape/{handle}", response_model=ScrapeResult)
async def scrape_handle(
    handle: str,
    org_name: str = Query("Unknown Org", description="Organization name"),
    days_back: int = Query(14, description="Days to look back"),
    max_posts: int = Query(10, description="Max posts to check"),
):
    """Scrape a single Instagram handle for events."""
    result = await scrape_org_instagram(
        handle=handle,
        org_name=org_name,
        days_back=days_back,
        max_posts=max_posts,
    )
    return ScrapeResult(
        handle=handle,
        posts_checked=result["posts_checked"],
        events_created=result["events_created"],
    )


@router.post("/scrape-all", response_model=BulkScrapeResult)
async def scrape_all(
    background_tasks: BackgroundTasks,
    days_back: int = Query(None, description="Days to look back"),
    max_posts: int = Query(None, description="Max posts per org"),
    background: bool = Query(True, description="Run in background"),
):
    """Scrape all orgs that have Instagram handles.

    By default runs as a background task since it takes a while.
    """
    async with async_session_factory() as db:
        result = await db.execute(
            select(Organization).where(
                Organization.instagram_handle.isnot(None),
                Organization.instagram_handle != "",
            )
        )
        orgs = result.scalars().all()

    if not orgs:
        raise HTTPException(
            status_code=404,
            detail="No organizations with Instagram handles found",
        )

    handles = [(org.instagram_handle, org.name) for org in orgs]
    _days = days_back or settings.instagram_days_back
    _max = max_posts or settings.instagram_max_posts_per_org

    if background:
        background_tasks.add_task(scrape_all_orgs, handles, _days, _max)
        return BulkScrapeResult(
            status="started",
            orgs_queued=len(handles),
        )

    result = await scrape_all_orgs(handles, _days, _max)
    return BulkScrapeResult(status="completed", orgs_queued=len(handles), **result)


@router.post("/handles", response_model=dict)
async def update_handles(payload: BulkHandleUpdate):
    """Bulk update Instagram handles for organizations."""
    updated = 0
    async with async_session_factory() as db:
        for item in payload.updates:
            result = await db.execute(
                select(Organization).where(Organization.id == item.org_id)
            )
            org = result.scalar_one_or_none()
            if org:
                org.instagram_handle = item.handle.lstrip("@").strip()
                updated += 1
        await db.commit()

    return {"updated": updated, "total": len(payload.updates)}


@router.get("/handles", response_model=dict)
async def list_handles():
    """List all organizations with Instagram handles."""
    async with async_session_factory() as db:
        result = await db.execute(
            select(Organization).where(
                Organization.instagram_handle.isnot(None),
                Organization.instagram_handle != "",
            ).order_by(Organization.name)
        )
        orgs = result.scalars().all()

    return {
        "total": len(orgs),
        "handles": [
            {"id": org.id, "name": org.name, "handle": org.instagram_handle}
            for org in orgs
        ],
    }
