"""Scraper registry — import and register all scrapers here.

Other modules can import SCRAPER_REGISTRY to discover available scrapers.
"""

from src.scrapers.base import BaseScraper
from src.scrapers.northwestern_events import NorthwesternEventsScraper

SCRAPER_REGISTRY: dict[str, BaseScraper] = {
    "northwestern_events": NorthwesternEventsScraper(),
}

__all__ = ["SCRAPER_REGISTRY", "BaseScraper"]
