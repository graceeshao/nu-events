# Setup Guide

Complete setup instructions for running NU Events locally.

## Prerequisites

- Python 3.11+
- Node.js 18+
- A Google account (for Gmail poller OAuth — personal account works)
- An `@u.northwestern.edu` Gmail account (for LISTSERV subscriptions)

## 1. Clone the Repo

```bash
git clone https://github.com/graceeshao/nu-events.git
cd nu-events
```

## 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

# Install dependencies
pip install -e ".[dev]"
pip install python-dateutil google-auth google-auth-oauthlib google-auth-httplib2 pymupdf

# Start the server (creates SQLite DB automatically)
uvicorn src.main:app --reload --port 8000
```

The API is now at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

## 3. Seed Data

```bash
# Seed organizations (159 campus orgs)
python scripts/seed_organizations.py

# Seed sample events (for development)
python ../scripts/seed_data.py

# OR scrape real events from PlanIt Purple
curl -X POST http://localhost:8000/scrapers/planitpurple/run
```

## 4. Frontend Setup

```bash
cd frontend

# Create env file
cp .env.local.example .env.local
# Edit .env.local if your backend isn't on port 8000

# Install dependencies
npm install

# Start dev server
npm run dev
```

The site is now at `http://localhost:3000` (or 3001 if 3000 is taken).

## 5. Gmail Poller Setup (Optional)

The poller monitors your NU Gmail for LISTSERV event emails. Skip this if you just want to use the PlanIt Purple scraper.

### 5a. Google OAuth Credentials

1. Go to [console.cloud.google.com](https://console.cloud.google.com) (use a **personal** Google account if your NU account blocks Cloud Console)
2. Create a new project (e.g. "NU Events")
3. Go to **APIs & Services → Library** → search "Gmail API" → **Enable**
4. Go to **APIs & Services → Credentials** → **Create Credentials** → **OAuth client ID**
5. Application type: **Desktop app**
6. Click **Create**, then **Download JSON**
7. Save the file as `backend/credentials.json`

### 5b. Authorize the App

```bash
cd backend
python ../scripts/gmail_auth.py
```

A browser window opens. Log in with your **NU Google account** (`@u.northwestern.edu`) and click Allow. A `token.json` file is saved — you won't need to do this again.

### 5c. Gmail Label & Filter

1. In Gmail, create a new label: **NU-Events**
2. Go to Settings → Filters → Create a new filter:
   - **Has the words:** `list:listserv.it.northwestern.edu`
   - **Action:** Skip the Inbox, Apply label "NU-Events"

This catches all LISTSERV emails regardless of sender and keeps your inbox clean.

### 5d. Subscribe to LISTSERVs

Send an email to `LISTSERV@LISTSERV.IT.NORTHWESTERN.EDU` with the body containing one subscribe command per line:

```
SUBSCRIBE ANIME Grace Shao
SUBSCRIBE EVENTS Grace Shao
SUBSCRIBE DANCE-MARATHON Grace Shao
```

You'll get confirmation emails for each list that accepts you. Some lists may require owner approval.

### 5e. Run the Poller

```bash
cd backend

# Set your email
export GMAIL_USER_EMAIL=graceshao@u.northwestern.edu

# Test with a single poll
python ../scripts/run_poller.py --once

# Run continuously (polls every 15 min)
python ../scripts/run_poller.py

# Or with a custom interval
python ../scripts/run_poller.py --interval 300  # every 5 min
```

## 6. Running Tests

```bash
cd backend
pytest -v           # all 169 tests
pytest -v -k email  # just email parser tests
pytest -v -k api    # just API tests
```

## Environment Variables

All optional. Set in a `.env` file in `backend/` or export in your shell.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./nu_events.db` | Database connection string |
| `API_KEY` | *(empty)* | If set, required on POST/PATCH/DELETE |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed frontend origins |
| `GMAIL_CREDENTIALS_FILE` | `credentials.json` | Google OAuth client-secret JSON |
| `GMAIL_TOKEN_FILE` | `token.json` | Saved OAuth token |
| `GMAIL_USER_EMAIL` | *(empty)* | Your NU Gmail address |
| `GMAIL_LABEL` | `NU-Events` | Gmail label to poll |
| `GMAIL_POLL_INTERVAL_SECONDS` | `900` | Poll interval in seconds |
| `DEBUG` | `false` | Enable SQL query logging |

## Troubleshooting

### "Failed to select label 'NU-Events'"
The Gmail label doesn't exist yet. Create it in Gmail (see step 5c).

### "AUTHENTICATE command error: BAD"
The OAuth token may have expired. Delete `token.json` and re-run `gmail_auth.py`.

### "This app is blocked" during OAuth
Your NU Google Workspace may block third-party OAuth apps. Use a personal Google account for the Cloud Console project (step 5a), then still log in with your NU account during authorization (step 5b).

### Events not showing on frontend
1. Check the backend is running: `curl http://localhost:8000/`
2. Check there are events: `curl http://localhost:8000/events`
3. Check the frontend `.env.local` has the correct API URL
4. Check browser console for CORS errors

### Scraper returns 0 events
PlanIt Purple's HTML structure may have changed. Check `backend/src/scrapers/planitpurple.py` selectors against the live site.
