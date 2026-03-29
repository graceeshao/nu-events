#!/usr/bin/env python3
"""Full PlanIt Purple scraper using JSON-LD from event detail pages.

Strategy:
1. Crawl the list view (all pages) to collect event IDs
2. Fetch each event's detail page which has schema.org/Event JSON-LD
3. Parse structured data directly — no regex guessing needed

No LLM needed. ~5-10 min for 60 days of events.

Usage:
    python scripts/scrape_planitpurple_full.py [--days 60] [--dry-run]
"""

import argparse
import asyncio
import json
import re
import sys
import os
from datetime import datetime, timedelta

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database.session import async_session_factory
from src.models.event import EventCategory
from src.schemas.event import EventCreate
from src.services.event_service import create_event

BASE_URL = "https://planitpurple.northwestern.edu"

CATEGORY_MAP = {
    "arts/humanities": EventCategory.ARTS,
    "academic (general)": EventCategory.ACADEMIC,
    "fitness/sports": EventCategory.SPORTS,
    "community engagement": EventCategory.SOCIAL,
    "social": EventCategory.SOCIAL,
    "career": EventCategory.CAREER,
}


async def collect_event_ids(client: httpx.AsyncClient, days: int) -> set[str]:
    """Collect event IDs from multiple NU event pages.

    PlanIt Purple uses client-side JS pagination, so we can't paginate
    the main list. Instead we collect IDs from multiple sources:
    1. Main PlanIt Purple page (~36 events)
    2. Weinberg College events page (~200 events, server-rendered)
    3. Any other school pages that link to PlanIt Purple
    """
    all_ids = set()

    sources = [
        ("PlanIt Purple", f"{BASE_URL}"),
        ("Weinberg", "https://weinberg.northwestern.edu/about/events/"),
    ]

    for name, url in sources:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            for link in soup.find_all("a", href=re.compile(r"(?:planitpurple\.northwestern\.edu)?/event/\d+")):
                eid = re.search(r"/event/(\d+)", link["href"])
                if eid:
                    all_ids.add(eid.group(1))

            print(f"  {name}: {len(all_ids)} total IDs", flush=True)
        except Exception as e:
            print(f"  {name}: error — {e}", flush=True)

    return all_ids


async def fetch_event_jsonld(client: httpx.AsyncClient, eid: str) -> EventCreate | None:
    """Fetch an event detail page and extract JSON-LD structured data."""
    try:
        resp = await client.get(f"{BASE_URL}/event/{eid}")
        if resp.status_code != 200:
            return None
        
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Extract JSON-LD
        script = soup.find("script", type="application/ld+json")
        if not script or not script.string:
            return None
        
        data = json.loads(script.string)
        if data.get("@type") != "Event":
            return None
        
        # Parse fields
        title = data.get("name", "").strip()
        if not title:
            return None
        
        # Dates
        start_str = data.get("startDate", "")
        end_str = data.get("endDate", "")
        
        try:
            # Strip timezone offset for naive datetime comparison
            # "2026-04-01T09:00:00-05:00" -> "2026-04-01T09:00:00"
            clean_start = re.sub(r'[+-]\d{2}:\d{2}$', '', start_str).replace('Z', '')
            start_dt = datetime.fromisoformat(clean_start)
        except (ValueError, AttributeError):
            return None
        
        end_dt = None
        if end_str:
            try:
                clean_end = re.sub(r'[+-]\d{2}:\d{2}$', '', end_str).replace('Z', '')
                end_dt = datetime.fromisoformat(clean_end)
            except (ValueError, AttributeError):
                pass
        
        # Skip past events
        if start_dt < datetime.now():
            return None
        
        # Location — extract clean venue name + address from JSON-LD
        location = None
        loc_data = data.get("location", {})
        if isinstance(loc_data, dict):
            venue = loc_data.get("name", "").strip()
            addr = loc_data.get("address", {})
            if isinstance(addr, dict):
                street = addr.get("streetAddress", "").strip()
                city = addr.get("addressLocality", "").strip()
                # Build clean location: "Venue Name, Street Address, City"
                parts = [p for p in [venue, street] if p]
                location = ", ".join(parts)
                # Add city only if it's not Evanston (assumed default)
                if city and city.lower() != "evanston":
                    location += f", {city}"
            else:
                location = venue
        elif isinstance(loc_data, str):
            location = loc_data.strip()
        
        # Safety: strip any time patterns that leaked into location
        if location:
            location = re.sub(r'^-?\s*\d{1,2}:\d{2}\s*(AM|PM)\s*', '', location, flags=re.IGNORECASE).strip()
            # Strip trailing category names
            for cat_name in ["Academic (general)", "Arts/Humanities", "Fitness/Sports", 
                            "Community Engagement", "Social", "Career"]:
                location = location.replace(cat_name, "").strip().rstrip(",")
        
        # Description
        description = data.get("description", "")
        if description:
            # Clean HTML
            description = re.sub(r"<[^>]+>", " ", description).strip()[:500]
        
        # Category from page
        category = EventCategory.OTHER
        cat_btn = soup.find("a", class_="category-button")
        if cat_btn:
            cat_text = cat_btn.get_text(strip=True).lower()
            category = CATEGORY_MAP.get(cat_text, EventCategory.OTHER)
        
        # RSVP URL
        rsvp_url = None
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True).lower()
            if text in ("register", "rsvp", "sign up", "tickets"):
                href = a["href"]
                if href.startswith("http"):
                    rsvp_url = href
                    break
        
        # Free food
        page_text = soup.get_text().lower()
        has_free_food = bool(re.search(r"free\s+(?:food|pizza|lunch|snacks|refreshments)", page_text))
        
        event_url = f"{BASE_URL}/event/{eid}"
        
        return EventCreate(
            title=title,
            description=description or None,
            start_time=start_dt,
            end_time=end_dt,
            location=location or None,
            source_url=event_url,
            source_name="PlanIt Purple",
            category=category,
            rsvp_url=rsvp_url,
            has_free_food=has_free_food,
        )
    
    except json.JSONDecodeError:
        return None
    except Exception:
        return None


async def scrape_planitpurple(days: int = 60) -> list[EventCreate]:
    """Scrape all future events from PlanIt Purple using JSON-LD."""
    
    async with httpx.AsyncClient(
        timeout=30.0,
        headers={"User-Agent": "NU-Events-Aggregator/0.1"},
        follow_redirects=True,
        limits=httpx.Limits(max_connections=10),
    ) as client:
        # Step 1: Collect event IDs
        print("Step 1: Collecting event IDs...", flush=True)
        event_ids = await collect_event_ids(client, days)
        print(f"  Found {len(event_ids)} potential event IDs", flush=True)
        
        # Step 2: Fetch JSON-LD from each detail page (concurrent)
        print(f"Step 2: Fetching event details...", flush=True)
        
        events = []
        ids_list = sorted(event_ids, key=int)
        batch_size = 10
        
        for i in range(0, len(ids_list), batch_size):
            batch = ids_list[i:i + batch_size]
            tasks = [fetch_event_jsonld(client, eid) for eid in batch]
            results = await asyncio.gather(*tasks)
            
            for event in results:
                if event is not None:
                    events.append(event)
            
            if (i // batch_size) % 10 == 0:
                print(f"  Processed {i + len(batch)}/{len(ids_list)}, found {len(events)} future events", flush=True)
            
            await asyncio.sleep(0.2)  # Be nice
    
    return events


async def main(days: int, dry_run: bool):
    print(f"Scraping PlanIt Purple for next {days} days...", flush=True)
    events = await scrape_planitpurple(days=days)
    
    print(f"\nFound {len(events)} future events", flush=True)
    
    if dry_run:
        for e in events[:25]:
            loc = (e.location or "?")[:35]
            print(f"  {e.start_time.strftime('%m/%d %H:%M')} | {e.title[:45]:<45} | {loc}")
        if len(events) > 25:
            print(f"  ... and {len(events) - 25} more")
        print(f"\n(dry run — nothing saved)")
        return
    
    created = 0
    async with async_session_factory() as db:
        for e in events:
            result = await create_event(db, e)
            if result.title == e.title:
                created += 1
        await db.commit()
    
    print(f"Created {created} new events (deduped {len(events) - created})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=60, help="Days ahead to scrape")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.days, args.dry_run))
