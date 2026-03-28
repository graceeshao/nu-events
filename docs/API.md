# API Reference

Base URL: `http://localhost:8000`

Interactive Swagger docs: `http://localhost:8000/docs`

## Health Check

### `GET /`
```json
{"status": "ok", "app": "NU Events"}
```

---

## Events

### `GET /events`

List events with optional filters and pagination.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `category` | string | - | Filter: academic, social, career, arts, sports, other |
| `date_from` | ISO datetime | - | Events starting on or after |
| `date_to` | ISO datetime | - | Events starting on or before |
| `search` | string | - | Search title and description |
| `page` | int | 1 | Page number (1-indexed) |
| `page_size` | int | 20 | Results per page (max 100) |

**Response:**
```json
{
  "items": [
    {
      "id": 1,
      "title": "CIERA Astronomer Evenings",
      "description": null,
      "start_time": "2026-03-27T20:00:00",
      "end_time": "2026-03-27T22:00:00",
      "location": "Dearborn Observatory, 2131 Tech Drive, Evanston, IL 60208",
      "source_url": "https://planitpurple.northwestern.edu/event/636656",
      "source_name": "PlanIt Purple",
      "category": "other",
      "tags": {"categories": ["Academic (general)"]},
      "image_url": null,
      "dedup_key": "abc123...",
      "created_at": "2026-03-28T02:16:04",
      "updated_at": "2026-03-28T02:16:04"
    }
  ],
  "total": 130,
  "page": 1,
  "page_size": 20,
  "pages": 7
}
```

**Examples:**
```bash
# All events
curl http://localhost:8000/events

# Academic events this week
curl "http://localhost:8000/events?category=academic&date_from=2026-03-27&date_to=2026-04-03"

# Search for "concert"
curl "http://localhost:8000/events?search=concert"

# Page 2, 10 per page
curl "http://localhost:8000/events?page=2&page_size=10"
```

### `GET /events/{id}`

Get a single event by ID.

```bash
curl http://localhost:8000/events/1
```

### `POST /events`

Create an event manually.

```bash
curl -X POST http://localhost:8000/events \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Study Break",
    "start_time": "2026-04-01T16:00:00",
    "location": "Norris University Center",
    "category": "social"
  }'
```

### `PATCH /events/{id}`

Partial update.

```bash
curl -X PATCH http://localhost:8000/events/1 \
  -H "Content-Type: application/json" \
  -d '{"description": "Updated description"}'
```

### `DELETE /events/{id}`

```bash
curl -X DELETE http://localhost:8000/events/1
```

---

## Organizations

### `GET /organizations`

List organizations with optional filters.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `category` | string | - | Filter: RSO, TGS, FSL, etc. |
| `search` | string | - | Search org names |
| `page` | int | 1 | Page number |
| `page_size` | int | 20 | Results per page |

```bash
# All orgs
curl http://localhost:8000/organizations

# Search for dance clubs
curl "http://localhost:8000/organizations?search=dance"

# Only fraternities/sororities
curl "http://localhost:8000/organizations?category=FSL"
```

### `GET /organizations/{id}`
### `POST /organizations`
### `PATCH /organizations/{id}`
### `DELETE /organizations/{id}`

Same CRUD pattern as events.

---

## Email Ingestion

### `POST /ingest/email`

Submit a structured email for event extraction.

```bash
curl -X POST http://localhost:8000/ingest/email \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "Movie Night this Friday!",
    "body": "Join us Friday, March 28, 2026 at 7:00 PM at Norris University Center Room 201 for a movie screening.",
    "sender": "filmclub@u.northwestern.edu",
    "list_id": "FILMCLUB.LISTSERV.IT.NORTHWESTERN.EDU",
    "list_sender": ""
  }'
```

**Response:**
```json
{
  "status": "processed",
  "events_created": 1,
  "events": [
    {
      "id": 131,
      "title": "Movie Night this Friday!",
      "start_time": "2026-03-28T19:00:00",
      "location": "Norris University Center, Room 201",
      "source_name": "LISTSERV:FILMCLUB",
      ...
    }
  ]
}
```

### `POST /ingest/raw`

Submit a raw email (RFC 822 format).

```bash
curl -X POST http://localhost:8000/ingest/raw \
  -H "Content-Type: text/plain" \
  -d 'From: filmclub@u.northwestern.edu
Subject: Movie Night this Friday!
List-Id: FILMCLUB.LISTSERV.IT.NORTHWESTERN.EDU
Sender: owner-FILMCLUB@LISTSERV.IT.NORTHWESTERN.EDU

Join us Friday, March 28, 2026 at 7:00 PM at Norris Room 201.'
```

---

## Scrapers

### `GET /scrapers`

List registered scrapers.

```json
[{"name": "planitpurple"}]
```

### `POST /scrapers/{name}/run`

Trigger a scraper. Returns count of events found/created.

```bash
curl -X POST http://localhost:8000/scrapers/planitpurple/run
```

```json
{
  "scraper": "planitpurple",
  "events_found": 130,
  "events_created": 130
}
```

---

## Poller

### `GET /poller/status`

Check Gmail poller configuration and last run.

### `POST /poller/trigger`

Trigger a single Gmail poll cycle.

---

## Authentication

When `API_KEY` environment variable is set, mutation endpoints (POST, PATCH, DELETE) require the `X-API-Key` header:

```bash
export API_KEY=my-secret-key
# Then:
curl -X POST http://localhost:8000/events \
  -H "X-API-Key: my-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"title": "Test", "start_time": "2026-04-01T10:00:00"}'
```

When `API_KEY` is not set (default), no auth is required (development mode).
