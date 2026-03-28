"""Scraper for planitpurple.northwestern.edu.

Fetches the PlanIt Purple events calendar and parses individual event listings.
Uses httpx for async HTTP and BeautifulSoup for HTML parsing.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup, Tag

from src.models.event import EventCategory
from src.scrapers.base import BaseScraper
from src.schemas.event import EventCreate
from src.services.email_parser import detect_free_food

logger = logging.getLogger(__name__)

# Map PlanIt Purple category labels to EventCategory enum values
CATEGORY_MAP: dict[str, EventCategory] = {
    "Arts/Humanities": EventCategory.ARTS,
    "Academic (general)": EventCategory.ACADEMIC,
    "Fitness/Sports": EventCategory.SPORTS,
    "Community Engagement": EventCategory.SOCIAL,
    "Social": EventCategory.SOCIAL,
    "Career": EventCategory.CAREER,
}

# Month abbreviation to number
MONTH_MAP: dict[str, int] = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


class PlanItPurpleScraper(BaseScraper):
    """Scrapes events from the PlanIt Purple Northwestern events calendar."""

    name = "planitpurple"
    base_url = "https://planitpurple.northwestern.edu"

    def __init__(self, *, fetch_details: bool = False) -> None:
        """Initialize the scraper.

        Args:
            fetch_details: If True, fetch individual event detail pages
                for descriptions. Defaults to False to reduce HTTP requests.
        """
        self.fetch_details = fetch_details

    async def fetch(self) -> list[str]:
        """Fetch the events listing page HTML, following pagination.

        Fetches up to 5 pages to avoid hammering the server.

        Returns:
            List of raw HTML strings, one per page.
        """
        pages: list[str] = []
        url: str | None = self.base_url
        max_pages = 5

        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "NU-Events-Aggregator/0.1"},
            follow_redirects=True,
        ) as client:
            for _ in range(max_pages):
                if url is None:
                    break
                response = await client.get(url)
                response.raise_for_status()
                html = response.text
                pages.append(html)

                # Look for "Next >" pagination link
                soup = BeautifulSoup(html, "html.parser")
                next_link = soup.select_one('a:contains("Next")')
                if next_link and next_link.get("href"):
                    href = next_link["href"]
                    url = href if href.startswith("http") else f"{self.base_url}{href}"
                else:
                    url = None

        return pages

    async def parse(self, raw_data: list[str]) -> list[EventCreate]:
        """Parse events from the PlanIt Purple HTML pages.

        When ``fetch_details`` is enabled, also fetches individual event
        detail pages to extract descriptions, RSVP URLs, and free-food
        indicators.

        Args:
            raw_data: List of HTML strings from fetch().

        Returns:
            List of EventCreate objects.
        """
        events: list[EventCreate] = []

        for html in raw_data:
            soup = BeautifulSoup(html, "html.parser")
            articles = soup.select("article.event")

            for article in articles:
                try:
                    event = self._parse_article(article)
                    if event is not None:
                        events.append(event)
                except Exception:
                    logger.warning("Failed to parse event article, skipping", exc_info=True)
                    continue

        if self.fetch_details and events:
            await self._enrich_with_details(events)

        return events

    async def _enrich_with_details(self, events: list[EventCreate]) -> None:
        """Fetch detail pages and enrich events with descriptions, RSVP URLs, etc.

        Rate-limits requests with a 0.5s delay between fetches.

        Args:
            events: List of EventCreate objects to enrich in-place.
        """
        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "NU-Events-Aggregator/0.1"},
            follow_redirects=True,
        ) as client:
            for event in events:
                if not event.source_url:
                    continue
                try:
                    resp = await client.get(event.source_url)
                    resp.raise_for_status()
                    detail = self._parse_detail_page(resp.text)
                    if detail.get("description") and not event.description:
                        event.description = detail["description"]
                    if detail.get("rsvp_url") and not event.rsvp_url:
                        event.rsvp_url = detail["rsvp_url"]
                    if detail.get("has_free_food"):
                        event.has_free_food = True
                except Exception:
                    logger.warning(
                        "Failed to fetch detail page for %s", event.source_url,
                        exc_info=True,
                    )
                await asyncio.sleep(0.5)

    @staticmethod
    def _parse_detail_page(html: str) -> dict[str, Any]:
        """Extract description, RSVP URL, and free food info from a detail page.

        Args:
            html: HTML of the event detail page.

        Returns:
            Dict with optional keys: description, rsvp_url, has_free_food.
        """
        soup = BeautifulSoup(html, "html.parser")
        result: dict[str, Any] = {}

        # Extract description from main content area
        desc_el = soup.select_one(".event-description, .description, .event-detail-description")
        if desc_el:
            result["description"] = desc_el.get_text(strip=True)

        # Extract RSVP/Register link
        for link in soup.select("a[href]"):
            link_text = link.get_text(strip=True).lower()
            if link_text in ("register", "rsvp", "sign up"):
                href = link.get("href", "")
                if href and href.startswith("http"):
                    result["rsvp_url"] = href
                    break

        # Check for "Cost: Free" and free food keywords
        page_text = soup.get_text()
        if re.search(r"cost\s*:\s*free", page_text, re.IGNORECASE):
            # Cost is free, but that doesn't mean free food
            pass
        if detect_free_food(page_text):
            result["has_free_food"] = True

        return result

    def _parse_article(self, article: Tag) -> EventCreate | None:
        """Parse a single <article> tag into an EventCreate.

        Args:
            article: BeautifulSoup Tag for an event article.

        Returns:
            EventCreate or None if required fields are missing.
        """
        # Title and source URL
        title_el = article.select_one("h3 a")
        if title_el is None:
            return None
        title = title_el.get_text(strip=True)
        if not title:
            return None

        href = title_el.get("href", "")
        source_url = href if href.startswith("http") else f"{self.base_url}{href}"

        # Date
        date_div = article.select_one(".event-date")
        if date_div is None:
            return None
        month_el = date_div.select_one(".month")
        day_el = date_div.select_one(".day")
        year_el = date_div.select_one(".year")
        if not (month_el and day_el and year_el):
            return None

        month_str = month_el.get_text(strip=True)
        day_str = day_el.get_text(strip=True)
        year_str = year_el.get_text(strip=True)

        month = MONTH_MAP.get(month_str)
        if month is None:
            logger.warning("Unknown month abbreviation: %s", month_str)
            return None

        try:
            event_date = datetime(int(year_str), month, int(day_str))
        except (ValueError, TypeError):
            logger.warning("Invalid date: %s %s, %s", month_str, day_str, year_str)
            return None

        # Time and location
        time_loc = article.select_one(".time-location")
        start_time = event_date  # default: midnight
        end_time: datetime | None = None
        location: str | None = None

        if time_loc:
            strong = time_loc.select_one("strong")
            if strong:
                time_str = strong.get_text(strip=True)
                start_time, end_time = self._parse_time(time_str, event_date)

            # Location is everything in .time-location after <strong>
            location_text = time_loc.get_text(strip=True)
            if strong:
                time_text = strong.get_text(strip=True)
                location = location_text.replace(time_text, "", 1).strip()
            else:
                location = location_text.strip()
            if not location:
                location = None

        # Categories
        category = EventCategory.OTHER
        tag_els = article.select(".tags .category-button")
        categories: list[str] = [t.get_text(strip=True) for t in tag_els]
        for cat_name in categories:
            if cat_name in CATEGORY_MAP:
                category = CATEGORY_MAP[cat_name]
                break

        return EventCreate(
            title=title,
            description=None,
            start_time=start_time,
            end_time=end_time,
            location=location,
            source_url=source_url,
            source_name="PlanIt Purple",
            category=category,
            tags={"categories": categories} if categories else None,
            rsvp_url=None,
            has_free_food=False,
        )

    @staticmethod
    def _parse_time(
        time_str: str, event_date: datetime
    ) -> tuple[datetime, datetime | None]:
        """Parse a time string into start and optional end datetimes.

        Handles formats like:
        - "All Day" → start at midnight, end_time=None
        - "9:00 AM - 10:00 AM" → parsed start and end
        - "12:00 PM - 1:00 PM" → parsed start and end

        Args:
            time_str: Time string from the event card.
            event_date: The date of the event (used as base for combining).

        Returns:
            Tuple of (start_time, end_time). end_time may be None.
        """
        if time_str.strip().lower() == "all day":
            return event_date, None

        # Try to match "HH:MM AM/PM - HH:MM AM/PM"
        match = re.match(
            r"(\d{1,2}:\d{2}\s*[AaPp][Mm])\s*-\s*(\d{1,2}:\d{2}\s*[AaPp][Mm])",
            time_str.strip(),
        )
        if match:
            start_str, end_str = match.group(1).strip(), match.group(2).strip()
            try:
                start = datetime.strptime(start_str, "%I:%M %p")
                end = datetime.strptime(end_str, "%I:%M %p")
                start_dt = event_date.replace(
                    hour=start.hour, minute=start.minute, second=0, microsecond=0
                )
                end_dt = event_date.replace(
                    hour=end.hour, minute=end.minute, second=0, microsecond=0
                )
                return start_dt, end_dt
            except ValueError:
                logger.warning("Could not parse time range: %s", time_str)

        # Fallback: try single time
        try:
            single = datetime.strptime(time_str.strip(), "%I:%M %p")
            start_dt = event_date.replace(
                hour=single.hour, minute=single.minute, second=0, microsecond=0
            )
            return start_dt, None
        except ValueError:
            pass

        logger.warning("Unrecognized time format: %s", time_str)
        return event_date, None
