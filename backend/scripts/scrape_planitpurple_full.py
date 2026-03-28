"""Full PlanIt Purple scraper — fetches ALL events for the next 60 days.

Uses the list view with date range params to get complete event data.
Parses event cards from the HTML and fetches detail pages for descriptions.
No LLM needed — events are structured.

Usage:
    python scripts/scrape_planitpurple_full.py [--days 60] [--dry-run]
"""

import argparse
import asyncio
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
    "Arts/Humanities": EventCategory.ARTS,
    "Academic (general)": EventCategory.ACADEMIC,
    "Fitness/Sports": EventCategory.SPORTS,
    "Community Engagement": EventCategory.SOCIAL,
    "Social": EventCategory.SOCIAL,
    "Career": EventCategory.CAREER,
}

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def parse_date_from_card(card) -> datetime | None:
    """Parse date from a PlanIt Purple event card."""
    # Find the date block: "Mar\n28\n2026"
    date_parts = card.find_all(string=re.compile(r'^\d{1,2}$'))
    month_parts = card.find_all(string=re.compile(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$'))
    year_parts = card.find_all(string=re.compile(r'^20\d{2}$'))

    if not month_parts or not date_parts or not year_parts:
        return None

    try:
        month = MONTH_MAP[month_parts[0].strip()]
        day = int(date_parts[0].strip())
        year = int(year_parts[0].strip())
        return datetime(year, month, day)
    except (ValueError, KeyError):
        return None


def parse_time_range(text: str) -> tuple[str | None, str | None]:
    """Parse time range like '9:00 AM - 4:00 PM' or '12:30 PM'."""
    time_re = re.compile(r'(\d{1,2}:\d{2}\s*[AP]M)', re.IGNORECASE)
    matches = time_re.findall(text)
    if len(matches) >= 2:
        return matches[0].strip(), matches[1].strip()
    elif len(matches) == 1:
        return matches[0].strip(), None
    return None, None


def time_str_to_time(s: str) -> tuple[int, int]:
    """Parse '9:00 AM' to (9, 0)."""
    match = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM)', s, re.IGNORECASE)
    if not match:
        return 0, 0
    h, m, ampm = int(match.group(1)), int(match.group(2)), match.group(3).upper()
    if ampm == "PM" and h != 12:
        h += 12
    elif ampm == "AM" and h == 12:
        h = 0
    return h, m


async def fetch_event_detail(client: httpx.AsyncClient, event_url: str) -> dict:
    """Fetch an event detail page for description and extra info."""
    try:
        resp = await client.get(event_url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Get description from the main content area
        # PlanIt Purple detail pages have the description after the metadata
        desc_parts = []
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if text and len(text) > 20 and not text.startswith("Cost:"):
                desc_parts.append(text)

        description = " ".join(desc_parts[:3])[:500] if desc_parts else None

        # Check for registration/RSVP links
        rsvp_url = None
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True).lower()
            if any(w in text for w in ["register", "rsvp", "sign up", "tickets"]):
                rsvp_url = a["href"]
                break

        # Check for free
        page_text = soup.get_text().lower()
        has_free_food = bool(re.search(r'free\s+(?:food|pizza|lunch|snacks|refreshments)', page_text))
        is_free = "cost: free" in page_text

        return {
            "description": description,
            "rsvp_url": rsvp_url,
            "has_free_food": has_free_food,
            "is_free": is_free,
        }
    except Exception:
        return {}


async def scrape_planitpurple(days: int = 60, fetch_details: bool = True) -> list[EventCreate]:
    """Scrape all events from PlanIt Purple for the next N days."""
    start = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

    events = []
    page = 1
    max_pages = 20

    async with httpx.AsyncClient(
        timeout=30.0,
        headers={"User-Agent": "NU-Events-Aggregator/0.1"},
        follow_redirects=True,
    ) as client:
        while page <= max_pages:
            url = f"{BASE_URL}?start={start}&end={end}&page={page}"
            print(f"  Fetching page {page}: {url}", flush=True)

            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except Exception as e:
                print(f"  Error fetching page {page}: {e}", flush=True)
                break

            soup = BeautifulSoup(resp.text, "html.parser")

            # Find all event links
            event_links = soup.find_all("a", href=re.compile(r'^/event/\d+'))
            if not event_links:
                break

            seen_this_page = set()
            for link in event_links:
                href = link.get("href", "")
                event_id = re.search(r'/event/(\d+)', href)
                if not event_id:
                    continue
                eid = event_id.group(1)
                if eid in seen_this_page:
                    continue
                seen_this_page.add(eid)

                title = link.get_text(strip=True)
                if not title:
                    continue

                # Find the parent card to get date/time/location
                card = link.find_parent()
                if card is None:
                    continue
                # Go up a few levels to get the full card
                for _ in range(5):
                    parent = card.find_parent()
                    if parent and parent.find(string=re.compile(r'^20\d{2}$')):
                        card = parent
                        break
                    elif parent:
                        card = parent

                card_text = card.get_text(" ", strip=True)

                # Parse date
                date_match = re.search(
                    r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+(\d{4})',
                    card_text
                )
                if not date_match:
                    continue

                month = MONTH_MAP.get(date_match.group(1))
                day = int(date_match.group(2))
                year = int(date_match.group(3))
                if not month:
                    continue

                event_date = datetime(year, month, day)

                # Skip past events
                if event_date.date() < datetime.now().date():
                    continue

                # Parse time
                start_time_str, end_time_str = parse_time_range(card_text)

                if start_time_str:
                    h, m = time_str_to_time(start_time_str)
                    start_dt = event_date.replace(hour=h, minute=m)
                else:
                    start_dt = event_date

                end_dt = None
                if end_time_str:
                    h, m = time_str_to_time(end_time_str)
                    end_dt = event_date.replace(hour=h, minute=m)

                # Parse location (after the time, usually the rest of the line)
                location = None
                loc_match = re.search(
                    r'(?:AM|PM)\s+(.+?)(?:\s*$)',
                    card_text,
                    re.IGNORECASE
                )
                if loc_match:
                    loc = loc_match.group(1).strip()
                    # Clean up — remove trailing date fragments
                    loc = re.sub(r'\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+\s+\d{4}.*', '', loc)
                    if loc and len(loc) > 3:
                        location = loc

                event_url = f"{BASE_URL}{href}"

                # Fetch detail page for description
                detail = {}
                if fetch_details:
                    detail = await fetch_event_detail(client, event_url)
                    await asyncio.sleep(0.3)  # Be nice

                events.append(EventCreate(
                    title=title,
                    description=detail.get("description"),
                    start_time=start_dt,
                    end_time=end_dt,
                    location=location,
                    source_url=event_url,
                    source_name="PlanIt Purple",
                    category=EventCategory.OTHER,
                    rsvp_url=detail.get("rsvp_url"),
                    has_free_food=detail.get("has_free_food", False),
                ))

            # Check for next page
            next_link = soup.find("a", string=re.compile(r'Next'))
            if not next_link:
                break
            page += 1

    return events


async def main(days: int, dry_run: bool):
    print(f"Scraping PlanIt Purple for next {days} days...", flush=True)
    events = await scrape_planitpurple(days=days, fetch_details=True)

    print(f"\nFound {len(events)} future events", flush=True)

    if dry_run:
        for e in events[:20]:
            print(f"  {e.start_time.strftime('%m/%d %H:%M')} | {e.title[:60]} | {e.location or '?'}")
        if len(events) > 20:
            print(f"  ... and {len(events) - 20} more")
        print("\n(dry run — nothing saved)")
        return

    # Save to DB
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
