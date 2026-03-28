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

import instaloader

from src.config import settings
from src.database.session import async_session_factory
from src.models.email_ingest import IngestedEmail
from src.services.event_service import create_event
from src.services.llm_parser import parse_event_with_llm

logger = logging.getLogger(__name__)

# Rate limiting: pause between profile fetches to avoid Instagram bans
_PROFILE_DELAY_SECONDS = 5
_POST_DELAY_SECONDS = 2


def _get_loader() -> instaloader.Instaloader:
    """Create a configured Instaloader instance.

    Instagram blocks anonymous API access (403), so a logged-in session
    is required. Use ``instaloader --login YOUR_USERNAME`` once to create
    a session file, then set INSTAGRAM_SESSION_USER in .env.

    Returns:
        An Instaloader instance with conservative rate-limit settings.

    Raises:
        RuntimeError: If no session file is available (anonymous access
            is blocked by Instagram).
    """
    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        max_connection_attempts=3,
        request_timeout=30,
    )

    session_user = settings.instagram_session_user
    if not session_user:
        raise RuntimeError(
            "Instagram requires a logged-in session. "
            "Run: instaloader --login YOUR_USERNAME  (once) "
            "then set INSTAGRAM_SESSION_USER=YOUR_USERNAME in .env"
        )

    try:
        L.load_session_from_file(session_user)
        logger.info("Loaded Instagram session for @%s", session_user)
    except FileNotFoundError:
        raise RuntimeError(
            f"No session file found for @{session_user}. "
            f"Run: instaloader --login {session_user}"
        )

    return L


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


def fetch_recent_posts(
    handle: str,
    days_back: int = 14,
    max_posts: int = 20,
) -> list[dict[str, Any]]:
    """Fetch recent posts from an Instagram profile.

    Args:
        handle: Instagram username (without @).
        days_back: How many days back to look.
        max_posts: Maximum posts to fetch per profile.

    Returns:
        List of dicts with keys: caption, post_url, posted_at, handle.
    """
    L = _get_loader()
    handle = handle.lstrip("@").strip().lower()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    try:
        profile = instaloader.Profile.from_username(L.context, handle)
    except instaloader.exceptions.ProfileNotExistsException:
        logger.warning("Instagram profile @%s does not exist", handle)
        return []
    except instaloader.exceptions.ConnectionException as exc:
        logger.error("Instagram connection error for @%s: %s", handle, exc)
        return []

    posts = []
    try:
        for i, post in enumerate(profile.get_posts()):
            if i >= max_posts:
                break
            if post.date_utc < cutoff:
                break  # Posts are in reverse chronological order

            caption = _extract_caption_text(post)
            if not caption or len(caption) < 20:
                continue  # Skip image-only posts or very short captions

            posts.append({
                "caption": caption,
                "post_url": f"https://www.instagram.com/p/{post.shortcode}/",
                "posted_at": post.date_utc,
                "handle": handle,
                "shortcode": post.shortcode,
            })

            import time
            time.sleep(_POST_DELAY_SECONDS)

    except instaloader.exceptions.ConnectionException as exc:
        logger.error("Error fetching posts for @%s: %s", handle, exc)

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
