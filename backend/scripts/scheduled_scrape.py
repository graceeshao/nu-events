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

# Load .env
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

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
    """Persist scrape state, merging INTO the current file so we don't
    clobber keys written by other code mid-run (e.g. instagram_cursor)."""
    # Re-read current file — it may have been updated during this run
    current = {}
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                current = json.load(f)
        except (ValueError, json.JSONDecodeError):
            pass
    # Merge: state's keys win EXCEPT instagram_cursor which is owned by the scraper
    for k, v in state.items():
        if k in ("instagram_cursor", "last_gmail_poll"):
            continue  # never overwrite — owned by their respective modules
        current[k] = v
    with open(STATE_FILE, "w") as f:
        json.dump(current, f, indent=2, default=str)


def check_ollama() -> bool:
    """Check if Ollama is running."""
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def schedule_next_wake(logger):
    """Schedule a one-shot pmset wake for the next overnight scrape.

    After each run during overnight hours (10 PM – 5 AM), schedule a
    wake 2 hours from now so launchd can fire the scraper again.
    Requires passwordless sudo for pmset (see install_scheduler.sh).
    """
    now = datetime.now()
    hour = now.hour

    # Only schedule wakes during overnight hours
    if not (hour >= 22 or hour < 5):
        return  # Daytime — Mac is presumably awake

    # Schedule wake 2 hours from now
    wake_time = now + timedelta(hours=2)
    if 7 <= wake_time.hour < 22:
        return  # Next wake would be daytime — skip

    wake_str = wake_time.strftime("%m/%d/%Y %H:%M:%S")
    try:
        result = subprocess.run(
            ["sudo", "-n", "pmset", "schedule", "wake", wake_str],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            logger.info("Scheduled next wake at %s", wake_str)
        else:
            logger.debug("Could not schedule wake (sudo -n failed)")
    except Exception as exc:
        logger.debug("Failed to schedule wake: %s", exc)


def check_network(logger) -> bool:
    """Quick DNS check — can we resolve instagram.com?"""
    import socket
    try:
        socket.getaddrinfo("www.instagram.com", 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return True
    except socket.gaierror:
        logger.warning("Network check failed — cannot resolve www.instagram.com")
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
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
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
    """Scrape Instagram orgs using a persistent cursor.

    Passes ALL active orgs to scrape_all_orgs() which handles cursor-based
    sequential iteration internally (via scrape_state.json). Each run
    processes up to max_per_run orgs starting from where the last run
    left off.
    """
    MAX_PER_RUN = 15
    logger.info("=== Instagram Scrape (max %d per run) ===", MAX_PER_RUN)

    # Bail early if no network — prevents cursor reset on DNS failure
    if not check_network(logger):
        logger.warning("Skipping Instagram — no network connectivity")
        return {"error": "no_network", "orgs_scraped": 0}

    try:
        from src.services.instagram_scraper import scrape_all_orgs

        conn = sqlite3.connect(str(DB_PATH), timeout=30)
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

        logger.info("Total active orgs with handles: %d", len(orgs))

        result = await scrape_all_orgs(orgs, days_back=14, max_posts=5, max_per_run=MAX_PER_RUN)
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


REMOTE_DATABASE_URL = os.environ.get(
    "REMOTE_DATABASE_URL",
    "",  # Set in .env — never hardcode credentials
)


async def sync_to_remote(logger):
    """Push future events from local SQLite to remote Postgres."""
    if not REMOTE_DATABASE_URL:
        logger.info("Skipping remote sync — REMOTE_DATABASE_URL not set")
        return

    logger.info("=== Syncing to remote Postgres ===")
    try:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from sqlalchemy import text

        remote_url = REMOTE_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        engine = create_async_engine(remote_url)

        # Read local future events
        conn = sqlite3.connect(str(DB_PATH), timeout=30)
        conn.row_factory = sqlite3.Row
        events = conn.execute("""
            SELECT title, description, start_time, end_time, location,
                   source_url, source_name, category, image_url, rsvp_url,
                   has_free_food, dedup_key
            FROM events WHERE start_time >= datetime('now')
        """).fetchall()
        conn.close()

        def parse_dt(s):
            if not s:
                return None
            try:
                return datetime.fromisoformat(s.replace(".000000", ""))
            except (ValueError, AttributeError):
                return None

        async with async_sessionmaker(engine, class_=AsyncSession)() as session:
            inserted = 0
            for event in events:
                result = await session.execute(
                    text("SELECT id FROM events WHERE dedup_key = :key"),
                    {"key": event["dedup_key"]},
                )
                if result.scalar_one_or_none() is not None:
                    continue

                await session.execute(
                    text("""
                        INSERT INTO events (title, description, start_time, end_time, location,
                            source_url, source_name, category, image_url, rsvp_url,
                            has_free_food, dedup_key, created_at, updated_at)
                        VALUES (:title, :description, :start_time, :end_time, :location,
                            :source_url, :source_name, :category, :image_url, :rsvp_url,
                            :has_free_food, :dedup_key, :now, :now)
                    """),
                    {
                        "title": event["title"],
                        "description": event["description"],
                        "start_time": parse_dt(event["start_time"]),
                        "end_time": parse_dt(event["end_time"]),
                        "location": event["location"],
                        "source_url": event["source_url"],
                        "source_name": event["source_name"],
                        "category": event["category"],
                        "image_url": event["image_url"],
                        "rsvp_url": event["rsvp_url"],
                        "has_free_food": bool(event["has_free_food"]),
                        "dedup_key": event["dedup_key"],
                        "now": datetime.now(),
                    },
                )
                inserted += 1

            # Delete remote events that no longer exist locally
            local_keys = {e["dedup_key"] for e in events}
            remote_result = await session.execute(
                text("SELECT id, dedup_key FROM events")
            )
            remote_events = remote_result.fetchall()
            deleted = 0
            for remote_id, remote_key in remote_events:
                if remote_key not in local_keys:
                    await session.execute(
                        text("DELETE FROM events WHERE id = :id"),
                        {"id": remote_id},
                    )
                    deleted += 1

            await session.commit()

        await engine.dispose()
        logger.info("Synced %d new, %d deleted from remote (%d total local)", inserted, deleted, len(events))

    except Exception as exc:
        logger.exception("Remote sync failed: %s", exc)


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
        try:
            results["instagram"] = await asyncio.wait_for(
                run_instagram(logger), timeout=3600,  # 1 hour hard cap
            )
        except asyncio.TimeoutError:
            logger.error("Instagram scrape timed out after 1 hour — aborting")
            results["instagram"] = {"error": "timeout_1h"}
        state["last_instagram_run"] = datetime.now().isoformat()
    elif not ollama_ok:
        logger.warning("Skipping Instagram — Ollama not running")
    else:
        logger.info("Would scrape Instagram (batch of 50)")

    # 4. Clean up past events
    if not dry_run:
        clean_past_events(logger)

    # 5. Sync to remote Postgres (deployed site)
    if not dry_run:
        await sync_to_remote(logger)

    # Save state
    state["last_run"] = datetime.now().isoformat()
    state["last_results"] = results
    if not dry_run:
        save_state(state)

    # Schedule next wake if between 10 PM and 5 AM (overnight runs)
    schedule_next_wake(logger)

    # Summary
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
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
