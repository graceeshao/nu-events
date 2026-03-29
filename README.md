# 🟣 NU Events — Northwestern Campus Event Aggregator

**Live site: [nu-events.vercel.app](https://nu-events.vercel.app)**

A unified platform that aggregates events from across Northwestern University's campus — scraping PlanIt Purple, ingesting LISTSERV emails, and scraping 427 student org Instagram accounts, all classified by a local LLM running on your Mac.

**Built for students who are tired of missing events because they're scattered across 50 different sources.**

## How It Works

```
YOUR MAC (scraping + LLM)                    CLOUD (serving)
─────────────────────────                    ───────────────

┌─────────────────────┐                      
│  Scheduler (1.5h)   │                      
│                     │                      
│  PlanIt Purple ─────┤  JSON-LD             
│  Gmail LISTSERV ────┤  IMAP + Ollama       
│  Instagram (427) ───┤  REST API + Ollama   
│                     │                      
│  Gemma 12B (local)  │                      
│  3-layer filter     │                      
│  Event validator    │                      
│         │           │                      
│    SQLite (local)   │                      
│         │           │    sync_to_remote    
│         └───────────┼──────────────────→  Render Postgres
│                     │                          │
└─────────────────────┘                          │
                                                 ▼
                                          Render (FastAPI)
                                          nu-events-api.onrender.com
                                                 │
                                                 ▼
                                          Vercel (Next.js)
                                          nu-events.vercel.app
                                                 │
                                                 ▼
                                          Students browse events
```

## Data Sources

| Source | Method | Events | Cost |
|--------|--------|:------:|:----:|
| **PlanIt Purple** | JSON-LD from detail pages | ~180 | $0 |
| **NU LISTSERV emails** (176+ lists) | Gmail IMAP → Gemma 12B LLM | ~10 | $0 |
| **Instagram** (427 org accounts) | REST API → prefilter → Gemma 12B | growing | $0 |
| **Manual submission** | POST API endpoints | — | $0 |

**Total: ~190+ future events, 100% local processing, $0 LLM cost**

## Live Deployment

| Component | URL | Host |
|-----------|-----|------|
| **Frontend** | [nu-events.vercel.app](https://nu-events.vercel.app) | Vercel (free) |
| **Backend API** | [nu-events-api.onrender.com](https://nu-events-api.onrender.com) | Render (free) |
| **Database** | Render PostgreSQL | Render (free) |
| **Scraping + LLM** | Local Mac | launchd scheduler |

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- [Ollama](https://ollama.com) with Gemma 12B (`ollama pull gemma3:12b`)

### 1. Backend (local development)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Start the API server (auto-creates SQLite DB)
uvicorn src.main:app --reload --port 8000
```

### 2. Ollama (LLM for email/Instagram parsing)

```bash
# Install Ollama
brew install ollama
brew services start ollama

# Pull the model (~8GB)
ollama pull gemma3:12b
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3001
```

### 4. Gmail Poller (for LISTSERV emails)

1. **Google Cloud OAuth**: Create project → Enable Gmail API → OAuth 2.0 credentials → save as `backend/credentials.json`
2. **Gmail label + filter**: Create `NU-Events` label, filter `list:listserv.it.northwestern.edu` → Skip Inbox, Apply label
3. **Subscribe to LISTSERV lists**: Email `LISTSERV@LISTSERV.IT.NORTHWESTERN.EDU` with `SUBSCRIBE LISTNAME Your Name`
4. **Add to .env**: `GMAIL_USER_EMAIL=you@u.northwestern.edu`

### 5. Instagram Scraper

```bash
cd backend
source .venv/bin/activate

# Extract cookies from Chrome (must be logged into Instagram)
python -c "
import browser_cookie3, json
cj = browser_cookie3.chrome(domain_name='.instagram.com')
cookies = [{'name':c.name,'value':c.value,'domain':c.domain,
             'path':c.path,'secure':c.secure} for c in cj]
json.dump(cookies, open('ig_cookies.json','w'))
print(f'Cached {len(cookies)} cookies')
"

# Import handles from JSON
python scripts/import_handles.py handles.json
```

### 6. Automated Scheduler

```bash
cd backend

# Install (runs every 1.5 hours + on boot)
bash scripts/install_scheduler.sh install

# Manage
bash scripts/install_scheduler.sh status   # check if running
bash scripts/install_scheduler.sh logs     # view recent logs
bash scripts/install_scheduler.sh uninstall # stop
launchctl start com.nuevents.scraper       # trigger manually
```

Each scheduler run:
1. Scrapes PlanIt Purple (JSON-LD, no LLM needed)
2. Polls Gmail for new LISTSERV emails (Gemma 12B)
3. Scrapes 25 Instagram orgs (staggered batches, Gemma 12B)
4. Cleans past events
5. **Auto-syncs to remote Postgres** (deployed site updates)

### 7. Deployment

**Backend (Render):**
- New Web Service → `graceeshao/nu-events`, root: `backend`
- Build: `pip install -e "."`
- Start: `uvicorn src.main:app --host 0.0.0.0 --port 10000`
- Add PostgreSQL database
- Env vars: `DATABASE_URL` (internal Postgres URL), `CORS_ORIGINS` (JSON array of allowed origins)

**Frontend (Vercel):**
- Import → `graceeshao/nu-events`, root: `frontend`
- Env var: `NEXT_PUBLIC_API_URL=https://nu-events-api.onrender.com`

**Manual sync (if needed):**
```bash
DATABASE_URL="postgresql://..." python scripts/sync_to_remote.py
```

## Architecture

### Event Processing Pipeline

```
Email/Instagram Post
    │
    ▼
┌─────────────────────────────────┐
│  Layer 1: Pre-filters (instant) │  Subscriptions, job postings,
│  - Regex patterns               │  elections, welcome messages
│  - Post cache (seen before?)    │  → skip without LLM
└───────────┬─────────────────────┘
            │ passes
            ▼
┌─────────────────────────────────┐
│  Layer 2: LLM Classification    │  Gemma 12B via Ollama (LOCAL)
│  - Batch: 20 captions per call  │  "Is this an attendable event?"
│  - Full body (no truncation)    │  → EVENT or NOT_EVENT
│  - Year-aware prompts           │
└───────────┬─────────────────────┘
            │ EVENT
            ▼
┌─────────────────────────────────┐
│  Layer 3: LLM Extraction        │  Title, date, time, location,
│  - Structured JSON output       │  description, RSVP URL, category
│  - Image analysis for flyers    │  free food detection
└───────────┬─────────────────────┘
            │
            ▼
┌─────────────────────────────────┐
│  Layer 4: Validation            │  Reject courses, forms, surveys,
│  - event_validator.py           │  admin notices, past events,
│  - 2-tier dedup (exact + fuzzy) │  deadlines without gatherings
└───────────┬─────────────────────┘
            │ valid + future
            ▼
        Database
```

### PlanIt Purple Pipeline (no LLM needed)

```
planitpurple.northwestern.edu
    → Collect event IDs from main page + Weinberg
    → Fetch JSON-LD from each event detail page
    → Parse structured schema.org/Event data
    → Clean location (strip time/category artifacts)
    → Dedup + insert
```

### Instagram Pipeline

```
427 org accounts (staggered: 25 per run)
    → Chrome cookies for auth (ig_cookies.json)
    → REST API v1: profile info + user feed
    → 3-layer filter: cache → regex prefilter → batch LLM (20/call)
    → Image analysis for flyer posts (Gemma 12B vision)
    → Future-only events, inactive org detection
    → Rate limit handling: stop batch early on 429/401
```

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

### Instagram
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/instagram/scrape/{handle}` | Scrape a single org |
| `POST` | `/instagram/scrape-all` | Scrape all orgs with handles |
| `GET` | `/instagram/handles` | List all orgs with Instagram handles |
| `POST` | `/instagram/handles` | Bulk update Instagram handles |

### Email Ingestion
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/ingest/email` | JSON: `{subject, body, sender}` |
| `POST` | `/ingest/raw` | Raw RFC 822 email text |

### Scrapers & Poller
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/scrapers/planitpurple/run` | Trigger PlanIt Purple scraper |
| `POST` | `/poller/trigger` | Trigger one Gmail poll cycle |
| `GET` | `/poller/status` | Check poller status |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./nu_events.db` | Database connection |
| `API_KEY` | *(empty)* | If set, required on write endpoints |
| `CORS_ORIGINS` | `["http://localhost:3000","http://localhost:3001"]` | Allowed frontend origins |
| `GMAIL_USER_EMAIL` | *(empty)* | Your NU Gmail for IMAP auth |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `gemma3:12b` | LLM model for classification |
| `INSTAGRAM_SESSION_USER` | *(empty)* | Instagram username (Instaloader fallback) |

## Project Structure

```
nu-events/
├── backend/
│   ├── src/
│   │   ├── api/routes/           # FastAPI endpoints
│   │   ├── models/               # SQLAlchemy: Event, Organization, IngestedEmail
│   │   ├── schemas/              # Pydantic request/response schemas
│   │   ├── scrapers/             # PlanIt Purple scraper
│   │   ├── services/
│   │   │   ├── llm_parser.py     # Gemma 12B classification + extraction
│   │   │   ├── batch_classifier.py # Batch 20 captions per LLM call
│   │   │   ├── email_parser.py   # Regex fallback parser
│   │   │   ├── gmail_poller.py   # IMAP polling with OAuth2
│   │   │   ├── instagram_scraper.py # REST API + Chrome cookies
│   │   │   ├── instagram_prefilter.py # Regex pre-screening
│   │   │   ├── post_cache.py     # IG post dedup across runs
│   │   │   ├── event_validator.py # Post-LLM quality control
│   │   │   ├── event_service.py  # CRUD + 2-tier dedup
│   │   │   └── dedup.py          # SHA-256 dedup keys
│   │   ├── config.py             # Env-based settings
│   │   └── main.py               # FastAPI app factory
│   ├── scripts/
│   │   ├── scheduled_scrape.py   # Main scheduler (all sources + sync)
│   │   ├── scrape_planitpurple_full.py # JSON-LD scraper
│   │   ├── sync_to_remote.py     # Push to Render Postgres
│   │   ├── import_handles.py     # Bulk IG handle import
│   │   ├── install_scheduler.sh  # launchd install/uninstall
│   │   └── com.nuevents.scraper.plist # launchd config
│   ├── tests/                    # pytest tests
│   ├── Procfile                  # Render deployment
│   └── render.yaml               # Render blueprint
├── frontend/                     # Next.js 14 + TypeScript + Tailwind
│   └── src/
│       ├── app/                  # Pages: home, events/[id], organizations
│       ├── components/           # EventCard, FilterBar, Pagination, Header
│       ├── hooks/                # useEvents (debounced search)
│       └── lib/                  # API client, types, utils
├── docs/
│   ├── ARCHITECTURE.md           # System architecture deep dive
│   ├── INSTAGRAM_SCRAPING.md     # Instagram scraping research
│   ├── API.md                    # API documentation
│   └── SETUP.md                  # Setup guide
└── docker-compose.yml
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, SQLAlchemy (async), Pydantic |
| Frontend | Next.js 14, React 18, TypeScript, Tailwind CSS |
| Database | SQLite (local) / PostgreSQL (deployed) |
| LLM | Ollama + Gemma 12B (local, free, no API key) |
| Scraping | httpx, BeautifulSoup4, browser-cookie3 |
| Email | imaplib, Google OAuth2, python-dateutil |
| Deployment | Vercel (frontend), Render (backend + Postgres) |
| Scheduling | macOS launchd (every 1.5 hours) |

## License

MIT
