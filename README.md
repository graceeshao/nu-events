# 🟣 NU Events — Northwestern Campus Event Aggregator

A unified platform that scrapes, aggregates, and displays events from across Northwestern University's campus. Built for students, by students.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                │
│         React + TypeScript + Tailwind CSS            │
│              http://localhost:3000                    │
└──────────────────────┬──────────────────────────────┘
                       │  REST API
┌──────────────────────▼──────────────────────────────┐
│                  Backend (FastAPI)                    │
│              http://localhost:8000                    │
│                                                      │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │  Routes   │  │ Services  │  │    Scrapers      │  │
│  │ /events   │──│  dedup    │  │  base.py         │  │
│  │ /scrapers │  │  CRUD     │  │  northwestern.py │  │
│  └──────────┘  └─────┬─────┘  │  (add more!)     │  │
│                      │        └──────────────────┘  │
│               ┌──────▼──────┐                        │
│               │  SQLAlchemy │                        │
│               │   (async)   │                        │
│               └──────┬──────┘                        │
│                      │                               │
│               ┌──────▼──────┐                        │
│               │   SQLite    │  ← swap to Postgres    │
│               │  (aiosqlite)│    via DATABASE_URL     │
│               └─────────────┘                        │
└──────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- (Optional) Docker & Docker Compose

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Run the API server
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest -v

# Seed sample data
python ../scripts/seed_data.py

# Run scrapers
python ../scripts/run_scrapers.py              # all scrapers
python ../scripts/run_scrapers.py --scraper northwestern_events  # specific one
```

### Frontend

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
# → http://localhost:3000
```

### Docker (both services)

```bash
docker compose up --build
# Backend → http://localhost:8000
# Frontend → http://localhost:3000
```

## Adding a New Scraper

1. Create a file in `backend/src/scrapers/`, e.g. `my_source.py`:

```python
"""Scraper for My Event Source."""

import httpx
from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper
from src.schemas.event import EventCreate


class MySourceScraper(BaseScraper):
    name = "my_source"
    base_url = "https://example.com/events"

    async def fetch(self) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.get(self.base_url)
            response.raise_for_status()
            return response.text

    async def parse(self, raw_data: str) -> list[EventCreate]:
        soup = BeautifulSoup(raw_data, "html.parser")
        events: list[EventCreate] = []
        # ... parse HTML into EventCreate objects ...
        return events
```

2. Register it in `backend/src/scrapers/__init__.py`:

```python
from src.scrapers.my_source import MySourceScraper
SCRAPER_REGISTRY["my_source"] = MySourceScraper()
```

3. Test it: `POST http://localhost:8000/scrapers/my_source/run`

## Running Tests

```bash
cd backend
pytest -v                    # all tests
pytest tests/test_api.py     # specific file
pytest -k "test_create"      # by name pattern
pytest --cov=src             # with coverage (install pytest-cov)
```

## Project Structure

| Directory | Purpose |
|-----------|---------|
| `backend/src/api/` | FastAPI route handlers |
| `backend/src/models/` | SQLAlchemy ORM models |
| `backend/src/schemas/` | Pydantic request/response schemas |
| `backend/src/scrapers/` | Modular event scrapers |
| `backend/src/services/` | Business logic layer |
| `backend/src/database/` | DB engine and session management |
| `backend/tests/` | Pytest test suite |
| `frontend/src/app/` | Next.js pages and layout |
| `frontend/src/components/` | React UI components |
| `frontend/src/lib/` | API client and shared types |
| `frontend/src/hooks/` | Custom React hooks |
| `scripts/` | CLI utilities for scraping and seeding |

## Tech Stack

- **Backend:** Python, FastAPI, SQLAlchemy (async), aiosqlite, Pydantic
- **Frontend:** Next.js 14, React 18, TypeScript, Tailwind CSS
- **Database:** SQLite (local) — Postgres-ready via `DATABASE_URL`
- **Scraping:** httpx, BeautifulSoup4

## Contributing

1. Fork the repo and create a feature branch (`git checkout -b feature/my-scraper`)
2. Write tests for any new functionality
3. Make sure all tests pass (`pytest -v`)
4. Follow existing code style (type hints, docstrings)
5. Open a PR with a clear description of changes

### Code Style

- Python: type hints on all functions, module-level docstrings on every file
- TypeScript: explicit types, no `any` unless unavoidable
- Commits: conventional style (`feat:`, `fix:`, `docs:`, `test:`)

## License

MIT
