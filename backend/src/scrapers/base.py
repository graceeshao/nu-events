"""Abstract base class for event scrapers.

To add a new scraper:
1. Subclass BaseScraper
2. Set the `name` class attribute
3. Implement fetch() to retrieve raw data
4. Implement parse() to convert raw data into EventCreate objects
5. Register the instance in scrapers/__init__.py

The run() method orchestrates fetch → parse and handles errors.
"""

import abc
import logging
from typing import Any

from src.schemas.event import EventCreate

logger = logging.getLogger(__name__)


class BaseScraper(abc.ABC):
    """Abstract base for all event scrapers."""

    name: str = "base"

    @abc.abstractmethod
    async def fetch(self) -> Any:
        """Fetch raw data from the source (HTML, JSON, etc.).

        Returns:
            Raw data in whatever format the source provides.
        """
        ...

    @abc.abstractmethod
    async def parse(self, raw_data: Any) -> list[EventCreate]:
        """Parse raw data into a list of EventCreate schemas.

        Args:
            raw_data: Output from fetch().

        Returns:
            List of validated EventCreate objects.
        """
        ...

    async def run(self) -> list[EventCreate]:
        """Execute the full scrape pipeline: fetch → parse.

        Returns:
            List of EventCreate objects ready for insertion.

        Raises:
            Exception: Re-raises any error after logging.
        """
        logger.info("Scraper '%s': starting fetch", self.name)
        try:
            raw_data = await self.fetch()
            logger.info("Scraper '%s': fetch complete, parsing", self.name)
            events = await self.parse(raw_data)
            logger.info("Scraper '%s': parsed %d events", self.name, len(events))
            return events
        except Exception:
            logger.exception("Scraper '%s': failed", self.name)
            raise
