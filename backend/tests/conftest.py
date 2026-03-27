"""Shared test fixtures for the NU Events test suite.

Provides an async test client backed by an in-memory SQLite database,
plus sample event data for reuse across tests.
"""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.main import create_app
from src.models.event import Base
from src.database.session import get_db
from src.schemas.event import EventCreate
from src.models.event import EventCategory

# In-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite://"


@pytest_asyncio.fixture
async def db_engine():
    """Create a fresh in-memory database engine for each test."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Provide an async session bound to the test database."""
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine):
    """Async HTTP test client with dependency-overridden database."""
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_event_data() -> dict:
    """Return a dictionary suitable for creating a test event via API."""
    return {
        "title": "Intro to Machine Learning Workshop",
        "description": "A hands-on workshop on ML fundamentals.",
        "start_time": (datetime.now() + timedelta(days=1)).isoformat(),
        "end_time": (datetime.now() + timedelta(days=1, hours=2)).isoformat(),
        "location": "Tech Auditorium, Mudd Library",
        "source_url": "https://events.northwestern.edu/ml-workshop",
        "source_name": "Northwestern Events",
        "category": "academic",
        "tags": {"department": "CS"},
        "image_url": "https://example.com/ml.jpg",
    }


@pytest.fixture
def sample_event_create() -> EventCreate:
    """Return an EventCreate schema instance for service-layer tests."""
    return EventCreate(
        title="Intro to Machine Learning Workshop",
        description="A hands-on workshop on ML fundamentals.",
        start_time=datetime.now() + timedelta(days=1),
        end_time=datetime.now() + timedelta(days=1, hours=2),
        location="Tech Auditorium, Mudd Library",
        source_url="https://events.northwestern.edu/ml-workshop",
        source_name="Northwestern Events",
        category=EventCategory.ACADEMIC,
        tags={"department": "CS"},
        image_url="https://example.com/ml.jpg",
    )
