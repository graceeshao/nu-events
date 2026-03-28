# Architecture

## System Overview

NU Events is a three-tier web application that aggregates campus events from multiple sources into a single searchable interface.

```
┌──────────────────────────────────────────────────────────────────┐
│                     DATA COLLECTION TIER                         │
│                                                                  │
│  ┌──────────────┐  ┌────────────────────┐  ┌─────────────────┐  │
│  │  PlanIt      │  │  Gmail IMAP Poller │  │  Instagram      │  │
│  │  Purple      │  │  (NU-Events label, │  │  Scraper        │  │
│  │  Scraper     │  │   every 15 min)    │  │  (195 org accts │  │
│  │              │  │                    │  │   via REST API) │  │
│  └──────┬───────┘  └────────┬───────────┘  └───────┬─────────┘  │
│         │                   │                      │            │
│         │          ┌────────▼───────────┐  ┌───────▼─────────┐  │
│         │          │  Email Parser      │  │  3-Layer Filter │  │
│         │          │  (regex: dates,    │  │  1. Post cache  │  │
│         │          │   times, NU bldgs, │  │  2. Regex pre-  │  │
│         │          │   LISTSERV hdrs)   │  │     filter      │  │
│         │          └────────┬───────────┘  │  3. LLM (only   │  │
│         │                   │              │     if needed)   │  │
│         │                   │              └───────┬─────────┘  │
│         │          ┌────────▼──────────────────────▼─────────┐  │
│         │          │  LLM Classifier (Gemma 4B via Ollama)   │  │
│         │          │  • Classification: EVENT or NOT_EVENT   │  │
│         │          │  • Extraction: title, date, time, loc   │  │
│         │          │  • Full body scanning (no truncation)   │  │
│         │          │  • Year-aware (current year context)    │  │
│         │          └────────┬────────────────────────────────┘  │
└─────────┼───────────────────┼────────────────────────────────────┘
          │                   │
          ▼                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                       BACKEND TIER                               │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                  FastAPI Application                        │  │
│  │                                                            │  │
│  │  Routes:                                                   │  │
│  │    /events         — CRUD + search/filter                  │  │
│  │    /organizations  — campus org directory (700+ orgs)      │  │
│  │    /ingest         — email ingestion                       │  │
│  │    /scrapers       — PlanIt Purple scraper management      │  │
│  │    /poller         — Gmail poller control                  │  │
│  │    /instagram      — IG scraper + handle management        │  │
│  │                                                            │  │
│  │  Services:                                                 │  │
│  │    event_service   — 2-tier dedup (exact + fuzzy) + CRUD   │  │
│  │    email_parser    — regex extraction                      │  │
│  │    llm_parser      — Ollama/Gemma classifier + extractor   │  │
│  │    gmail_poller    — IMAP + OAuth2                         │  │
│  │    instagram_scraper — REST API + Chrome cookies           │  │
│  │    instagram_prefilter — regex pre-screening               │  │
│  │    post_cache      — dedup for IG posts across runs        │  │
│  └─────────────────────────┬──────────────────────────────────┘  │
│                            │                                     │
│  ┌─────────────────────────▼──────────────────────────────────┐  │
│  │                    SQLite Database                          │  │
│  │                                                            │  │
│  │  Tables:                                                   │  │
│  │    events            — aggregated events (all sources)     │  │
│  │    organizations     — 700+ campus orgs (195 w/ IG)        │  │
│  │    ingested_emails   — processing log                      │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
          │
          │ REST API (JSON)
          ▼
┌──────────────────────────────────────────────────────────────────┐
│                      FRONTEND TIER                               │
│                                                                  │
│  Next.js 14 + React + TypeScript + Tailwind (port 3001)         │
│                                                                  │
│  Pages:                                                          │
│    /              — event list + search/filter                    │
│    /events/[id]   — event detail (SSR)                           │
│    /organizations — org directory                                 │
└──────────────────────────────────────────────────────────────────┘
```

## Data Sources

### 1. PlanIt Purple Scraper
```
planitpurple.northwestern.edu
    → HTTP GET (up to 5 pages)
    → Parse <article> tags (title, date, time, location, category)
    → Generate dedup key (SHA-256 of title + start_time + location)
    → Insert into events table (skip if dedup key exists)
```

### 2. LISTSERV Email Pipeline
```
Student org sends email to LISTSERV
    → Email arrives in Gmail (graceshao2026@u.northwestern.edu)
    → Gmail filter moves it to "NU-Events" label (skips inbox)
    → IMAP Poller connects every 15 min via OAuth2
    → Reads UNSEEN messages from NU-Events folder
    → For each email:
        1. Extract headers: Subject, From, List-Id, Sender
        2. Extract body (prefer text/plain, fallback HTML)
        3. Identify org from List-Id header
        4. LLM Classification (full body — no truncation):
           - Gemma 4B classifies: EVENT or NOT_EVENT
           - Current year + date injected into prompt
           - Pre-filters skip subscriptions, job postings, elections
        5. LLM Extraction (if EVENT):
           - Title, date, time, location, description, category
           - RSVP URL, free food detection
        6. Year validation: clamp to current year ± 1
        7. 2-tier dedup: exact key + fuzzy (title + ±1 day)
        8. Create event(s) in database
        9. Log in ingested_emails table
```

### 3. Instagram Scraper Pipeline
```
195 org Instagram accounts with known handles
    → Authenticate via Chrome browser cookies (ig_cookies.json)
    → REST API v1: /users/web_profile_info + /feed/user/{id}
    → For each post (last 30 days, max 5 per org):

        Layer 1 — Post Cache (instant):
          Already processed? → skip (processed_posts.json)

        Layer 2 — Regex Pre-filter (microseconds):
          Score caption for event signals:
            +3 date patterns (March 28, this Friday, tomorrow)
            +3 time patterns (7pm, 7-9pm, noon)
            +2 event words (join us, RSVP, don't miss)
            +2 event types (workshop, concert, meeting)
            +2 location (Norris, Tech, room 301)
            -3 non-event (throwback, congrats, hiring)
          Score < 3? → skip (not an event)

        Layer 3 — LLM Classification (10-30 sec, LOCAL):
          → Gemma 4B via Ollama (same as email pipeline)
          → Zero API cost — runs on local Mac

    → Rate limiting: 3s between profiles, 1s between posts
    → Results: ~33% of posts filtered before LLM on first run
    → Re-runs: near-zero LLM calls (cache handles it)
```

### 4. Manual Ingestion
```
POST /ingest/email  →  JSON {subject, body, sender}
POST /ingest/raw    →  Raw RFC 822 email text
    → Same LLM pipeline as above
    → Returns created events
```

## Deduplication

Events from different sources may describe the same event. Two-tier dedup prevents duplicates:

### Tier 1: Exact Key Match
```
dedup_key = SHA-256(normalize(title) + "|" + start_time.isoformat() + "|" + normalize(location))[:32]
```
The `dedup_key` column has a UNIQUE constraint.

### Tier 2: Fuzzy Match
```
normalized_title = lowercase(strip Re:/Fwd:/[brackets], remove punctuation, collapse whitespace)
If any existing event has the same normalized title within ±1 day → duplicate
```
Catches Re:/Fwd: email chain duplicates with slightly different locations.

## LLM Configuration

- **Model**: Gemma 3 4B (`gemma3:4b`) via Ollama
- **Fallback**: Gemma 3 1B (`gemma3:1b`)
- **Temperature**: 0 (deterministic)
- **Cost**: $0 — runs 100% locally
- **Classification prompt**: Detailed NU-specific context (event types, non-events, key distinctions)
- **Extraction prompt**: Includes today's date, current year, academic year for temporal grounding

## Instagram Authentication

Instagram blocks anonymous API access. The scraper uses Chrome browser cookies:

```
1. Log into Instagram in Chrome (one-time)
2. Extract cookies: python -c "import browser_cookie3, json; ..."
3. Cached to ig_cookies.json (no Keychain prompts during scraping)
4. Session reused in-memory across all profile fetches
```

To refresh cookies (if they expire):
```bash
cd backend
source .venv/bin/activate
python -c "
import browser_cookie3, json
cj = browser_cookie3.chrome(domain_name='.instagram.com')
cookies = [{'name':c.name,'value':c.value,'domain':c.domain,
             'path':c.path,'secure':c.secure} for c in cj]
json.dump(cookies, open('ig_cookies.json','w'))
print(f'Cached {len(cookies)} cookies')
"
```

## Database Schema

### events
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | Primary key, autoincrement |
| title | VARCHAR(500) | Not null |
| description | TEXT | Nullable |
| start_time | DATETIME | Not null, indexed |
| end_time | DATETIME | Nullable |
| location | VARCHAR(500) | Nullable |
| source_url | VARCHAR(2000) | Link to original event page |
| source_name | VARCHAR(200) | e.g. "PlanIt Purple", "LISTSERV:ANIME", "Instagram:@ao.productions" |
| category | ENUM | academic, social, career, arts, sports, other |
| tags | JSON | Arbitrary metadata |
| image_url | VARCHAR(2000) | Nullable |
| rsvp_url | VARCHAR(2000) | Registration/RSVP link |
| has_free_food | BOOLEAN | Free food flag |
| dedup_key | VARCHAR(500) | Unique, indexed |
| created_at | DATETIME | Auto-set |
| updated_at | DATETIME | Auto-set, auto-update |

### organizations
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | Primary key |
| name | VARCHAR(500) | Unique, not null |
| category | VARCHAR(100) | RSO, TGS, FSL, etc. |
| tags | JSON | List of tag strings |
| club_id | INTEGER | WildcatConnection ID |
| instagram_handle | VARCHAR(200) | e.g. "ao.productions" |
| website | VARCHAR(500) | Nullable |
| email | VARCHAR(200) | Nullable |
| listserv_name | VARCHAR(200) | Corresponding LISTSERV list |
| created_at | DATETIME | Auto-set |
| updated_at | DATETIME | Auto-set |

### ingested_emails
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | Primary key |
| subject | VARCHAR | Nullable |
| sender | VARCHAR | Nullable |
| body | TEXT | Not null |
| received_at | DATETIME | Auto-set |
| events_created | INTEGER | Count of events extracted |
| status | VARCHAR | processed, no_events_found, error |
| error_message | TEXT | Nullable |

## Security

- **API Key**: Optional `API_KEY` env var. When set, POST/PATCH/DELETE require `X-API-Key` header.
- **OAuth tokens**: `credentials.json` and `token.json` are in `.gitignore`. Never committed.
- **Instagram cookies**: `ig_cookies.json` is in `.gitignore`. Contains session data.
- **CORS**: Configured in settings, defaults to `http://localhost:3000,3001,3002`.
- **No user accounts**: This is a public read-only site. Write operations are for admin/scraper use only.

## Performance

| Metric | Value |
|--------|-------|
| Organizations in DB | 700+ |
| Orgs with Instagram handles | 195 |
| Email ingestion (132 emails) | ~10 min (LLM-bound) |
| Instagram scrape (195 orgs) | ~30-60 min (rate-limit-bound) |
| Instagram re-scrape | Near-instant (cache) |
| Pre-filter efficiency | ~33% of posts skipped before LLM |
| LLM cost | $0 (100% local Gemma 4B) |
