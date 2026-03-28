# Development Guide

How to work on and extend NU Events.

## Project Structure

```
nu-events/
├── backend/
│   ├── src/
│   │   ├── api/routes/           # FastAPI endpoint handlers
│   │   │   ├── events.py        #   GET/POST/PATCH/DELETE /events
│   │   │   ├── organizations.py #   GET/POST/PATCH/DELETE /organizations
│   │   │   ├── ingest.py        #   POST /ingest/email, /ingest/raw
│   │   │   ├── scrapers.py      #   GET /scrapers, POST /scrapers/{name}/run
│   │   │   └── poller.py        #   GET /poller/status, POST /poller/trigger
│   │   ├── models/               # SQLAlchemy ORM models
│   │   │   ├── event.py         #   Event + EventCategory enum + Base
│   │   │   ├── organization.py  #   Organization
│   │   │   └── email_ingest.py  #   IngestedEmail
│   │   ├── schemas/              # Pydantic request/response schemas
│   │   │   ├── event.py         #   EventCreate, EventRead, EventUpdate, EventList
│   │   │   └── organization.py  #   OrganizationCreate, OrganizationRead, etc.
│   │   ├── scrapers/             # Modular event scrapers
│   │   │   ├── base.py          #   Abstract BaseScraper class
│   │   │   └── planitpurple.py  #   PlanIt Purple scraper
│   │   ├── services/             # Business logic
│   │   │   ├── event_service.py #   CRUD with dedup
│   │   │   ├── llm_parser.py    #   LLM classification + extraction (Ollama/Gemma)
│   │   │   ├── email_parser.py  #   Regex fallback parser
│   │   │   ├── gmail_auth.py    #   Google OAuth2 helpers
│   │   │   ├── gmail_poller.py  #   IMAP polling logic
│   │   │   ├── organization_service.py
│   │   │   └── dedup.py         #   Dedup key generation
│   │   ├── middleware/auth.py    # API key middleware
│   │   ├── database/session.py   # Async SQLAlchemy engine
│   │   ├── config.py             # Pydantic settings
│   │   └── main.py               # FastAPI app factory
│   ├── tests/                     # 114 pytest tests
│   ├── data/organizations.json    # Org seed data
│   └── pyproject.toml
├── frontend/                      # Next.js app
│   └── src/
│       ├── app/                   # Pages (Next.js App Router)
│       ├── components/            # React components
│       ├── hooks/                 # Custom hooks
│       └── lib/                   # API client, types, utils
├── scripts/                       # CLI tools
│   ├── gmail_auth.py             # One-time OAuth setup
│   ├── run_poller.py             # Gmail poller runner
│   ├── run_scrapers.py           # Run all/specific scrapers
│   ├── seed_data.py              # Sample events
│   └── seed_organizations.py     # Seed orgs from JSON
├── docs/                          # Documentation
└── docker-compose.yml
```

## Adding a New Scraper

Scrapers are modular — each is a Python class that fetches data from a source and returns `EventCreate` objects.

### 1. Create the scraper file

`backend/src/scrapers/my_source.py`:

```python
"""Scraper for My Event Source."""

import httpx
from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper
from src.schemas.event import EventCreate
from src.models.event import EventCategory


class MySourceScraper(BaseScraper):
    """Scrapes events from example.com."""

    name = "my_source"
    base_url = "https://example.com/events"

    async def fetch(self) -> str:
        """Fetch raw HTML from the source."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(self.base_url)
            response.raise_for_status()
            return response.text

    async def parse(self, raw_data: str) -> list[EventCreate]:
        """Parse HTML into EventCreate objects."""
        soup = BeautifulSoup(raw_data, "html.parser")
        events: list[EventCreate] = []

        for card in soup.select(".event-card"):
            title = card.select_one("h3").get_text(strip=True)
            # ... extract other fields ...

            events.append(EventCreate(
                title=title,
                start_time=start_time,
                location=location,
                source_url=f"{self.base_url}/{event_id}",
                source_name="My Source",
                category=EventCategory.OTHER,
            ))

        return events
```

### 2. Register it

In `backend/src/scrapers/__init__.py`:

```python
from src.scrapers.my_source import MySourceScraper

SCRAPER_REGISTRY["my_source"] = MySourceScraper()
```

### 3. Test it

```python
# tests/test_scrapers.py
class TestMySourceScraper:
    @pytest.mark.asyncio
    async def test_parse_event(self):
        scraper = MySourceScraper()
        html = '<div class="event-card"><h3>Test Event</h3>...</div>'
        events = await scraper.parse(html)
        assert len(events) == 1
```

### 4. Run it

```bash
curl -X POST http://localhost:8000/scrapers/my_source/run
```

## Adding a New Email Pattern

The email parser (`src/services/email_parser.py`) uses regex to extract event data. To handle a new pattern:

### Date patterns
Add to the appropriate regex in `email_parser.py`:
- `_DATE_LONG_RE` — "March 27, 2026"
- `_DATE_NUMERIC_RE` — "3/27/2026"
- `_RELATIVE_DAY_RE` — "this Friday"

### Time patterns
- `_TIME_RE` — single times
- `_TIME_RANGE_RE` — time ranges

### Location patterns
- Add building names to `NU_BUILDINGS` list
- Add labeled patterns to `_LOCATION_LABEL_RE`

### Testing

Always add test cases for new patterns:

```python
# tests/test_email_parser.py
def test_my_new_date_format(self):
    dates = extract_dates("Event on 2026-03-28T19:00:00")
    assert len(dates) == 1
    assert dates[0] == date(2026, 3, 28)
```

## Code Conventions

### Python (backend)
- **Type hints** on all function signatures
- **Docstrings** on all modules, classes, and public functions
- **Async** for all database and HTTP operations
- **Pydantic** for all request/response validation
- Run `pytest -v` before committing

### TypeScript (frontend)
- Explicit types (avoid `any`)
- Client components marked with `"use client"`
- Server components for data fetching (event detail page)
- `date-fns` for all date formatting

### Git Commits
Use conventional commit style:
- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation
- `test:` — test additions
- `refactor:` — code restructuring

## Database Migrations

The project uses Alembic for migrations (configured but not required for SQLite dev):

```bash
cd backend

# Create a new migration
alembic revision --autogenerate -m "add_new_field"

# Apply migrations
alembic upgrade head
```

For local development, the app auto-creates tables on startup via `Base.metadata.create_all()`. Delete `nu_events.db` and restart to reset.

## Testing

```bash
cd backend

# Run all tests
pytest -v

# Run specific test file
pytest tests/test_email_parser.py -v

# Run tests matching a pattern
pytest -k "listserv" -v

# Run with coverage
pip install pytest-cov
pytest --cov=src --cov-report=term-missing
```

## Future Improvements

### More data sources
- Instagram scraper (public org profiles)
- Department calendar scraping (Google Calendar API for public calendars)
- Daily Northwestern events section

### Frontend
- Calendar view (month/week/day)
- Event notifications/subscriptions
- PWA support for mobile
- Dark mode

### Infrastructure
- PostgreSQL for production
- Redis for caching
- Background task queue (Celery) for scraper scheduling
- Docker deployment
- CI/CD with GitHub Actions
