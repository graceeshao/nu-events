# 🟣 NU Events — Northwestern Campus Event Aggregator

A unified platform that aggregates events from across Northwestern University's campus — scraping PlanIt Purple, ingesting LISTSERV emails via a local LLM, and displaying everything in one searchable, filterable website.

**Built for students who are tired of missing events because they're scattered across 50 different sources.**

## How It Works

```
                    ┌──────────────────────┐
                    │   PlanIt Purple      │
                    │   (NU events site)   │
                    └──────────┬───────────┘
                               │ Scraper (130+ events)
                               ▼
┌────────────┐    ┌─────────────────────────┐    ┌──────────────────┐
│  LISTSERV  │───▶│      Gmail Inbox        │    │                  │
│  Emails    │    │   (NU-Events label)     │    │   Frontend       │
│ from 176+  │    └──────────┬──────────────┘    │   (Next.js)      │
│  campus    │               │ IMAP Poller       │                  │
│  lists     │               ▼                   │  Search/Filter   │
└────────────┘    ┌─────────────────────────┐    │  Category browse │
                  │   LLM Classifier        │    │  Event details   │
                  │   (Gemma 4B via Ollama) │    │  Org directory   │
                  │   EVENT or NOT_EVENT    │    │                  │
                  └──────────┬──────────────┘    └────────▲─────────┘
                             │ if EVENT                   │
                             ▼                            │ REST API
                  ┌─────────────────────────┐             │
                  │   LLM Extractor         │    ┌───────┴──────────┐
                  │   → title, date, time,  │    │   FastAPI Backend │
                  │     location, desc,     │───▶│   /events         │
                  │     RSVP, free food     │    │   /organizations  │
                  └──────────┬──────────────┘    │   /ingest         │
                             │                   │   /scrapers       │
                             ▼                   │   /poller         │
                  ┌─────────────────────────┐    └──────────────────┘
                  │      Events DB          │
                  │  (SQLite / Postgres)    │
                  │  + 553 Organizations    │
                  │  + Ingested Emails log  │
                  └─────────────────────────┘
```

## Data Sources

| Source | Method | Status |
|--------|--------|--------|
| **PlanIt Purple** (planitpurple.northwestern.edu) | Web scraper — parses event cards, pagination, category mapping | ✅ Working (130+ events) |
| **NU LISTSERV emails** (176+ student org lists) | Gmail IMAP poller → LLM classifier → LLM extractor | ✅ Working |
| **Manual submission** | `POST /ingest/email` or `/ingest/raw` API endpoints | ✅ Working |
| **Organization directory** | 553 orgs from Cats on Campus PDF (Greek orgs excluded) | ✅ Seeded |

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- [Ollama](https://ollama.com) (for LLM-based email parsing)

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install python-dateutil google-auth google-auth-oauthlib google-auth-httplib2 ollama

# Start the API server (auto-creates SQLite DB)
uvicorn src.main:app --reload --port 8000

# Seed organizations (553 campus orgs)
python scripts/seed_organizations.py

# Scrape PlanIt Purple for live events
curl -X POST http://localhost:8000/scrapers/planitpurple/run

# Run tests (169 tests)
pytest -v
```

### 2. Ollama (LLM for email parsing)

```bash
# Install Ollama
brew install ollama
brew services start ollama

# Pull the model (~3.3GB)
ollama pull gemma3:4b
```

The LLM parser automatically falls back to regex if Ollama isn't running.

### 3. Frontend

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
# → http://localhost:3000
```

### 4. Gmail Poller (for LISTSERV emails)

See [Gmail Poller Setup](#gmail-poller-setup) below.

## Email Parsing Pipeline

Emails go through a two-stage LLM pipeline:

1. **Pre-filters** — Instantly reject subscription confirmations, welcome messages, job postings (`[POSTING]`), election/voting emails, pre-registration notices, and application deadlines. No LLM call needed.

2. **LLM Classification** (Gemma 4B) — "Is this email about an attendable event?" Uses few-shot examples to distinguish real events from course announcements, recruiting emails, and newsletters.

3. **LLM Extraction** — For confirmed events, extracts: clean title, date, time, location, description, RSVP URL, free food flag, and category. Returns structured JSON.

4. **Regex fallback** — If Ollama is down, falls back to a regex-based parser with 40+ NU building names, date/time patterns, confidence scoring, and LISTSERV header matching.

### Features detected:
- 🍕 **Free food** — "free pizza", "food provided", "complimentary refreshments"
- 🔗 **RSVP links** — Eventbrite, Google Forms, lu.ma, bit.ly
- 📍 **NU locations** — 40+ known buildings (Norris, Tech, Kresge, etc.)
- 🏷️ **Categories** — academic, social, career, arts, sports, other
- 🏢 **Organization matching** — from LISTSERV List-Id/Sender headers

## API Reference

### Events
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/events` | List events (filters: `category`, `date_from`, `date_to`, `search`, `page`, `page_size`) |
| `GET` | `/events/{id}` | Get single event |
| `POST` | `/events` | Create event manually |
| `PATCH` | `/events/{id}` | Partial update |
| `DELETE` | `/events/{id}` | Delete event |

### Organizations
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/organizations` | List orgs (filters: `category`, `search`, `page`, `page_size`) |
| `GET` | `/organizations/{id}` | Get single org |
| `POST` | `/organizations` | Create org |
| `PATCH` | `/organizations/{id}` | Update org |
| `DELETE` | `/organizations/{id}` | Delete org |

### Email Ingestion
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/ingest/email` | JSON: `{subject, body, sender, list_id, list_sender}` |
| `POST` | `/ingest/raw` | Raw RFC 822 email text |

### Scrapers & Poller
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/scrapers` | List registered scrapers |
| `POST` | `/scrapers/{name}/run` | Trigger a scraper |
| `POST` | `/poller/trigger` | Trigger one Gmail poll cycle |
| `GET` | `/poller/status` | Check poller config and last run |

Full API docs with examples: [docs/API.md](docs/API.md)

## Gmail Poller Setup

### One-Time Setup

1. **Google Cloud OAuth** (use a personal Google account if NU blocks Cloud Console):
   - [console.cloud.google.com](https://console.cloud.google.com) → Create project → Enable **Gmail API**
   - Create **OAuth 2.0 credentials** (Desktop app) → Download JSON → save as `backend/credentials.json`

2. **Gmail label + filter:**
   - Create label: `NU-Events`
   - Create filter: Has the words `list:listserv.it.northwestern.edu` → Skip Inbox, Apply label `NU-Events`

3. **Subscribe to LISTSERV lists** — Email `LISTSERV@LISTSERV.IT.NORTHWESTERN.EDU`:
   ```
   SUBSCRIBE LISTNAME Your Name
   ```

4. **Authorize:** `python scripts/gmail_auth.py` (opens browser, log in with NU account)

5. **Run:**
   ```bash
   export GMAIL_USER_EMAIL=you@u.northwestern.edu
   python scripts/run_poller.py          # continuous (every 15 min)
   python scripts/run_poller.py --once   # one-shot
   ```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./nu_events.db` | Database connection |
| `API_KEY` | *(empty)* | If set, required on POST/PATCH/DELETE |
| `CORS_ORIGINS` | `localhost:3000,3001,3002` | Allowed frontend origins |
| `GMAIL_USER_EMAIL` | *(empty)* | Your NU Gmail for IMAP auth |
| `GMAIL_CREDENTIALS_FILE` | `credentials.json` | OAuth client-secret JSON |
| `GMAIL_TOKEN_FILE` | `token.json` | Saved OAuth token |
| `GMAIL_LABEL` | `NU-Events` | Gmail label to poll |
| `GMAIL_POLL_INTERVAL_SECONDS` | `900` | Poll interval (seconds) |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `gemma3:4b` | LLM model for email parsing |
| `USE_LLM_PARSER` | `true` | Set `false` to use regex-only parser |

## Project Structure

```
nu-events/
├── backend/
│   ├── src/
│   │   ├── api/routes/           # FastAPI endpoints (events, orgs, ingest, scrapers, poller)
│   │   ├── models/               # SQLAlchemy: Event, Organization, IngestedEmail
│   │   ├── schemas/              # Pydantic request/response schemas
│   │   ├── scrapers/             # PlanIt Purple scraper + base class
│   │   ├── services/             # Business logic
│   │   │   ├── llm_parser.py     #   Ollama/Gemma LLM classification + extraction
│   │   │   ├── email_parser.py   #   Regex fallback parser
│   │   │   ├── gmail_poller.py   #   IMAP polling with OAuth2
│   │   │   ├── event_service.py  #   CRUD + deduplication
│   │   │   └── dedup.py          #   SHA-256 dedup keys
│   │   ├── middleware/auth.py    # Optional API key auth
│   │   ├── config.py             # Env-based settings
│   │   └── main.py               # FastAPI app factory
│   ├── tests/                    # 169 pytest tests
│   ├── data/organizations.json   # 553 NU orgs (no Greek)
│   └── pyproject.toml
├── frontend/                     # Next.js 14 + TypeScript + Tailwind
│   └── src/
│       ├── app/                  # Pages: home, events/[id], organizations
│       ├── components/           # EventCard, FilterBar, Pagination, Header
│       ├── hooks/                # useEvents (debounced search)
│       └── lib/                  # API client, types, utils
├── scripts/                      # CLI: gmail_auth, run_poller, run_scrapers, seed
├── docs/                         # ARCHITECTURE.md, SETUP.md, DEVELOPMENT.md, API.md
└── docker-compose.yml
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, SQLAlchemy (async), Pydantic |
| Frontend | Next.js 14, React 18, TypeScript, Tailwind CSS |
| Database | SQLite (local) → Postgres (production) via `DATABASE_URL` |
| LLM | Ollama + Gemma 4B (local, free, no API key) |
| Scraping | httpx, BeautifulSoup4 |
| Email | imaplib, Google OAuth2, python-dateutil |
| Testing | pytest, pytest-asyncio (169 tests) |

## Running Tests

```bash
cd backend
pytest -v              # all 169 tests
pytest -k "llm"        # LLM parser tests
pytest -k "email"      # email parser tests
pytest -k "api"        # API endpoint tests
```

## Contributing

1. Fork & create a feature branch
2. Write tests for new functionality
3. All tests must pass (`pytest -v`)
4. Type hints and docstrings on everything
5. Open a PR

## License

MIT
