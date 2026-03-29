#!/usr/bin/env python3
"""Sync local SQLite events to the remote Postgres database.

Reads from local nu_events.db and pushes future events to the
remote DATABASE_URL. Run after each local scrape to keep the
deployed site up to date.

Usage:
    DATABASE_URL=postgresql://... python scripts/sync_to_remote.py
"""

import asyncio
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def sync():
    remote_url = os.environ.get("DATABASE_URL", "")
    if not remote_url:
        print("Set DATABASE_URL env var to the remote Postgres connection string")
        sys.exit(1)

    # Fix URL for asyncpg
    if remote_url.startswith("postgres://"):
        remote_url = remote_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif remote_url.startswith("postgresql://") and "+asyncpg" not in remote_url:
        remote_url = remote_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy import text

    # Read from local SQLite
    local_db = Path(__file__).parent.parent / "nu_events.db"
    conn = sqlite3.connect(str(local_db))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Get all future events
    events = c.execute("""
        SELECT title, description, start_time, end_time, location,
               source_url, source_name, category, image_url, rsvp_url,
               has_free_food, dedup_key
        FROM events
        WHERE start_time >= datetime('now')
        ORDER BY start_time
    """).fetchall()

    print(f"Local: {len(events)} future events to sync")

    # Connect to remote
    engine = create_async_engine(remote_url)

    # Create tables if needed
    from src.models.event import Base
    import src.models.organization
    import src.models.email_ingest

    async with engine.begin() as conn_remote:
        await conn_remote.run_sync(Base.metadata.create_all)

    # Upsert events
    async with async_sessionmaker(engine, class_=AsyncSession)() as session:
        inserted = 0
        skipped = 0

        for event in events:
            # Check if exists by dedup_key
            result = await session.execute(
                text("SELECT id FROM events WHERE dedup_key = :key"),
                {"key": event["dedup_key"]},
            )
            if result.scalar_one_or_none() is not None:
                skipped += 1
                continue

            def parse_dt(s):
                """Convert SQLite datetime string to Python datetime."""
                if not s:
                    return None
                try:
                    return datetime.fromisoformat(s.replace(".000000", ""))
                except (ValueError, AttributeError):
                    return None

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

        await session.commit()

    await engine.dispose()
    conn.close()

    print(f"Synced: {inserted} new, {skipped} already existed")


if __name__ == "__main__":
    asyncio.run(sync())
