"""Scraper for events.northwestern.edu.

Fetches the main events page and parses individual event listings.
Uses httpx for async HTTP and BeautifulSoup for HTML parsing.
"""

import logging
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from src.models.event import EventCategory
from src.scrapers.base import BaseScraper
from src.schemas.event import EventCreate

logger = logging.getLogger(__name__)


class NorthwesternEventsScraper(BaseScraper):
    """Scrapes events from the official Northwestern events calendar."""

    name = "northwestern_events"
    base_url = "https://events.northwestern.edu"

    async def fetch(self) -> str:
        """Fetch the events listing page HTML.

        Returns:
            Raw HTML string of the events page.
        """
        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "NU-Events-Aggregator/0.1"},
        ) as client:
            response = await client.get(self.base_url)
            response.raise_for_status()
            return response.text

    async def parse(self, raw_data: str) -> list[EventCreate]:
        """Parse events from the Northwestern events HTML.

        Args:
            raw_data: HTML string from fetch().

        Returns:
            List of EventCreate objects.
        """
        soup = BeautifulSoup(raw_data, "html.parser")
        events: list[EventCreate] = []

        # TODO: Inspect the actual HTML structure at events.northwestern.edu
        # and update the selectors below. The following is a plausible
        # skeleton based on common university event page patterns.

        # TODO: Find the correct container selector for event cards
        event_cards = soup.select(".event-card, .views-row, .event-item")

        for card in event_cards:
            try:
                # TODO: Update selector for event title
                title_el = card.select_one(".event-title, h3 a, .field-title")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)

                # TODO: Update selector and date format for start time
                date_el = card.select_one(".event-date, .date-display-single, time")
                if not date_el:
                    continue
                date_str = date_el.get("datetime") or date_el.get_text(strip=True)
                start_time = self._parse_date(date_str)
                if start_time is None:
                    continue

                # TODO: Update selector for description
                desc_el = card.select_one(".event-description, .field-body, .summary")
                description = desc_el.get_text(strip=True) if desc_el else None

                # TODO: Update selector for location
                loc_el = card.select_one(".event-location, .field-location, .location")
                location = loc_el.get_text(strip=True) if loc_el else None

                # TODO: Update selector for event detail link
                link_el = card.select_one("a[href]")
                source_url = None
                if link_el and link_el.get("href"):
                    href = link_el["href"]
                    source_url = href if href.startswith("http") else f"{self.base_url}{href}"

                # TODO: Update selector for image
                img_el = card.select_one("img")
                image_url = img_el.get("src") if img_el else None

                events.append(
                    EventCreate(
                        title=title,
                        description=description,
                        start_time=start_time,
                        location=location,
                        source_url=source_url,
                        source_name="Northwestern Events",
                        category=EventCategory.OTHER,
                        image_url=image_url,
                    )
                )
            except Exception:
                logger.warning("Failed to parse event card, skipping", exc_info=True)
                continue

        return events

    @staticmethod
    def _parse_date(date_str: str) -> datetime | None:
        """Try multiple date formats to parse a date string.

        Args:
            date_str: Raw date string from the HTML.

        Returns:
            Parsed datetime or None if no format matched.
        """
        formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M",
            "%B %d, %Y %I:%M %p",
            "%b %d, %Y %I:%M %p",
            "%B %d, %Y",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        logger.warning("Could not parse date: %s", date_str)
        return None
