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
from src.services.instagram_prefilter import caption_looks_like_event
from src.services.llm_parser import parse_event_with_llm
from src.services.post_cache import is_processed, mark_processed

logger = logging.getLogger(__name__)

# Rate limiting: pause between profile fetches to avoid Instagram bans
_PROFILE_DELAY_SECONDS = 3
_POST_DELAY_SECONDS = 1


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

    # Check latest post timestamp — if older than 1 year, account is inactive
    # This is checked in scrape_org_instagram which marks the org accordingly

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

            # Extract image URL for vision analysis
            image_url = None
            image_versions = item.get("image_versions2", {})
            candidates = image_versions.get("candidates", [])
            if candidates:
                # Pick smallest image that's still readable (~320-640px)
                sorted_imgs = sorted(candidates, key=lambda x: x.get("width", 9999))
                for img in sorted_imgs:
                    if img.get("width", 0) >= 320:
                        image_url = img.get("url")
                        break
                if not image_url and candidates:
                    image_url = candidates[0].get("url")

            posts.append({
                "caption": caption,
                "post_url": f"https://www.instagram.com/p/{code}/" if code else "",
                "posted_at": datetime.fromtimestamp(taken_at, tz=timezone.utc),
                "handle": handle,
                "shortcode": code,
                "image_url": image_url,
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


def _check_account_activity(handle: str) -> datetime | None:
    """Check when an Instagram account last posted.

    Uses the REST API to fetch the most recent post timestamp.

    Args:
        handle: Instagram username.

    Returns:
        Datetime of the most recent post, or None if no posts / error.
    """
    import time as _time

    session = _get_browser_session()
    headers = {"x-ig-app-id": "936619743392459"}

    try:
        resp = session.get(
            f"https://www.instagram.com/api/v1/users/web_profile_info/?username={handle}",
            headers=headers,
        )
        if resp.status_code != 200:
            return None

        user_data = resp.json().get("data", {}).get("user")
        if not user_data:
            return None

        user_id = user_data.get("id")
        if not user_id:
            return None

        # Fetch just 1 post to check latest activity
        resp = session.get(
            f"https://www.instagram.com/api/v1/feed/user/{user_id}/?count=1",
            headers=headers,
        )
        if resp.status_code != 200:
            return None

        items = resp.json().get("items", [])
        if not items:
            return None

        taken_at = items[0].get("taken_at", 0)
        if taken_at:
            return datetime.fromtimestamp(taken_at, tz=timezone.utc)

    except Exception:
        pass

    return None


async def scrape_org_instagram(
    handle: str,
    org_name: str,
    days_back: int = 14,
    max_posts: int = 20,
) -> dict[str, int]:
    """Scrape an org's Instagram and ingest events.

    Skips orgs marked as inactive (no posts in 1+ year).
    Automatically marks orgs as inactive if their latest post
    is older than 365 days.

    Args:
        handle: Instagram username.
        org_name: Organization name for source attribution.
        days_back: How far back to look.
        max_posts: Max posts to check.

    Returns:
        Summary dict with posts_checked and events_created.
    """
    # Check if org is marked inactive in DB — skip if so
    from sqlalchemy import select as _select
    from src.models.organization import Organization

    async with async_session_factory() as db:
        result = await db.execute(
            _select(Organization).where(
                Organization.instagram_handle == handle,
            )
        )
        org_record = result.scalars().first()

        if org_record and org_record.instagram_active is False:
            logger.debug("Skipping inactive @%s", handle)
            return {
                "posts_checked": 0, "events_created": 0,
                "skipped_cached": 0, "skipped_prefilter": 0,
                "sent_to_llm": 0, "inactive": True,
            }

    posts = await asyncio.to_thread(
        fetch_recent_posts, handle, days_back, max_posts,
    )

    # Check account activity — if no posts at all, check latest post date
    if not posts:
        last_post_dt = await asyncio.to_thread(_check_account_activity, handle)
        one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)

        async with async_session_factory() as db:
            result = await db.execute(
                _select(Organization).where(
                    Organization.instagram_handle == handle,
                )
            )
            org_record = result.scalars().first()
            if org_record:
                if last_post_dt:
                    org_record.instagram_last_post_at = last_post_dt
                    if last_post_dt < one_year_ago:
                        org_record.instagram_active = False
                        logger.info(
                            "Marked @%s as inactive (last post: %s)",
                            handle, last_post_dt.strftime("%Y-%m-%d"),
                        )
                elif org_record.instagram_last_post_at is None:
                    # No posts ever found — mark inactive
                    org_record.instagram_active = False
                    logger.info("Marked @%s as inactive (no posts found)", handle)
                await db.commit()

    events_created = 0
    skipped_cached = 0
    skipped_prefilter = 0
    sent_to_llm = 0

    async with async_session_factory() as db:
        for post in posts:
            caption = post["caption"]
            post_url = post["post_url"]
            shortcode = post.get("shortcode", "")

            # Layer 1: Cache — skip already-processed posts (instant)
            if shortcode and is_processed(shortcode):
                skipped_cached += 1
                continue

            # Layer 2: Regex pre-filter — skip obvious non-events (microseconds)
            looks_like_event, score = caption_looks_like_event(caption)
            if not looks_like_event:
                skipped_prefilter += 1
                if shortcode:
                    mark_processed(shortcode)
                continue

            # Layer 3: LLM classification + extraction (10-30 seconds)
            sent_to_llm += 1
            subject = caption[:100].split("\n")[0]

            try:
                parsed_events = await parse_event_with_llm(
                    subject=subject,
                    body=caption,
                    sender=f"@{handle}",
                )

                from datetime import datetime as _dt
                _now = _dt.now()

                for event_in in parsed_events:
                    # Skip past events — only future events matter
                    if event_in.start_time < _now:
                        logger.debug(
                            "Skipping past event from @%s: %s (%s)",
                            handle, event_in.title, event_in.start_time,
                        )
                        continue

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

            # Mark as processed regardless of outcome
            if shortcode:
                mark_processed(shortcode)

        await db.commit()

    summary = {
        "posts_checked": len(posts),
        "events_created": events_created,
        "skipped_cached": skipped_cached,
        "skipped_prefilter": skipped_prefilter,
        "sent_to_llm": sent_to_llm,
    }
    logger.info(
        "Instagram @%s: %d posts, %d→LLM, %d filtered, %d cached, %d events",
        handle, len(posts), sent_to_llm, skipped_prefilter, skipped_cached, events_created,
    )
    return summary


async def scrape_all_orgs(
    handles: list[tuple[str, str]],
    days_back: int = 14,
    max_posts: int = 10,
) -> dict[str, Any]:
    """Scrape all orgs using batch classification for speed.

    Strategy:
    1. Fetch posts from all orgs (sequential, rate-limited)
    2. Pre-filter with regex (instant)
    3. Batch classify remaining posts 20 at a time (1 LLM call per 20)
    4. Extract events only for posts classified as EVENT
    5. Analyze images for posts with short/no captions

    Args:
        handles: List of (instagram_handle, org_name) tuples.
        days_back: How far back to look.
        max_posts: Max posts per org.

    Returns:
        Summary with total stats.
    """
    from src.services.batch_classifier import (
        batch_classify_captions,
        extract_event_from_caption,
        extract_event_from_image,
    )
    from sqlalchemy import select as _select
    from src.models.organization import Organization

    # Phase 1: Fetch all posts
    logger.info("Phase 1: Fetching posts from %d orgs...", len(handles))
    all_posts = []  # (handle, org_name, post)
    orgs_scraped = 0
    orgs_inactive = 0
    orgs_failed = 0
    skipped_cached = 0

    for i, (handle, org_name) in enumerate(handles):
        try:
            # Check if inactive
            async with async_session_factory() as db:
                result = await db.execute(
                    _select(Organization).where(
                        Organization.instagram_handle == handle,
                    )
                )
                org_record = result.scalars().first()
                if org_record and org_record.instagram_active is False:
                    orgs_inactive += 1
                    continue

            posts = await asyncio.to_thread(
                fetch_recent_posts, handle, days_back, max_posts,
            )

            # Check activity for empty accounts
            if not posts:
                last_post_dt = await asyncio.to_thread(_check_account_activity, handle)
                one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)
                async with async_session_factory() as db:
                    result = await db.execute(
                        _select(Organization).where(
                            Organization.instagram_handle == handle,
                        )
                    )
                    org_record = result.scalars().first()
                    if org_record:
                        if last_post_dt:
                            org_record.instagram_last_post_at = last_post_dt
                            if last_post_dt < one_year_ago:
                                org_record.instagram_active = False
                                logger.info("Marked @%s inactive (last: %s)", handle, last_post_dt.strftime("%Y-%m-%d"))
                        elif org_record.instagram_last_post_at is None:
                            org_record.instagram_active = False
                            logger.info("Marked @%s inactive (no posts)", handle)
                        await db.commit()

            for post in posts:
                shortcode = post.get("shortcode", "")
                if shortcode and is_processed(shortcode):
                    skipped_cached += 1
                    continue
                all_posts.append((handle, org_name, post))

            orgs_scraped += 1

            if (i + 1) % 20 == 0:
                logger.info(
                    "Fetch progress: %d/%d orgs | %d posts collected | %d cached",
                    i + 1, len(handles), len(all_posts), skipped_cached,
                )

            await asyncio.sleep(_PROFILE_DELAY_SECONDS)

        except Exception:
            logger.exception("Failed to fetch @%s", handle)
            orgs_failed += 1

    logger.info(
        "Phase 1 done: %d posts from %d orgs (%d inactive, %d cached)",
        len(all_posts), orgs_scraped, orgs_inactive, skipped_cached,
    )

    # Phase 2: Pre-filter
    logger.info("Phase 2: Pre-filtering...")
    caption_posts = []  # Posts with captions for LLM
    image_posts = []    # Posts with short/no captions but images
    skipped_prefilter = 0

    for handle, org_name, post in all_posts:
        caption = post.get("caption", "")
        image_url = post.get("image_url")

        if len(caption) < 50 and image_url:
            # Short/no caption — try image analysis
            image_posts.append((handle, org_name, post))
        elif caption:
            is_event_like, score = caption_looks_like_event(caption)
            if is_event_like:
                caption_posts.append((handle, org_name, post))
            else:
                skipped_prefilter += 1
                shortcode = post.get("shortcode", "")
                if shortcode:
                    mark_processed(shortcode)
        else:
            skipped_prefilter += 1

    logger.info(
        "Phase 2 done: %d→batch classify, %d→image analysis, %d filtered",
        len(caption_posts), len(image_posts), skipped_prefilter,
    )

    # Phase 3: Batch classify captions
    logger.info("Phase 3: Batch classifying %d captions (20 per call)...", len(caption_posts))
    posts_for_extraction = []

    if caption_posts:
        post_dicts = [p for _, _, p in caption_posts]
        classified = await batch_classify_captions(post_dicts, batch_size=20)

        for (handle, org_name, post), (_, is_event) in zip(caption_posts, classified):
            if is_event:
                posts_for_extraction.append((handle, org_name, post))
            else:
                shortcode = post.get("shortcode", "")
                if shortcode:
                    mark_processed(shortcode)

    logger.info(
        "Phase 3 done: %d posts need extraction",
        len(posts_for_extraction),
    )

    # Phase 4: Extract events from captions + images
    logger.info("Phase 4: Extracting events...")
    total_events = 0
    total_llm_calls = len(caption_posts) // 20 + 1  # batch classify calls

    async with async_session_factory() as db:
        # Caption-based extraction
        for handle, org_name, post in posts_for_extraction:
            caption = post["caption"]
            post_url = post.get("post_url", "")
            shortcode = post.get("shortcode", "")

            events = await extract_event_from_caption(caption, handle)
            total_llm_calls += 1

            _now = datetime.now()
            for event in events:
                if event.start_time < _now:
                    continue
                event.source_name = f"Instagram:@{handle}"
                event.source_url = post_url
                await create_event(db, event)
                total_events += 1
                logger.info("Created event from @%s: %s", handle, event.title)

            if shortcode:
                mark_processed(shortcode)

        # Image-based extraction
        if image_posts:
            logger.info("Analyzing %d images...", len(image_posts))
        for handle, org_name, post in image_posts:
            image_url = post.get("image_url")
            post_url = post.get("post_url", "")
            shortcode = post.get("shortcode", "")

            if image_url:
                events = await extract_event_from_image(image_url, handle)
                total_llm_calls += 1

                _now = datetime.now()
                for event in events:
                    if event.start_time < _now:
                        continue
                    event.source_name = f"Instagram:@{handle}"
                    event.source_url = post_url
                    await create_event(db, event)
                    total_events += 1
                    logger.info("Created event from image @%s: %s", handle, event.title)

            if shortcode:
                mark_processed(shortcode)

        await db.commit()

    summary = {
        "orgs_scraped": orgs_scraped,
        "orgs_failed": orgs_failed,
        "orgs_inactive": orgs_inactive,
        "total_posts_checked": len(all_posts) + skipped_cached,
        "total_events_created": total_events,
        "total_llm_calls": total_llm_calls,
        "total_filtered_out": skipped_prefilter + skipped_cached,
        "image_posts_analyzed": len(image_posts),
    }

    logger.info(
        "Instagram complete: %d orgs, %d posts, %d LLM calls, %d events, %d images analyzed",
        orgs_scraped, len(all_posts), total_llm_calls, total_events, len(image_posts),
    )

    return summary
