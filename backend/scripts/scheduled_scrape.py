#!/usr/bin/env python3
"""Automated event scraper — runs all sources on a schedule.

Designed to be called by macOS launchd every 3 hours.
All processing is local (Ollama + HTTP). Zero API tokens consumed.

Every run:
  1. PlanIt Purple — HTTP scrape, no LLM (~2 min)
  2. Gmail LISTSERV — IMAP poll + local LLM (~10 min)
  3. Clean up past events

Once per day (first run after midnight):
  4. Instagram — REST API + local LLM (~45 min)
  5. Refresh post cache stats

Usage:
    python scripts/scheduled_scrape.py           # normal run
    python scripts/scheduled_scrape.py --all     # force all sources including IG
    python scripts/scheduled_scrape.py --dry-run # log what would happen
"""

import argparse
import asyncio
import json
import logging
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Ensure we can import from src/
sys.path.insert(0, str(Path(__file__).parent.parent))

LOG_DIR = Path(__file__).parent.parent / "logs"
STATE_FILE = Path(__file__).parent.parent / "scrape_state.json"
DB_PATH = Path(__file__).parent.parent / "nu_events.db"


def setup_logging():
    """Configure logging to both file and stdout."""
    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / f"scrape-{datetime.now().strftime('%Y-%m-%d')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode="a"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("scheduled_scrape")


def load_state() -> dict:
    """Load scrape state (last run times, etc.)."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    """Persist scrape state."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def check_ollama() -> bool:
    """Check if Ollama is running."""
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def should_run_instagram(state: dict) -> bool:
    """Check if Instagram scrape should run (once per day)."""
    last_ig = state.get("last_instagram_run")
    if not last_ig:
        return True
    last_dt = datetime.fromisoformat(last_ig)
    return datetime.now() - last_dt > timedelta(hours=20)


def clean_past_events(logger):
    """Remove events that have already passed."""
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    # Keep events from the last 24h (they might still be happening)
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    deleted = c.execute(
        "DELETE FROM events WHERE start_time < ? AND source_name != 'PlanIt Purple'",
        (cutoff,),
    ).rowcount
    # For PlanIt Purple, keep longer since they're structured
    pp_cutoff = (datetime.now() - timedelta(days=1)).isoformat()
    pp_deleted = c.execute(
        "DELETE FROM events WHERE start_time < ? AND source_name = 'PlanIt Purple'",
        (pp_cutoff,),
    ).rowcount
    conn.commit()
    conn.close()
    if deleted + pp_deleted > 0:
        logger.info("Cleaned %d past events (%d general + %d PlanIt Purple)", deleted + pp_deleted, deleted, pp_deleted)


async def run_planitpurple(logger) -> dict:
    """Scrape PlanIt Purple (no LLM needed)."""
    logger.info("=== PlanIt Purple Scrape ===")
    try:
        # Import here to avoid startup cost if not needed
        from scripts.scrape_planitpurple_full import scrape_planitpurple
        from src.database.session import async_session_factory
        from src.services.event_service import create_event

        events = await scrape_planitpurple(days=30)
        future_events = [e for e in events if e.start_time > datetime.now()]

        created = 0
        async with async_session_factory() as db:
            for e in future_events:
                result = await create_event(db, e)
                if result.title == e.title:
                    created += 1
            await db.commit()

        logger.info("PlanIt Purple: %d scraped, %d future, %d new", len(events), len(future_events), created)
        return {"scraped": len(events), "future": len(future_events), "new": created}

    except Exception as exc:
        logger.exception("PlanIt Purple failed: %s", exc)
        return {"error": str(exc)}


async def run_gmail(logger) -> dict:
    """Poll Gmail for new LISTSERV emails."""
    logger.info("=== Gmail LISTSERV Poll ===")
    try:
        # Load .env for GMAIL_USER_EMAIL
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / ".env")

        from src.services.gmail_poller import GmailPoller
        from src.config import settings

        poller = GmailPoller(
            credentials_file=settings.gmail_credentials_file,
            token_file=settings.gmail_token_file,
            label=settings.gmail_label,
        )
        result = await poller.poll_once()
        logger.info("Gmail: %d emails processed, %d events created",
                     result["emails_processed"], result["events_created"])
        return result

    except Exception as exc:
        logger.exception("Gmail poll failed: %s", exc)
        return {"error": str(exc)}


async def run_instagram(logger) -> dict:
    """Scrape a BATCH of Instagram orgs (staggered to avoid rate limits).

    Instead of scraping all 427 orgs at once (triggers 429s), we split
    them into batches of ~50 and rotate through them across scheduler
    runs. With 8 runs/day, all orgs get checked every ~1 day.
    """
    BATCH_SIZE = 25
    logger.info("=== Instagram Scrape (batch of %d) ===", BATCH_SIZE)
    try:
        from src.services.instagram_scraper import scrape_all_orgs

        conn = sqlite3.connect(str(DB_PATH))
        orgs = conn.execute("""
            SELECT instagram_handle, name FROM organizations
            WHERE instagram_handle IS NOT NULL AND instagram_handle != ''
              AND (instagram_active = 1 OR instagram_active IS NULL)
            ORDER BY name
        """).fetchall()
        conn.close()

        if not orgs:
            logger.info("No orgs with Instagram handles")
            return {"orgs": 0}

        # Determine which batch to scrape this run
        state = load_state()
        batch_index = state.get("ig_batch_index", 0)
        total_batches = (len(orgs) + BATCH_SIZE - 1) // BATCH_SIZE

        start = batch_index * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(orgs))
        batch = orgs[start:end]

        # Advance batch index for next run (wrap around)
        state["ig_batch_index"] = (batch_index + 1) % total_batches
        save_state(state)

        logger.info(
            "Batch %d/%d: orgs %d-%d of %d (handles: %s ... %s)",
            batch_index + 1, total_batches, start + 1, end, len(orgs),
            batch[0][0] if batch else "?", batch[-1][0] if batch else "?",
        )

        result = await scrape_all_orgs(batch, days_back=14, max_posts=5)
        logger.info(
            "Instagram: %d orgs, %d posts, %d→LLM, %d filtered, %d events",
            result["orgs_scraped"], result["total_posts_checked"],
            result.get("total_llm_calls", 0), result.get("total_filtered_out", 0),
            result["total_events_created"],
        )
        return result

    except Exception as exc:
        logger.exception("Instagram scrape failed: %s", exc)
        return {"error": str(exc)}


async def main(force_all: bool = False, dry_run: bool = False):
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("Scheduled scrape starting at %s", datetime.now().isoformat())

    state = load_state()
    ollama_ok = check_ollama()
    logger.info("Ollama status: %s", "running" if ollama_ok else "NOT RUNNING")

    if dry_run:
        logger.info("DRY RUN — no changes will be made")

    results = {}

    # 1. PlanIt Purple (always, no LLM needed)
    if not dry_run:
        results["planitpurple"] = await run_planitpurple(logger)
    else:
        logger.info("Would scrape PlanIt Purple (30 days)")

    # 2. Gmail LISTSERV (always, needs Ollama)
    if ollama_ok and not dry_run:
        results["gmail"] = await run_gmail(logger)
    elif not ollama_ok:
        logger.warning("Skipping Gmail — Ollama not running")
    else:
        logger.info("Would poll Gmail LISTSERV")

    # 3. Instagram (staggered — 50 orgs per run, every run)
    if ollama_ok and not dry_run:
        results["instagram"] = await run_instagram(logger)
        state["last_instagram_run"] = datetime.now().isoformat()
    elif not ollama_ok:
        logger.warning("Skipping Instagram — Ollama not running")
    else:
        logger.info("Would scrape Instagram (batch of 50)")

    # 4. Clean up past events
    if not dry_run:
        clean_past_events(logger)

    # Save state
    state["last_run"] = datetime.now().isoformat()
    state["last_results"] = results
    if not dry_run:
        save_state(state)

    # Summary
    conn = sqlite3.connect(str(DB_PATH))
    total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    future = conn.execute("SELECT COUNT(*) FROM events WHERE start_time >= datetime('now')").fetchone()[0]
    conn.close()

    logger.info("=" * 60)
    logger.info("DONE — DB: %d total events, %d future", total, future)
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scheduled NU Events scraper")
    parser.add_argument("--all", action="store_true", help="Force all sources including Instagram")
    parser.add_argument("--dry-run", action="store_true", help="Log what would happen")
    args = parser.parse_args()
    asyncio.run(main(force_all=args.all, dry_run=args.dry_run))
