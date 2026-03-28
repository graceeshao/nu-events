"""Instagram scraper for student org event posts.

Uses Instaloader to fetch recent posts from org Instagram accounts,
then feeds captions through the LLM pipeline for event classification
and extraction.
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from src.database.session import async_session_factory
from src.models.email_ingest import IngestedEmail
from src.services.event_service import create_event
from src.services.llm_parser import parse_event_with_llm

logger = logging.getLogger(__name__)

# Rate limiting: pause between profile fetches to avoid Instagram bans
_PROFILE_DELAY_SECONDS = 5
_POST_DELAY_SECONDS = 2


_cached_session: Any = None


def _get_browser_session() -> Any:
    """Create an authenticated requests session using cached Instagram cookies.

    On first call, loads cookies from ``ig_cookies.json`` (pre-extracted
    from Chrome).  The session is cached in-memory for reuse so that
    Chrome Safe Storage / Keychain is never hit during scraping.

    To refresh cookies run::

        python -c "
        import browser_cookie3, json
        cj = browser_cookie3.chrome(domain_name='.instagram.com')
        cookies = [{'name':c.name,'value':c.value,'domain':c.domain,
                     'path':c.path,'secure':c.secure} for c in cj]
        json.dump(cookies, open('ig_cookies.json','w'))
        print(f'Cached {len(cookies)} cookies')
        "

    Returns:
        A ``requests.Session`` with Instagram cookies loaded.

    Raises:
        RuntimeError: If no cached cookies are found.
    """
    global _cached_session
    if _cached_session is not None:
        return _cached_session

    import json as _json
    import os
    import requests

    # Look for cached cookies file
    cookie_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..", "ig_cookies.json"),
        "ig_cookies.json",
    ]

    cookies = None
    for path in cookie_paths:
        try:
            with open(path) as f:
                cookies = _json.load(f)
            logger.info("Loaded cached Instagram cookies from %s", path)
            break
        except FileNotFoundError:
            continue

    if not cookies:
        # Fallback: try browser_cookie3 (will trigger Keychain prompt)
        try:
            import browser_cookie3
            cj = browser_cookie3.chrome(domain_name=".instagram.com")
            session = requests.Session()
            session.cookies = cj
        except Exception as exc:
            raise RuntimeError(
                f"No cached cookies (ig_cookies.json) and Chrome fallback failed: {exc}"
            ) from exc
    else:
        session = requests.Session()
        for c in cookies:
            session.cookies.set(
                c["name"], c["value"],
                domain=c.get("domain", ".instagram.com"),
                path=c.get("path", "/"),
                secure=c.get("secure", True),
            )

    session.headers.update({
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "x-ig-app-id": "936619743392459",
        "x-requested-with": "XMLHttpRequest",
    })

    # Set CSRF token if available
    csrf = session.cookies.get("csrftoken")
    if csrf:
        session.headers["x-csrftoken"] = csrf

    _cached_session = session
    return session


def _extract_caption_text(post: Any) -> str:
    """Extract clean text from an Instagram post caption.

    Args:
        post: Instaloader Post object.

    Returns:
        Caption text, or empty string if no caption.
    """
    caption = post.caption or ""
    # Remove excessive hashtag blocks at the end
    # Keep hashtags that are inline (part of sentences)
    lines = caption.split("\n")
    cleaned_lines = []
    for line in lines:
        # Skip lines that are purely hashtags
        stripped = line.strip()
        if stripped and all(
            word.startswith("#") or word.startswith("@") or not word.strip()
            for word in stripped.split()
        ):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def _fetch_posts_rest_api(
    handle: str,
    session: Any,
    days_back: int = 14,
    max_posts: int = 20,
) -> list[dict[str, Any]]:
    """Fetch recent posts using Instagram's REST API (more reliable than GraphQL).

    Args:
        handle: Instagram username.
        session: Authenticated requests session from Instaloader.
        days_back: How many days back to look.
        max_posts: Maximum posts to fetch.

    Returns:
        List of post dicts.
    """
    import time as _time
    from datetime import datetime as _dt

    cutoff_ts = (_dt.now(timezone.utc) - timedelta(days=days_back)).timestamp()
    headers = {"x-ig-app-id": "936619743392459"}

    # Get user ID first
    resp = session.get(
        f"https://www.instagram.com/api/v1/users/web_profile_info/?username={handle}",
        headers=headers,
    )
    if resp.status_code != 200:
        logger.warning("Failed to fetch profile @%s: HTTP %d", handle, resp.status_code)
        return []

    user_data = resp.json().get("data", {}).get("user")
    if not user_data:
        logger.warning("Instagram profile @%s not found", handle)
        return []

    user_id = user_data.get("id")
    if not user_id:
        return []

    # Fetch posts via user feed endpoint
    posts = []
    end_cursor = None
    has_next = True

    while has_next and len(posts) < max_posts:
        url = f"https://www.instagram.com/api/v1/feed/user/{user_id}/?count=12"
        if end_cursor:
            url += f"&max_id={end_cursor}"

        _time.sleep(_POST_DELAY_SECONDS)
        resp = session.get(url, headers=headers)

        if resp.status_code != 200:
            logger.warning("Feed fetch failed for @%s: HTTP %d", handle, resp.status_code)
            break

        data = resp.json()
        items = data.get("items", [])
        has_next = data.get("more_available", False)
        end_cursor = data.get("next_max_id")

        for item in items:
            taken_at = item.get("taken_at", 0)
            if taken_at < cutoff_ts:
                has_next = False
                break

            # Extract caption
            caption_data = item.get("caption")
            caption = caption_data.get("text", "") if caption_data else ""
            if not caption or len(caption) < 20:
                continue

            # Clean caption (remove trailing hashtag blocks)
            lines = caption.split("\n")
            cleaned = []
            for line in lines:
                stripped = line.strip()
                if stripped and all(
                    w.startswith("#") or w.startswith("@") or not w.strip()
                    for w in stripped.split()
                ):
                    continue
                cleaned.append(line)
            caption = "\n".join(cleaned).strip()

            code = item.get("code", "")
            posts.append({
                "caption": caption,
                "post_url": f"https://www.instagram.com/p/{code}/" if code else "",
                "posted_at": datetime.fromtimestamp(taken_at, tz=timezone.utc),
                "handle": handle,
                "shortcode": code,
            })

            if len(posts) >= max_posts:
                break

    return posts


def fetch_recent_posts(
    handle: str,
    days_back: int = 14,
    max_posts: int = 20,
) -> list[dict[str, Any]]:
    """Fetch recent posts from an Instagram profile.

    Uses Chrome browser cookies for authentication and the REST API
    (v1/feed) for fetching posts — more reliable than Instaloader's
    GraphQL endpoint and uses the browser's higher rate limits.

    Args:
        handle: Instagram username (without @).
        days_back: How many days back to look.
        max_posts: Maximum posts to fetch per profile.

    Returns:
        List of dicts with keys: caption, post_url, posted_at, handle.
    """
    handle = handle.lstrip("@").strip().lower()
    session = _get_browser_session()
    posts = _fetch_posts_rest_api(
        session=session, handle=handle,
        days_back=days_back, max_posts=max_posts,
    )
    logger.info("Fetched %d recent posts from @%s", len(posts), handle)
    return posts


async def scrape_org_instagram(
    handle: str,
    org_name: str,
    days_back: int = 14,
    max_posts: int = 20,
) -> dict[str, int]:
    """Scrape an org's Instagram and ingest events.

    Fetches recent posts, classifies them via LLM, and creates events
    for any that describe attendable events.

    Args:
        handle: Instagram username.
        org_name: Organization name for source attribution.
        days_back: How far back to look.
        max_posts: Max posts to check.

    Returns:
        Summary dict with posts_checked and events_created.
    """
    posts = await asyncio.to_thread(
        fetch_recent_posts, handle, days_back, max_posts,
    )

    events_created = 0

    async with async_session_factory() as db:
        for post in posts:
            caption = post["caption"]
            post_url = post["post_url"]

            # Use the caption as both "subject" and "body" for the LLM
            # The subject is a truncated version for display
            subject = caption[:100].split("\n")[0]

            try:
                parsed_events = await parse_event_with_llm(
                    subject=subject,
                    body=caption,
                    sender=f"@{handle}",
                )

                for event_in in parsed_events:
                    # Override source info
                    event_in.source_name = f"Instagram:@{handle}"
                    event_in.source_url = post_url
                    await create_event(db, event_in)
                    events_created += 1
                    logger.info(
                        "Created event from @%s: %s",
                        handle, event_in.title,
                    )

            except Exception:
                logger.exception(
                    "Error processing post %s from @%s",
                    post_url, handle,
                )

        await db.commit()

    summary = {
        "posts_checked": len(posts),
        "events_created": events_created,
    }
    logger.info("Instagram scrape for @%s complete: %s", handle, summary)
    return summary


async def scrape_all_orgs(
    handles: list[tuple[str, str]],
    days_back: int = 14,
    max_posts: int = 10,
) -> dict[str, Any]:
    """Scrape multiple org Instagram accounts sequentially.

    Args:
        handles: List of (instagram_handle, org_name) tuples.
        days_back: How far back to look.
        max_posts: Max posts per org.

    Returns:
        Summary with total stats.
    """
    total_posts = 0
    total_events = 0
    orgs_scraped = 0
    orgs_failed = 0

    for handle, org_name in handles:
        try:
            result = await scrape_org_instagram(
                handle, org_name, days_back, max_posts,
            )
            total_posts += result["posts_checked"]
            total_events += result["events_created"]
            orgs_scraped += 1

            # Rate limit between orgs
            await asyncio.sleep(_PROFILE_DELAY_SECONDS)

        except Exception:
            logger.exception("Failed to scrape @%s (%s)", handle, org_name)
            orgs_failed += 1

    return {
        "orgs_scraped": orgs_scraped,
        "orgs_failed": orgs_failed,
        "total_posts_checked": total_posts,
        "total_events_created": total_events,
    }
