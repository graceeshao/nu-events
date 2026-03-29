# Instagram Scraping Research (2025–2026)

> **Goal:** Reliably view recent posts (captions + image URLs) from ~427 public university student org accounts, once daily, without getting banned.
>
> **Current approach:** Instagram REST API v1 (`/users/web_profile_info` + `/feed/user/{id}`) with Chrome browser cookies → hitting 429 after ~20-50 profiles.
>
> **Last updated:** 2026-03-28

---

## Table of Contents

1. [Instagram Rate Limits in 2025-2026](#1-instagram-rate-limits-in-2025-2026)
2. [Why Our Current Approach Fails](#2-why-our-current-approach-fails)
3. [Approach 1: Account + Session Rotation with Residential Proxies (RECOMMENDED)](#approach-1)
4. [Approach 2: Unauthenticated GraphQL with Proxy Rotation](#approach-2)
5. [Approach 3: Third-Party Scraping Services (Apify, etc.)](#approach-3)
6. [Approach 4: Instagram oEmbed + Graph API (Limited but Legitimate)](#approach-4)
7. [Approach 5: Hybrid — Time-Distributed Scraping with Fallbacks](#approach-5)
8. [Other Approaches Considered (and Why They Don't Work)](#other-approaches)
9. [Optimal Configuration & Delays](#optimal-configuration)
10. [Recommendation](#recommendation)

---

## 1. Instagram Rate Limits in 2025-2026

### Official API (Graph API)
- **Was:** 5,000 calls/hour per token
- **Now (2025+):** Reduced to ~200 calls/hour for many apps — a 96% decrease, rolled out without notice
- Source: MarketingScoop deep-dive confirmed this across multiple developer reports

### Unofficial REST API (what we use)
- **Logged-in sessions:** ~200 requests/hour per IP/session before 429
- **Anonymous (no cookies):** Much lower — Instagram now mandates login for most profile data; anonymous requests often get login walls or empty responses
- **Per-IP hard limit:** ~200 requests/hour regardless of session, based on IP reputation
- **Progressive penalties:** Repeated violations → longer blocks (hours → days) → permanent IP bans

### GraphQL Endpoints
- Similar rate limits to REST (~200/hr per IP/session)
- `doc_id` parameters change every 2-4 weeks (anti-scraping measure)
- Slightly more data per request (can get 12 posts embedded in profile response)

### Key Insight
Rate limits are enforced at **multiple layers**:
1. **Per IP** — datacenter IPs blocked on sight
2. **Per session/cookie** — each logged-in session has its own quota
3. **Per account** — Instagram tracks account-level request patterns
4. **Behavioral** — regular intervals, direct API hits without page loads, missing CSS/image requests all trigger flags

---

## 2. Why Our Current Approach Fails

| Problem | Details |
|---------|---------|
| **Single IP** | All 427 requests come from one IP → 429 after ~20-50 |
| **Single session** | One cookie set = one rate limit budget |
| **Direct API calls only** | No accompanying page/asset requests = bot signal |
| **Predictable pattern** | Rapid sequential hits to `/web_profile_info` screams automation |
| **No retry/backoff** | Hitting 429 and continuing burns the session |

---

## <a id="approach-1"></a>Approach 1: Account + Session Rotation with Residential Proxies ⭐ RECOMMENDED

### How It Works
- Maintain 5-10 throwaway Instagram accounts (created on different devices/IPs)
- Each account has its own session cookies
- Pair each account with a sticky residential proxy IP
- Distribute the 427 profiles across accounts: ~43-85 profiles per account per day
- Add human-like delays (3-8 seconds with jitter) between requests

### Rate Limit Characteristics
- Each account+IP pair gets its own ~200 req/hr budget
- 5 accounts × 200 req/hr = 1,000 req/hr capacity (we only need ~430)
- With delays, a full run across 427 profiles takes ~30-60 minutes spread across accounts

### Pros
- **Most reliable** — distributes load naturally
- **Stays well under limits** — 43 profiles per account is very conservative
- **Residential IPs** prevent datacenter detection
- **Recoverable** — if one account gets flagged, others continue
- **No external service dependency** — you control everything

### Cons
- Account maintenance overhead (accounts may still get flagged over months)
- Residential proxy cost: ~$5-15/month for the bandwidth needed (very low — we're only fetching JSON, not media)
- Need to periodically refresh accounts if they get challenged
- Initial setup complexity

### Python Implementation

```python
import asyncio
import random
import httpx
from itertools import cycle
from dataclasses import dataclass

@dataclass
class InstaSession:
    username: str
    cookies: dict
    proxy: str  # residential proxy URL
    
SESSIONS = [
    InstaSession("acct1", {"sessionid": "...", "csrftoken": "..."}, "http://user:pass@proxy1:port"),
    InstaSession("acct2", {"sessionid": "...", "csrftoken": "..."}, "http://user:pass@proxy2:port"),
    # ... 5-10 accounts
]

HEADERS_BASE = {
    "x-ig-app-id": "936619743392459",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "*/*",
}

async def scrape_profile(client: httpx.AsyncClient, username: str) -> dict | None:
    url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
    try:
        resp = await client.get(url, headers=HEADERS_BASE)
        if resp.status_code == 429:
            return None  # signal to rotate/backoff
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("user")
    except Exception as e:
        print(f"Error scraping {username}: {e}")
        return None

async def scrape_batch(session: InstaSession, usernames: list[str]) -> list[dict]:
    results = []
    async with httpx.AsyncClient(
        cookies=session.cookies,
        proxy=session.proxy,
        timeout=30.0,
        http2=True,  # Instagram expects HTTP/2
    ) as client:
        for username in usernames:
            result = await scrape_profile(client, username)
            if result is None:
                # 429 — back off and retry later
                await asyncio.sleep(random.uniform(60, 120))
                result = await scrape_profile(client, username)
            results.append({"username": username, "data": result})
            # Human-like delay with jitter
            await asyncio.sleep(random.uniform(3, 8))
    return results

async def scrape_all(all_usernames: list[str]):
    # Split usernames evenly across sessions
    chunks = [[] for _ in SESSIONS]
    for i, username in enumerate(all_usernames):
        chunks[i % len(SESSIONS)].append(username)
    
    # Run all session batches concurrently
    tasks = [scrape_batch(session, chunk) for session, chunk in zip(SESSIONS, chunks)]
    all_results = await asyncio.gather(*tasks)
    return [item for sublist in all_results for item in sublist]
```

### Proxy Providers (Budget-Friendly)
| Provider | Residential Pricing | Notes |
|----------|-------------------|-------|
| **BrightData** | $5.04/GB | Industry leader, sticky sessions |
| **Smartproxy** | $4/GB | Good for low-volume, rotating |
| **IPRoyal** | $1.75/GB | Budget option, decent quality |
| **Oxylabs** | $8/GB | Premium, highest success rates |

For our use case (~427 JSON responses/day ≈ 5-10 MB), monthly proxy cost would be **under $1/month** on bandwidth. Most providers have minimum plans of $5-15/month.

---

## <a id="approach-2"></a>Approach 2: Unauthenticated Scraping via GraphQL + Proxy Rotation

### How It Works
- Use Instagram's GraphQL endpoint (`/graphql/query`) without authentication
- Rotate through residential proxy IPs for each request
- Extract `doc_id` values by monitoring Instagram's web app in DevTools
- Each request to a new IP gets a fresh rate limit budget

### Rate Limit Characteristics
- ~200 requests/hour per IP
- With rotating residential proxies, effectively unlimited (each request = different IP)
- Instagram now shows login walls for many anonymous requests — **this is the main risk**

### Pros
- No account management needed
- Simple implementation
- With enough proxy IPs, rate limits are irrelevant

### Cons
- **Instagram increasingly requires login** for profile data — anonymous access is unreliable in 2026
- `doc_id` values change every 2-4 weeks; you must monitor and update
- Residential proxies still required (datacenter IPs blocked instantly)
- May return partial data compared to authenticated requests
- TLS fingerprinting can still detect Python `httpx`/`requests` libraries

### Python Implementation

```python
import httpx
import json
from urllib.parse import quote

PROFILE_DOC_ID = "9310670392322965"  # Changes every 2-4 weeks!

async def scrape_profile_graphql(username: str, proxy: str) -> dict | None:
    # First get user_id from profile page
    variables = quote(json.dumps({
        "username": username,
        "render_surface": "PROFILE"
    }, separators=(',', ':')))
    
    body = f"variables={variables}&doc_id={PROFILE_DOC_ID}"
    
    async with httpx.AsyncClient(proxy=proxy, timeout=30) as client:
        resp = await client.post(
            "https://www.instagram.com/graphql/query",
            content=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "x-ig-app-id": "936619743392459",
                "User-Agent": "Mozilla/5.0 ...",
            }
        )
        if resp.status_code == 200:
            return resp.json()
    return None
```

### Verdict
Workable as a **fallback** but not reliable as primary approach due to increasing login walls.

---

## <a id="approach-3"></a>Approach 3: Third-Party Scraping Services

### Options & Pricing

| Service | How It Works | Pricing (for ~427 profiles/day) | Notes |
|---------|-------------|--------------------------------|-------|
| **Apify** (Instagram Profile Scraper) | Cloud actors with built-in proxy rotation | ~$30-49/month (pay-per-result) | Most popular; handles all anti-bot |
| **ScrapFly** | API with anti-blocking, residential proxies included | ~$20-50/month | Open-source scraper code, maintained `doc_id` updates |
| **ScrapeCreators** | REST API, no Instagram login needed | ~$29/month starter | Claims "no rate limits" |
| **ScrapingBot** | API endpoint, returns structured JSON | ~$25-50/month | 100 free credits to test |
| **Lobstr.io** | No-code, point-and-click | ~$20-40/month | Good for non-technical users |
| **PhantomBuster** | Browser-based automation | ~$56/month starter | Higher cost, more features than needed |

### Pros
- **Zero maintenance** — they handle proxy rotation, account management, `doc_id` updates
- **Highest reliability** — it's their whole business
- **No risk to your IPs or accounts**
- **Structured data output** — clean JSON

### Cons
- **Cost:** $20-50/month ongoing
- **Vendor dependency** — if they shut down or change pricing, you're stuck
- **Data freshness** — some services cache results
- **Less control** over timing and error handling

### Apify Specific Notes
- The Reddit OP (DataHoarder thread) estimated ~$40/month for ~200 profiles
- For 427 profiles once daily, expect **$30-50/month** on Apify
- Their Instagram Profile Scraper actor is actively maintained and handles most blocking
- Can be called from Python via `apify-client` package

```python
from apify_client import ApifyClient

client = ApifyClient("YOUR_APIFY_TOKEN")

run = client.actor("apify/instagram-profile-scraper").call(
    run_input={
        "usernames": ["nu_wildside", "nubaja", ...],  # your 427 usernames
        "resultsLimit": 12,  # posts per profile
    }
)

for item in client.dataset(run["defaultDatasetId"]).iterate_items():
    print(item["username"], item["latestPosts"])
```

---

## <a id="approach-4"></a>Approach 4: Instagram oEmbed + Graph API (Limited but Legitimate)

### How It Works
- **oEmbed endpoint:** `https://graph.facebook.com/v21.0/instagram_oembed?url=https://instagram.com/p/{shortcode}&access_token={token}`
- Returns embed HTML and basic metadata for individual posts
- Requires a Facebook App with `meta_oembed_read` permission
- **Graph API:** For business/creator accounts you manage, provides full access

### Rate Limit Characteristics
- oEmbed: Subject to Graph API rate limits (~200 calls/hr per app token as of 2025)
- More lenient than scraping — it's an official endpoint
- No risk of IP bans

### Pros
- **Fully legitimate** — Meta-sanctioned endpoint
- **No proxy or account rotation needed**
- **Stable** — won't break from `doc_id` changes

### Cons
- **oEmbed only works with post URLs** — you need to know the shortcode first (chicken-and-egg problem)
- **Doesn't return profile/feed data** — can't discover new posts
- **Limited metadata** — embed HTML + author_name + thumbnail, NOT full caption text
- **thumbnail_url removed** as of Oct 2025 oEmbed update
- **Graph API** only works for accounts you own/manage (not arbitrary public profiles)

### Verdict
**Not viable as primary approach** for our use case. We need to discover new posts, not just embed known ones. However, oEmbed could supplement other approaches for getting embed-ready HTML.

---

## <a id="approach-5"></a>Approach 5: Hybrid — Time-Distributed Scraping with Fallbacks

### How It Works
Combine multiple techniques to maximize reliability:

1. **Split 427 accounts into 4 batches of ~107**
2. **Scrape each batch at a different time of day** (6am, 12pm, 6pm, 12am)
3. **Use 3-5 rotating accounts + residential proxies** (Approach 1)
4. **If a batch fails, retry with a different account/proxy pair**
5. **Cache results** — only re-scrape profiles that haven't been updated recently
6. **Fall back to Apify** for any profiles that consistently fail

### Rate Limit Characteristics
- Spreading across time windows avoids hitting sustained rate limits
- With 3 accounts per batch, each account handles ~36 profiles — very conservative
- Total daily requests: ~430 (one per profile) + retries

### Implementation Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│  Scheduler   │────▶│  Account Pool    │────▶│  Instagram   │
│  (4x daily)  │     │  (5 sessions +   │     │  REST/GQL    │
│              │     │   5 res. proxies) │     │  endpoints   │
└─────────────┘     └──────────────────┘     └─────┬───────┘
                                                     │
                    ┌──────────────────┐              │
                    │  Results Cache   │◀─────────────┘
                    │  (SQLite/JSON)   │
                    └──────┬───────────┘
                           │ on failure
                    ┌──────▼───────────┐
                    │  Apify Fallback  │
                    │  (pay-per-use)   │
                    └──────────────────┘
```

### Python Skeleton

```python
import asyncio
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

class HybridScraper:
    def __init__(self, sessions, usernames, cache_path="cache.json"):
        self.sessions = sessions  # List of InstaSession
        self.usernames = usernames
        self.cache_path = Path(cache_path)
        self.cache = self._load_cache()
    
    def _load_cache(self):
        if self.cache_path.exists():
            return json.loads(self.cache_path.read_text())
        return {}
    
    def _needs_update(self, username: str) -> bool:
        """Skip profiles updated in last 20 hours"""
        if username not in self.cache:
            return True
        last = datetime.fromisoformat(self.cache[username].get("updated_at", "2000-01-01"))
        return datetime.now() - last > timedelta(hours=20)
    
    async def scrape_batch(self, batch_usernames: list[str]):
        # Filter to only profiles needing update
        to_scrape = [u for u in batch_usernames if self._needs_update(u)]
        
        # Distribute across sessions
        session_cycle = cycle(self.sessions)
        tasks = []
        for username in to_scrape:
            session = next(session_cycle)
            tasks.append(self._scrape_one(session, username))
            # Stagger task starts
            await asyncio.sleep(random.uniform(2, 5))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle failures — queue for retry or Apify fallback
        failed = [to_scrape[i] for i, r in enumerate(results) if isinstance(r, Exception) or r is None]
        if failed:
            await self._apify_fallback(failed)
    
    async def _scrape_one(self, session, username):
        # ... (use scrape_profile from Approach 1)
        pass
    
    async def _apify_fallback(self, usernames):
        # Only called for persistent failures
        # Costs ~$0.01-0.05 per profile on Apify
        pass
```

### Pros
- **Most resilient** — multiple fallback layers
- **Cost-efficient** — Apify only used for failures (~$1-5/month)
- **Respects rate limits naturally** through time distribution
- **Caching reduces requests** — student orgs don't post every day

### Cons
- Most complex to implement and maintain
- Multiple moving parts to debug

---

## <a id="other-approaches"></a>Other Approaches Considered

### ❌ HTML Page Scraping (`instagram.com/username/`)
- **Status (2026):** Instagram requires login to view profiles on web; unauthenticated requests redirect to login page
- The `__a=1` JSON endpoint **no longer works** — removed years ago
- Page source no longer contains embedded JSON data for unauthenticated visitors
- **Verdict:** Dead approach

### ❌ Instagram RSS/Atom Feeds
- Instagram has **never** offered official RSS feeds
- Third-party RSS bridges (like Bibliogram) are all defunct as of 2024+
- **Verdict:** Not an option

### ❌ Google Cache / Wayback Machine
- Google Cache was **discontinued** in 2024
- Wayback Machine doesn't crawl Instagram profiles frequently enough for daily updates
- **Verdict:** Not useful for fresh data

### ❌ CrowdTangle
- **Shut down by Meta in August 2024**, replaced by Meta Content Library
- Meta Content Library requires academic/research institution access and lengthy approval
- Could be worth applying if you're affiliated with Northwestern — but approval takes months
- **Verdict:** Not practical for our timeline, but worth a long-term application

### ❌ Instagram Basic Display API
- **Deprecated** by Meta — being phased out entirely
- Only ever worked for your own account's data anyway
- **Verdict:** Dead

### ⚠️ User-Agent Rotation
- **Helps marginally** — Instagram checks User-Agent for consistency within a session, but the main detection is TLS fingerprinting and IP reputation
- Rotating User-Agents between sessions (not within) is good practice
- Alone, it won't solve rate limits — it's a supplementary measure
- **Verdict:** Do it, but it's not a solution by itself

---

## <a id="optimal-configuration"></a>Optimal Configuration & Delays

### Delay Between Requests
| Approach | Recommended Delay | Notes |
|----------|------------------|-------|
| Single account, single IP | 15-20 seconds | Still risky for 427 profiles |
| Multiple accounts + proxies | 3-8 seconds (randomized) | Sweet spot for our scale |
| Third-party service | N/A (handled for you) | — |

### Key Rules
1. **Never use fixed intervals** — always add random jitter (±30-50%)
2. **Add micro-pauses** between batches (30-60 sec every 20-30 profiles)
3. **Respect 429 responses** — exponential backoff: 60s → 120s → 300s → skip
4. **Scrape at different hours** — not always at the same time
5. **Warm up sessions** — make a few "normal" requests (load homepage, own profile) before scraping
6. **Randomize profile order** — don't always scrape alphabetically

### Session Health Monitoring
```python
async def check_session_health(session: InstaSession) -> bool:
    """Verify a session is still valid before using it"""
    try:
        async with httpx.AsyncClient(cookies=session.cookies, proxy=session.proxy) as client:
            resp = await client.get(
                "https://i.instagram.com/api/v1/accounts/current_user/",
                headers=HEADERS_BASE
            )
            return resp.status_code == 200
    except:
        return False
```

### Logged-in vs Anonymous
| Factor | Logged-in | Anonymous |
|--------|-----------|-----------|
| Rate limit | ~200 req/hr per account | ~100 req/hr per IP (often less) |
| Data access | Full profile + posts | Login wall on most endpoints (2026) |
| Detection risk | Moderate (account can be flagged) | High (suspicious without session) |
| Recommendation | **Use this** | Unreliable in 2026 |

---

## <a id="recommendation"></a>10. Recommendation

### For NU Events: Start with Approach 1, Plan for Approach 5

**Phase 1 (Immediate):**
1. Set up **5 throwaway Instagram accounts** on different IPs/devices
2. Get a **residential proxy plan** (~$5-15/month from IPRoyal or Smartproxy)
3. Extract session cookies from each account
4. Implement the account rotation scraper from Approach 1
5. Run once daily, ~43 profiles per account, 4-6 second delays
6. **Expected reliability: 90-95%** with occasional 429s handled by backoff

**Phase 2 (If needed):**
1. Add **time-distributed batching** (Approach 5)
2. Add **Apify as fallback** for persistent failures
3. Monitor account health and rotate as needed

**Phase 3 (Scale/Stability):**
1. If self-hosted approach becomes too much maintenance, **migrate to Apify fully** (~$30-50/month)
2. The structured output from Apify is cleaner and requires less parsing code

### Cost Summary
| Component | Monthly Cost |
|-----------|-------------|
| Residential proxies (5 IPs, ~10MB/day) | $5-15 |
| Apify fallback (occasional) | $0-5 |
| **Total (self-hosted)** | **$5-20/month** |
| **Total (full Apify)** | **$30-50/month** |

### Priority Actions
- [ ] Create 5 Instagram accounts (spread over a week, different IPs)
- [ ] Sign up for residential proxy service (IPRoyal recommended for budget)
- [ ] Refactor current scraper to use account rotation pool
- [ ] Add randomized delays and exponential backoff
- [ ] Add session health checks and auto-rotation
- [ ] Set up SQLite cache to skip recently-scraped profiles
- [ ] Test with 50 profiles first, then scale to full 427
