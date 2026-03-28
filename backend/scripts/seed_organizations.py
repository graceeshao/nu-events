"""Seed the organizations table from data/organizations.json.

Usage:
    cd backend
    .venv/bin/python -m scripts.seed_organizations

Or:
    .venv/bin/python scripts/seed_organizations.py
"""

import asyncio
import json
import sys
from pathlib import Path

# Ensure the backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from src.database.session import engine, async_session_factory
from src.models.event import Base
from src.models.organization import Organization


DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "organizations.json"


async def seed() -> None:
    """Load organizations from JSON and upsert into the database."""
    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    with open(DATA_PATH) as f:
        orgs_data: list[dict] = json.load(f)

    async with async_session_factory() as session:
        created = 0
        skipped = 0
        for org_dict in orgs_data:
            # Check if org already exists by name
            result = await session.execute(
                select(Organization).where(Organization.name == org_dict["name"])
            )
            if result.scalar_one_or_none() is not None:
                skipped += 1
                continue

            org = Organization(
                name=org_dict["name"],
                category=org_dict.get("category", "RSO"),
                tags=org_dict.get("tags"),
                club_id=org_dict.get("club_id"),
                instagram_handle=org_dict.get("instagram_handle"),
                website=org_dict.get("website"),
                email=org_dict.get("email"),
                listserv_name=org_dict.get("listserv_name"),
            )
            session.add(org)
            created += 1

        await session.commit()
        print(f"Seeded {created} organizations ({skipped} already existed).")


if __name__ == "__main__":
    asyncio.run(seed())
