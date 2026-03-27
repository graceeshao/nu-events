"""CLI script to run event scrapers.

Usage:
    python scripts/run_scrapers.py                          # run all scrapers
    python scripts/run_scrapers.py --scraper northwestern_events  # run one
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add backend to path so we can import src
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from src.database.session import async_session_factory, engine
from src.models.event import Base
from src.scrapers import SCRAPER_REGISTRY
from src.services.event_service import create_event

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("run_scrapers")


async def main(scraper_name: str | None = None) -> None:
    """Run scrapers and persist discovered events.

    Args:
        scraper_name: If given, run only this scraper. Otherwise run all.
    """
    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    scrapers_to_run = {}
    if scraper_name:
        if scraper_name not in SCRAPER_REGISTRY:
            logger.error(
                "Scraper '%s' not found. Available: %s",
                scraper_name,
                list(SCRAPER_REGISTRY.keys()),
            )
            sys.exit(1)
        scrapers_to_run[scraper_name] = SCRAPER_REGISTRY[scraper_name]
    else:
        scrapers_to_run = SCRAPER_REGISTRY

    for name, scraper in scrapers_to_run.items():
        logger.info("Running scraper: %s", name)
        try:
            events_data = await scraper.run()
            logger.info("Found %d events from %s", len(events_data), name)

            async with async_session_factory() as session:
                created = 0
                for event_in in events_data:
                    event = await create_event(session, event_in)
                    if event.created_at == event.updated_at:
                        created += 1
                await session.commit()
                logger.info("Created %d new events from %s", created, name)
        except Exception:
            logger.exception("Scraper %s failed", name)

    await engine.dispose()
    logger.info("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run NU Events scrapers")
    parser.add_argument("--scraper", type=str, default=None, help="Run a specific scraper by name")
    args = parser.parse_args()
    asyncio.run(main(args.scraper))
