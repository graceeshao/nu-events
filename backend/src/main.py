"""FastAPI application factory.

Creates the app with CORS middleware, lifespan events, and route registration.
Tables are created on startup so the app works out of the box with SQLite.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.database.session import engine
from src.models.event import Base
import src.models.organization  # noqa: F401 — register Organization with Base
import src.models.email_ingest  # noqa: F401 — register IngestedEmail with Base
from src.api.routes.events import router as events_router
from src.api.routes.scrapers import router as scrapers_router
from src.api.routes.organizations import router as organizations_router
from src.api.routes.ingest import router as ingest_router
from src.api.routes.poller import router as poller_router
from src.api.routes.instagram import router as instagram_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: create tables on startup, dispose engine on shutdown."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        description="Aggregated campus events from across Northwestern University",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(events_router, prefix="/events", tags=["events"])
    app.include_router(scrapers_router, prefix="/scrapers", tags=["scrapers"])
    app.include_router(organizations_router, prefix="/organizations", tags=["organizations"])
    app.include_router(ingest_router, prefix="/ingest", tags=["ingest"])
    app.include_router(poller_router, prefix="/poller", tags=["poller"])
    app.include_router(instagram_router, prefix="/instagram", tags=["instagram"])

    @app.get("/", tags=["health"])
    async def root() -> dict[str, str]:
        """Health-check endpoint."""
        return {"status": "ok", "app": settings.app_name}

    return app


app = create_app()
