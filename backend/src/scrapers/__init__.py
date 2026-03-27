"""Scraper registry — import and register all scrapers here.

Other modules can import SCRAPER_REGISTRY to discover available scrapers.
"""

from src.scrapers.base import BaseScraper
from src.scrapers.planitpurple import PlanItPurpleScraper
from src.scrapers.wildcat_connection import WildcatConnectionScraper

SCRAPER_REGISTRY: dict[str, BaseScraper] = {
    "planitpurple": PlanItPurpleScraper(),
    "wildcat_connection": WildcatConnectionScraper(),
}

__all__ = ["SCRAPER_REGISTRY", "BaseScraper"]
