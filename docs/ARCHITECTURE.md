# Architecture

## System Overview

NU Events is a three-tier web application that aggregates campus events from multiple sources into a single searchable interface.

```
┌─────────────────────────────────────────────────┐
│              DATA COLLECTION TIER                │
│                                                  │
│  ┌──────────────┐  ┌─────────────────────────┐  │
│  │  PlanIt      │  │  Gmail IMAP Poller      │  │
│  │  Purple      │  │  (polls NU-Events label │  │
│  │  Scraper     │  │   every 15 min)         │  │
│  └──────┬───────┘  └──────────┬──────────────┘  │
│         │                     │                  │
│         │          ┌──────────▼──────────────┐  │
│         │          │  Email Parser           │  │
│         │          │  (regex-based:          │  │
│         │          │   dates, times,         │  │
│         │          │   NU buildings,         │  │
│         │          │   LISTSERV headers)     │  │
│         │          └──────────┬──────────────┘  │
└─────────┼─────────────────────┼──────────────────┘
          │                     │
          ▼                     ▼
┌─────────────────────────────────────────────────┐
│                 BACKEND TIER                     │
│                                                  │
│  ┌───────────────────────────────────────────┐  │
│  │             FastAPI Application            │  │
│  │                                            │  │
│  │  Routes:                                   │  │
│  │    /events      — CRUD + search/filter     │  │
│  │    /organizations — campus org directory    │  │
│  │    /ingest      — email ingestion          │  │
│  │    /scrapers    — scraper management       │  │
│  │    /poller      — Gmail poller control     │  │
│  │                                            │  │
│  │  Services:                                 │  │
│  │    event_service  — dedup + CRUD           │  │
│  │    email_parser   — regex extraction       │  │
│  │    llm_parser     — Ollama/Gemma classifier │  │
│  │    gmail_poller   — IMAP + OAuth2          │  │
│  │    dedup          — SHA-256 key gen        │  │
│  └────────────────────┬──────────────────────┘  │
│                       │                          │
│  ┌────────────────────▼──────────────────────┐  │
│  │           SQLite Database                  │  │
│  │                                            │  │
│  │  Tables:                                   │  │
│  │    events          — aggregated events     │  │
│  │    organizations   — campus orgs           │  │
│  │    ingested_emails — processing log        │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
          │
          │ REST API (JSON)
          ▼
┌─────────────────────────────────────────────────┐
│               FRONTEND TIER                      │
│                                                  │
│  Next.js 14 + React + TypeScript + Tailwind      │
│                                                  │
│  Pages:                                          │
│    /              — event list + search/filter    │
│    /events/[id]   — event detail (SSR)           │
│    /organizations — org directory                 │
└─────────────────────────────────────────────────┘
```

## Data Flow

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
    → Email arrives in your NU Gmail
    → Gmail filter moves it to "NU-Events" label (skips inbox)
    → IMAP Poller connects every 15 min via OAuth2
    → Reads UNSEEN messages from NU-Events folder
    → For each email:
        1. Extract headers: Subject, From, List-Id, Sender
        2. Extract body (prefer text/plain, fallback HTML)
        3. Identify org from List-Id header
           (e.g. ANIME.LISTSERV.IT.NORTHWESTERN.EDU → ANIME)
        4. Parse body for event details:
           - Dates: "March 28, 2026", "3/28", "this Friday"
           - Times: "7pm", "7:00 PM - 9:00 PM"
           - Locations: 40+ known NU buildings
        5. Create event(s) in database
        6. Log in ingested_emails table
        7. Mark email as read
```

### 3. Manual Ingestion
```
POST /ingest/email  →  JSON {subject, body, sender}
POST /ingest/raw    →  Raw RFC 822 email text
    → Same email parser as above
    → Returns created events
```

## Deduplication

Events from different sources may describe the same event. Dedup prevents duplicates:

```
dedup_key = SHA-256(normalize(title) + "|" + start_time.isoformat() + "|" + normalize(location))[:32]
```

The `dedup_key` column has a UNIQUE constraint. If an event with the same key already exists, the existing record is returned instead of creating a duplicate.

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
| source_name | VARCHAR(200) | e.g. "PlanIt Purple", "LISTSERV:ANIME" |
| category | ENUM | academic, social, career, arts, sports, other |
| tags | JSON | Arbitrary metadata |
| image_url | VARCHAR(2000) | Nullable |
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
| instagram_handle | VARCHAR(200) | Nullable |
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
- **CORS**: Configured in settings, defaults to `http://localhost:3000`.
- **No user accounts**: This is a public read-only site. Write operations are for admin/scraper use only.
