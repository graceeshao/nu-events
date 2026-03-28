"""Batch LLM classification for Instagram captions.

Instead of 1 LLM call per post, batches 20 captions into a single
prompt for classification. Only posts classified as EVENT get
individual extraction calls. ~20x fewer LLM calls.

Also handles image-based event detection for posts with short/no captions.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, date
from typing import Any

import ollama

from src.config import settings
from src.schemas.event import EventCreate
from src.services.llm_parser import (
    _get_ollama_client,
    _resolve_model,
    _chat,
    _build_event,
    _clean_title,
    EXTRACTION_PROMPT,
    VALID_CATEGORIES,
)
from src.services.email_parser import (
    detect_free_food,
    extract_rsvp_url,
    match_organization,
)
from src.services.event_validator import validate_and_filter_events

logger = logging.getLogger(__name__)

BATCH_CLASSIFY_PROMPT = """\
You classify Instagram posts from Northwestern University student organizations.
Today's date is {today}.

For EACH post below, respond with ONLY its number and EVENT or NOT_EVENT.
Format: 1:EVENT or 1:NOT_EVENT (one per line, no extra text)

An EVENT is a specific gathering people attend at a scheduled date/time:
talks, concerts, workshops, socials, meetings, info sessions, performances, games, competitions, volunteerings.

NOT an event: throwbacks, recaps, shoutouts, board intros, hiring posts, application deadlines, forms/surveys, course listings, thank-you posts, merchandise sales, general announcements without a specific date+time+place.

{posts}

Respond with ONLY the numbered classifications, nothing else:"""

IMAGE_EVENT_PROMPT = """\
This is a flyer or promotional image from a Northwestern University student organization's Instagram.
Today's date is {today}. The current year is {year}.

If this image describes an ATTENDABLE EVENT (with a date, time, and/or location), extract the details as JSON:
{{"title": "...", "date": "YYYY-MM-DD", "start_time": "HH:MM", "end_time": "HH:MM or null", "location": "...", "description": "...", "category": "academic or social or career or arts or sports or other"}}

If this is NOT an event (just a graphic, meme, throwback, announcement without specific date/time), respond with exactly: NOT_EVENT

CRITICAL: Dates must be in {year}. If no year shown, assume {year}. Only extract FUTURE events (after {today})."""


async def batch_classify_captions(
    posts: list[dict[str, Any]],
    batch_size: int = 20,
) -> list[tuple[dict, bool]]:
    """Classify multiple captions in a single LLM call.

    Args:
        posts: List of post dicts with 'caption' key.
        batch_size: Number of captions per LLM call.

    Returns:
        List of (post, is_event) tuples.
    """
    try:
        client = _get_ollama_client()
        model = _resolve_model(client)
    except (ConnectionError, RuntimeError) as exc:
        logger.warning("Ollama unavailable for batch classify: %s", exc)
        # Fall back: treat all as potential events
        return [(p, True) for p in posts]

    results = []
    today = date.today().isoformat()

    for i in range(0, len(posts), batch_size):
        batch = posts[i:i + batch_size]

        # Build numbered post list
        post_lines = []
        for j, post in enumerate(batch):
            caption = post["caption"][:300]  # Trim for batch prompt
            caption = caption.replace("\n", " ").strip()
            post_lines.append(f"{j+1}. {caption}")

        prompt = BATCH_CLASSIFY_PROMPT.format(
            today=today,
            posts="\n".join(post_lines),
        )

        try:
            response = await _chat(client, model, prompt)

            # Parse response: "1:EVENT\n2:NOT_EVENT\n3:EVENT..."
            classifications = {}
            for line in response.strip().split("\n"):
                line = line.strip()
                match = re.match(r"(\d+)\s*[:\-\.]\s*(EVENT|NOT_EVENT)", line, re.IGNORECASE)
                if match:
                    num = int(match.group(1))
                    is_event = "NOT" not in match.group(2).upper()
                    classifications[num] = is_event

            for j, post in enumerate(batch):
                is_event = classifications.get(j + 1, True)  # Default to True if parse fails
                results.append((post, is_event))

            event_count = sum(1 for _, e in results[-len(batch):] if e)
            logger.info(
                "Batch %d-%d: %d/%d classified as EVENT",
                i + 1, i + len(batch), event_count, len(batch),
            )

        except Exception as exc:
            logger.warning("Batch classify failed: %s, treating all as events", exc)
            for post in batch:
                results.append((post, True))

    return results


async def extract_event_from_caption(
    caption: str,
    handle: str,
) -> list[EventCreate]:
    """Extract event details from a single caption using LLM.

    Args:
        caption: Full caption text.
        handle: Instagram handle for source attribution.

    Returns:
        List of EventCreate objects.
    """
    try:
        client = _get_ollama_client()
        model = _resolve_model(client)
    except (ConnectionError, RuntimeError):
        return []

    _today = date.today()
    _year = _today.year
    _ay = f"{_year}-{_year+1}" if _today.month >= 8 else f"{_year-1}-{_year}"

    subject = caption[:100].split("\n")[0]

    prompt = EXTRACTION_PROMPT.format(
        subject=subject,
        body_preview=caption,
        today=_today.isoformat(),
        current_year=_year,
        academic_year=_ay,
    )

    try:
        response = await _chat(client, model, prompt)

        # Parse JSON
        cleaned = response.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        parsed = json.loads(cleaned)

        if isinstance(parsed, dict):
            parsed = [parsed]

        events = []
        for data in parsed:
            try:
                event = _build_event(
                    data,
                    org=f"Instagram:@{handle}",
                    fallback_rsvp=extract_rsvp_url(caption),
                    fallback_free_food=detect_free_food(caption),
                    subject=subject,
                    body=caption,
                )
                events.append(event)
            except Exception:
                continue

        return validate_and_filter_events(events)

    except Exception as exc:
        logger.warning("Extraction failed for @%s: %s", handle, exc)
        return []


async def extract_event_from_image(
    image_url: str,
    handle: str,
) -> list[EventCreate]:
    """Extract event details from a flyer image using Ollama vision.

    Args:
        image_url: URL of the Instagram post image.
        handle: Instagram handle.

    Returns:
        List of EventCreate objects.
    """
    import httpx

    try:
        client = _get_ollama_client()
        model = _resolve_model(client)
    except (ConnectionError, RuntimeError):
        return []

    _today = date.today()
    _year = _today.year

    # Download image
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.get(image_url)
            if resp.status_code != 200:
                return []
            image_bytes = resp.content
    except Exception:
        logger.debug("Failed to download image from @%s", handle)
        return []

    # Convert to base64
    import base64
    image_b64 = base64.b64encode(image_bytes).decode()

    prompt = IMAGE_EVENT_PROMPT.format(
        today=_today.isoformat(),
        year=_year,
    )

    try:
        # Use Ollama chat with images
        response = await asyncio.to_thread(
            lambda: client.chat(
                model=model,
                messages=[{
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],
                }],
                options={"temperature": 0},
            )
        )

        text = response["message"]["content"].strip()

        if "NOT_EVENT" in text.upper():
            return []

        # Parse JSON
        cleaned = re.sub(r"^```(?:json)?\s*", "", text)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        parsed = json.loads(cleaned)

        if isinstance(parsed, dict):
            parsed = [parsed]

        events = []
        for data in parsed:
            try:
                event = _build_event(
                    data,
                    org=f"Instagram:@{handle}",
                    fallback_rsvp=None,
                    fallback_free_food=False,
                    subject=data.get("title", ""),
                    body=data.get("description", ""),
                )
                events.append(event)
            except Exception:
                continue

        return validate_and_filter_events(events)

    except json.JSONDecodeError:
        return []
    except Exception as exc:
        logger.debug("Image analysis failed for @%s: %s", handle, exc)
        return []
