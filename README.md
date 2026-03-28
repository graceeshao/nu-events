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

## Gmail Poller Setup

The Gmail poller monitors a Gmail label for event announcement emails and automatically ingests them into the database.

### Prerequisites

1. **Google Cloud Project** with the Gmail API enabled
2. **OAuth 2.0 Client ID** (Desktop application type) — download the JSON as `credentials.json`
3. A Gmail label (default: `NU-Events`) with a filter routing event emails into it

### Step-by-Step Setup

1. **Create a Google Cloud project** at [console.cloud.google.com](https://console.cloud.google.com)
2. Enable the **Gmail API**
3. Create **OAuth 2.0 credentials** → Desktop app → Download JSON
4. Place the file as `credentials.json` in the project root (or wherever `GMAIL_CREDENTIALS_FILE` points)
5. **Create the Gmail label:**
   - In Gmail → Settings → Labels → Create new label: `NU-Events`
   - Set up a filter (e.g. `from:*@u.northwestern.edu`) to auto-label incoming event emails
6. **Run the auth script** (one-time):
   ```bash
   cd backend
   python ../scripts/gmail_auth.py
   ```
   This opens a browser for Google sign-in and saves `token.json`.
7. **Run the poller:**
   ```bash
   # Continuous mode (polls every 15 minutes)
   python ../scripts/run_poller.py

   # Single poll (useful for cron)
   python ../scripts/run_poller.py --once

   # Custom interval
   python ../scripts/run_poller.py --interval 300
   ```

### API Endpoints

- `POST /poller/trigger` — manually trigger a single poll cycle
- `GET /poller/status` — check credentials config, last poll time, results

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GMAIL_CREDENTIALS_FILE` | `credentials.json` | Path to OAuth client-secret JSON |
| `GMAIL_TOKEN_FILE` | `token.json` | Path to saved OAuth token |
| `GMAIL_LABEL` | `NU-Events` | Gmail label to poll |
| `GMAIL_POLL_INTERVAL_SECONDS` | `900` | Polling interval (seconds) |

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
