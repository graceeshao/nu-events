"""Seed the database with sample events for development.

Usage:
    cd backend && python ../scripts/seed_data.py
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from src.database.session import async_session_factory, engine
from src.models.event import Base, EventCategory
from src.schemas.event import EventCreate
from src.services.event_service import create_event

SAMPLE_EVENTS = [
    EventCreate(
        title="Intro to Machine Learning Workshop",
        description="A beginner-friendly workshop covering the fundamentals of ML, including supervised and unsupervised learning. Bring your laptop!",
        start_time=datetime.now() + timedelta(days=2, hours=3),
        end_time=datetime.now() + timedelta(days=2, hours=5),
        location="Tech Auditorium, Mudd Library",
        source_url="https://events.northwestern.edu/ml-workshop",
        source_name="Northwestern Events",
        category=EventCategory.ACADEMIC,
        tags={"department": "CS", "level": "beginner"},
    ),
    EventCreate(
        title="Spring Fling 2025",
        description="Annual spring celebration with food trucks, live music, and games on Deering Meadow.",
        start_time=datetime.now() + timedelta(days=5, hours=6),
        end_time=datetime.now() + timedelta(days=5, hours=12),
        location="Deering Meadow",
        source_name="ASG",
        category=EventCategory.SOCIAL,
        tags={"annual": True},
    ),
    EventCreate(
        title="Goldman Sachs Info Session",
        description="Learn about internship and full-time opportunities at Goldman Sachs. Pizza provided.",
        start_time=datetime.now() + timedelta(days=3, hours=4),
        end_time=datetime.now() + timedelta(days=3, hours=5, minutes=30),
        location="Kresge 2-410",
        source_name="Northwestern Career Advancement",
        category=EventCategory.CAREER,
    ),
    EventCreate(
        title="Bienen School: Spring Recital",
        description="Student chamber music performances featuring works by Brahms and Dvořák.",
        start_time=datetime.now() + timedelta(days=7, hours=8),
        end_time=datetime.now() + timedelta(days=7, hours=10),
        location="Pick-Staiger Concert Hall",
        source_url="https://music.northwestern.edu/recitals",
        source_name="Bienen School of Music",
        category=EventCategory.ARTS,
    ),
    EventCreate(
        title="Wildcats vs. Michigan — Big Ten Baseball",
        description="Come support the Wildcats in this key Big Ten matchup!",
        start_time=datetime.now() + timedelta(days=4, hours=7),
        end_time=datetime.now() + timedelta(days=4, hours=10),
        location="Rocky Miller Park",
        source_url="https://nusports.com",
        source_name="NU Sports",
        category=EventCategory.SPORTS,
    ),
    EventCreate(
        title="Sustainability Panel: Campus Carbon Neutrality",
        description="Faculty and student leaders discuss Northwestern's path to carbon neutrality by 2030.",
        start_time=datetime.now() + timedelta(days=6, hours=5),
        end_time=datetime.now() + timedelta(days=6, hours=6, minutes=30),
        location="Harris Hall 107",
        source_name="Office of Sustainability",
        category=EventCategory.ACADEMIC,
        tags={"topic": "sustainability"},
    ),
    EventCreate(
        title="Open Mic Night",
        description="Share your poetry, music, comedy, or anything creative. Sign up at the door.",
        start_time=datetime.now() + timedelta(days=1, hours=9),
        end_time=datetime.now() + timedelta(days=1, hours=11),
        location="The Cabin, Norris University Center",
        source_name="Student Activities",
        category=EventCategory.ARTS,
    ),
    EventCreate(
        title="Hackathon: WildHacks 2025",
        description="Northwestern's premier 36-hour hackathon. Build something amazing with 500+ hackers.",
        start_time=datetime.now() + timedelta(days=10, hours=6),
        end_time=datetime.now() + timedelta(days=11, hours=18),
        location="Technological Institute",
        source_url="https://wildhacks.net",
        source_name="WildHacks",
        category=EventCategory.ACADEMIC,
        tags={"type": "hackathon", "duration_hours": 36},
    ),
]


async def main() -> None:
    """Seed the database with sample events."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        for event_in in SAMPLE_EVENTS:
            event = await create_event(session, event_in)
            print(f"  ✓ {event.title}")
        await session.commit()

    await engine.dispose()
    print(f"\nSeeded {len(SAMPLE_EVENTS)} events.")


if __name__ == "__main__":
    asyncio.run(main())
