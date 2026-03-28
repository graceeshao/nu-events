# NU Events — Northwestern Campus Event Aggregator

A unified platform that aggregates events from across Northwestern University's campus — scraping PlanIt Purple, ingesting LISTSERV emails, and displaying everything in one searchable, filterable website.

**Built for students who are tired of missing events because they're scattered across 50 different sources.**

## How It Works

```
                    ┌──────────────────────┐
                    │   PlanIt Purple      │
                    │   (NU events site)   │
                    └──────────┬───────────┘
                               │ Scraper
                               ▼
┌────────────┐    ┌─────────────────────────┐    ┌──────────────────┐
│  LISTSERV  │───▶│      Gmail Inbox        │    │                  │
│  Emails    │    │   (NU-Events label)     │    │   Frontend       │
│ from 38+   │    └──────────┬──────────────┘    │   (Next.js)      │
│  campus    │               │ IMAP Poller       │                  │
│  lists     │               ▼                   │  Calendar view   │
└────────────┘    ┌─────────────────────────┐    │  Search/Filter   │
                  │      Email Parser       │    │  Category browse │
                  │  (regex, NU buildings,  │───▶│                  │
                  │   date/time extraction) │    └────────▲─────────┘
                  └──────────┬──────────────┘             │
                             │                            │ REST API
                             ▼                            │
                  ┌─────────────────────────┐    ┌───────┴──────────┐
                  │      Events DB          │◀───│   FastAPI Backend │
                  │  (SQLite / Postgres)    │    │   /events         │
                  │  + Organizations DB     │    │   /organizations  │
                  │  + Ingested Emails      │    │   /ingest         │
                  └─────────────────────────┘    │   /scrapers       │
                                                 │   /poller         │
                                                 └──────────────────┘
```

## Data Sources

| Source | Method | Status |
|--------|--------|--------|
| **PlanIt Purple** (planitpurple.northwestern.edu) | Web scraper — parses event cards, handles pagination, maps NU categories 
| **NU LISTSERV emails** (38+ student org lists) | Gmail IMAP poller → email parser → event extraction
| **Manual submission** | `POST /ingest/email` or `/ingest/raw` API endpoints
| **Organization directory** | 70+ orgs seeded from AllCampusGroups PDF

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Start the API server
uvicorn src.main:app --reload --port 8000

# Run tests (114 tests)
pytest -v

# Seed organizations from PDF data
python scripts/seed_organizations.py

# Scrape PlanIt Purple
python ../scripts/run_scrapers.py
```

### 2. Frontend

```bash
cd frontend
cp .env.local.example .env.local   # sets API URL to localhost:8000
npm install
npm run dev
# → http://localhost:3000
```

### 3. Gmail Poller (for LISTSERV emails)

See [Gmail Poller Setup](#gmail-poller-setup) below.

## API Reference

### Events
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/events` | List events (filter by `category`, `date_from`, `date_to`, `search`, `page`, `page_size`) |
| `GET` | `/events/{id}` | Get single event |
| `POST` | `/events` | Create event manually |
| `PATCH` | `/events/{id}` | Update event (partial) |
| `DELETE` | `/events/{id}` | Delete event |

### Organizations
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/organizations` | List orgs (filter by `category`, `search`, `page`, `page_size`) |
| `GET` | `/organizations/{id}` | Get single org |
| `POST` | `/organizations` | Create org |
| `PATCH` | `/organizations/{id}` | Update org |
| `DELETE` | `/organizations/{id}` | Delete org |

### Email Ingestion
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/ingest/email` | Submit email as JSON (`{subject, body, sender, list_id, list_sender}`) |
| `POST` | `/ingest/raw` | Submit raw email text (RFC 822 headers + body) |

### Scrapers
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/scrapers` | List registered scrapers |
| `POST` | `/scrapers/{name}/run` | Trigger a scraper manually |

### Poller
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/poller/trigger` | Trigger one Gmail poll cycle |
| `GET` | `/poller/status` | Check poller config and last run |

## Gmail Poller Setup

The poller monitors a Gmail label for LISTSERV event emails and auto-ingests them.

### One-Time Setup

1. **Google Cloud OAuth credentials** (use a personal Google account if your NU account blocks Cloud Console):
   - Go to [console.cloud.google.com](https://console.cloud.google.com)
   - Create a project → Enable **Gmail API**
   - Create **OAuth 2.0 credentials** → Desktop app type
   - Download JSON → save as `backend/credentials.json`

2. **Gmail label + filter:**
   - Create a label called `NU-Events` in Gmail
   - Create a filter: Has the words `list:listserv.it.northwestern.edu` → Skip Inbox, Apply label `NU-Events`

3. **Subscribe to LISTSERV lists:**
   - Send an email to `LISTSERV@LISTSERV.IT.NORTHWESTERN.EDU` with body:
     ```
     SUBSCRIBE LISTNAME Your Name
     ```

4. **Authorize the app:**
   ```bash
   cd backend
   python ../scripts/gmail_auth.py
   ```
   Browser opens → log in with NU account → `token.json` is saved.

5. **Run the poller:**
   ```bash
   # Set your email
   export GMAIL_USER_EMAIL=you@u.northwestern.edu

   # Continuous (every 15 min)
   python ../scripts/run_poller.py

   # One-shot (for testing or cron)
   python ../scripts/run_poller.py --once
   ```

### How LISTSERV Email Matching Works

When a LISTSERV email arrives, the parser reads:
- `List-Id: ANIME.LISTSERV.IT.NORTHWESTERN.EDU` → identifies the list as `ANIME`
- `Sender: owner-ANIME@LISTSERV.IT.NORTHWESTERN.EDU` → backup identification

This works regardless of who the `From:` person is (e.g., `random-student@gmail.com`).

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GMAIL_CREDENTIALS_FILE` | `credentials.json` | OAuth client-secret JSON path |
| `GMAIL_TOKEN_FILE` | `token.json` | Saved OAuth token path |
| `GMAIL_USER_EMAIL` | *(empty)* | Your Gmail address for IMAP auth |
| `GMAIL_LABEL` | `NU-Events` | Gmail label to poll |
| `GMAIL_POLL_INTERVAL_SECONDS` | `900` | Poll interval (seconds) |
| `DATABASE_URL` | `sqlite+aiosqlite:///./nu_events.db` | Database connection string |
| `API_KEY` | *(empty)* | If set, required on POST/PATCH/DELETE |

## Email Parser

The parser extracts events from unstructured email text without any LLM — pure regex and heuristics:

- **Dates:** "March 27, 2026", "3/27", "this Friday", "next Tuesday"
- **Times:** "7pm", "7:00 PM - 9:00 PM", "from 3:30pm to 4:30pm"
- **Locations:** "Location: ...", "Where: ...", or 40+ known NU buildings (Norris, Tech, Kresge, etc.)
- **Organizations:** Matched from LISTSERV headers or sender email
- **Multi-event emails:** Detects line-by-line event listings

## Adding a New Scraper

1. Create `backend/src/scrapers/my_source.py`:

```python
from src.scrapers.base import BaseScraper
from src.schemas.event import EventCreate

class MySourceScraper(BaseScraper):
    name = "my_source"

    async def fetch(self) -> str:
        # Fetch raw data (HTML, JSON, etc.)
        ...

    async def parse(self, raw_data: str) -> list[EventCreate]:
        # Parse into EventCreate objects
        ...
```

2. Register in `backend/src/scrapers/__init__.py`:
```python
from src.scrapers.my_source import MySourceScraper
SCRAPER_REGISTRY["my_source"] = MySourceScraper()
```

3. Test: `POST http://localhost:8000/scrapers/my_source/run`

## Project Structure

```
nu-events/
├── backend/
│   ├── src/
│   │   ├── api/routes/         # FastAPI endpoints
│   │   │   ├── events.py       #   CRUD + filtering
│   │   │   ├── organizations.py#   Org directory
│   │   │   ├── ingest.py       #   Email ingestion
│   │   │   ├── scrapers.py     #   Scraper management
│   │   │   └── poller.py       #   Gmail poller control
│   │   ├── models/             # SQLAlchemy models
│   │   │   ├── event.py        #   Event + EventCategory enum
│   │   │   ├── organization.py #   Campus organizations
│   │   │   └── email_ingest.py #   Ingested email tracking
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── scrapers/           # Modular event scrapers
│   │   │   ├── base.py         #   Abstract base class
│   │   │   └── planitpurple.py #   PlanIt Purple scraper
│   │   ├── services/           # Business logic
│   │   │   ├── event_service.py#   Event CRUD + dedup
│   │   │   ├── email_parser.py #   Regex event extraction
│   │   │   ├── gmail_auth.py   #   Google OAuth2
│   │   │   ├── gmail_poller.py #   IMAP polling
│   │   │   └── dedup.py        #   Deduplication keys
│   │   ├── middleware/auth.py  # API key auth
│   │   ├── database/session.py # Async DB engine
│   │   ├── config.py           # Env-based settings
│   │   └── main.py             # FastAPI app factory
│   ├── tests/                  # 114 tests
│   ├── data/organizations.json # 70+ NU orgs seed data
│   └── pyproject.toml
├── frontend/                   # Next.js + TypeScript + Tailwind
├── scripts/
│   ├── gmail_auth.py           # One-time OAuth setup
│   ├── run_poller.py           # Gmail poller runner
│   ├── run_scrapers.py         # Scraper runner
│   ├── seed_data.py            # Sample event data
│   └── seed_organizations.py   # Org data from PDF
└── docker-compose.yml
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI, SQLAlchemy (async), Pydantic |
| Frontend | Next.js 14, React, TypeScript, Tailwind CSS |
| Database | SQLite (local) → Postgres (production) via `DATABASE_URL` |
| Scraping | httpx, BeautifulSoup4 |
| Email | imaplib, Google OAuth2, python-dateutil |
| Testing | pytest, pytest-asyncio (114 tests) |

## Running Tests

```bash
cd backend
pytest -v                    # all 114 tests
pytest tests/test_api.py     # specific file
pytest -k "listserv"         # by keyword
```

## Contributing

1. Fork & create a feature branch
2. Write tests for new functionality
3. Ensure all tests pass (`pytest -v`)
4. Follow existing code style (type hints, docstrings on everything)
5. Open a PR

## License

MIT
