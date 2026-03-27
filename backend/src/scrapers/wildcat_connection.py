"""Scraper for WildcatConnection (CampusLabs Engage platform).

Northwestern's student org events at northwestern.campuslabs.com.
Attempts the public API first; falls back gracefully if auth is required.
"""

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from src.models.event import EventCategory
from src.scrapers.base import BaseScraper
from src.schemas.event import EventCreate

logger = logging.getLogger(__name__)

API_URL = "https://northwestern.campuslabs.com/engage/api/discovery/event/search"

# Map CampusLabs category names to EventCategory enum values
CATEGORY_MAP: dict[str, EventCategory] = {
    "Arts": EventCategory.ARTS,
    "Arts & Entertainment": EventCategory.ARTS,
    "Academic": EventCategory.ACADEMIC,
    "Athletics": EventCategory.SPORTS,
    "Sports": EventCategory.SPORTS,
    "Fitness": EventCategory.SPORTS,
    "Social": EventCategory.SOCIAL,
    "Community Service": EventCategory.SOCIAL,
    "Career": EventCategory.CAREER,
    "Professional Development": EventCategory.CAREER,
}


class WildcatConnectionScraper(BaseScraper):
    """Scrapes events from Northwestern's WildcatConnection (CampusLabs Engage)."""

    name = "wildcat_connection"
    auth_cookie: str | None = None

    async def fetch(self) -> dict[str, Any] | None:
        """Fetch events from the CampusLabs Engage API.

        Tries the public API endpoint. If authentication is required
        (401/403 or redirect to login), logs a warning and returns None.

        Returns:
            JSON response dict, or None if auth is required.
        """
        headers: dict[str, str] = {
            "User-Agent": "NU-Events-Aggregator/0.1",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.auth_cookie:
            headers["Cookie"] = self.auth_cookie

        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "endsAfter": now_iso,
            "orderByField": "endsOn",
            "orderByDirection": "ascending",
            "status": "Approved",
            "take": 50,
        }

        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=False,
        ) as client:
            try:
                response = await client.post(API_URL, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                logger.error("HTTP error fetching WildcatConnection: %s", exc)
                raise

            # Check for auth-required responses
            if response.status_code in (401, 403):
                logger.warning(
                    "WildcatConnection API returned %d — authentication is required. "
                    "Set auth_cookie on the scraper instance to access events.",
                    response.status_code,
                )
                return None

            # Check for redirect to login page
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location", "")
                if "login" in location.lower() or "sso" in location.lower():
                    logger.warning(
                        "WildcatConnection API redirected to login (%s) — "
                        "authentication is required.",
                        location,
                    )
                    return None

            response.raise_for_status()
            return response.json()

    async def parse(self, raw_data: dict[str, Any] | None) -> list[EventCreate]:
        """Parse events from the CampusLabs Engage API response.

        Args:
            raw_data: JSON response dict from fetch(), or None if auth required.

        Returns:
            List of EventCreate objects.
        """
        if raw_data is None:
            return []

        events: list[EventCreate] = []
        items = raw_data.get("value", [])

        for item in items:
            try:
                event = self._parse_item(item)
                if event is not None:
                    events.append(event)
            except Exception:
                logger.warning(
                    "Failed to parse WildcatConnection event, skipping",
                    exc_info=True,
                )
                continue

        return events

    @staticmethod
    def _parse_item(item: dict[str, Any]) -> EventCreate | None:
        """Parse a single event item from the API response.

        Args:
            item: Event dict from the API response.

        Returns:
            EventCreate or None if required fields are missing.
        """
        name = item.get("name")
        if not name:
            return None

        starts_on = item.get("startsOn")
        if not starts_on:
            return None

        try:
            start_time = datetime.fromisoformat(starts_on.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

        end_time: datetime | None = None
        ends_on = item.get("endsOn")
        if ends_on:
            try:
                end_time = datetime.fromisoformat(ends_on.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        # Map categories
        category = EventCategory.OTHER
        category_names: list[str] = item.get("categoryNames") or []
        for cat_name in category_names:
            for key, value in CATEGORY_MAP.items():
                if key.lower() in cat_name.lower():
                    category = value
                    break
            if category != EventCategory.OTHER:
                break

        # Build source URL
        event_id = item.get("id")
        source_url: str | None = None
        if event_id:
            source_url = f"https://northwestern.campuslabs.com/engage/event/{event_id}"

        # Image URL
        image_url = item.get("imagePath")
        if image_url and not image_url.startswith("http"):
            image_url = f"https://northwestern.campuslabs.com{image_url}"

        org_name = item.get("organizationName")

        return EventCreate(
            title=name,
            description=item.get("description"),
            start_time=start_time,
            end_time=end_time,
            location=item.get("location"),
            source_url=source_url,
            source_name=f"WildcatConnection ({org_name})" if org_name else "WildcatConnection",
            category=category,
            tags={"categoryNames": category_names} if category_names else None,
            image_url=image_url,
        )
