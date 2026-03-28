"""LLM-based event extraction using local Ollama models.

Uses a local Gemma model via Ollama to classify emails and extract
structured event data. Falls back to regex parser if Ollama is unavailable.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, time

import ollama

from src.config import settings
from src.models.event import EventCategory
from src.schemas.event import EventCreate
from src.services.email_parser import (
    _clean_title,
    detect_free_food,
    extract_rsvp_url,
    match_organization,
    parse_event_email,
)

logger = logging.getLogger(__name__)

CLASSIFICATION_PROMPT = """\
You classify university emails as EVENT or NOT_EVENT.

EVENT = An attendable gathering with a specific date, time, and/or place where people show up in person or online. Examples: talks, lectures, concerts, workshops, movie nights, socials, meetings, info sessions, study breaks, performances.

NOT_EVENT = Course announcements, course registration info, job/internship postings, hiring notices, application deadlines, scholarships, newsletter digests, administrative notices, policy updates, meeting minutes (past), surveys.

Examples:
INPUT: "Join us Friday at 7pm at Norris for movie night! Free popcorn!"
OUTPUT: EVENT

INPUT: "Students can take a fall-quarter POLI_SCI 390 course, taught by Professor Smith. Enrollment begins Nov 9."
OUTPUT: NOT_EVENT

INPUT: "Workshop on resume writing, March 28 at 3pm, Career Services. RSVP required."
OUTPUT: EVENT

INPUT: "We are hiring a research assistant. Application deadline April 1."
OUTPUT: NOT_EVENT

INPUT: "The Buffett Institute invites you to a talk by Dr. Jones on April 3 at 12:30pm."
OUTPUT: EVENT

INPUT: "Reminder: Spring quarter course registration opens Monday."
OUTPUT: NOT_EVENT

Now classify this email:
Subject: {subject}
Body (first 1000 chars): {body_preview}

Respond with ONLY one word: EVENT or NOT_EVENT"""

EXTRACTION_PROMPT = """\
Extract event details from this email. Return ONLY valid JSON with no markdown formatting, no backticks, no explanation.

Subject: {subject}
Body: {body_preview}

Return this exact JSON structure (use null for unknown fields):
{{"title": "event title (concise, not the full email subject)", "date": "YYYY-MM-DD", "start_time": "HH:MM", "end_time": "HH:MM or null", "location": "venue name and room", "description": "1-2 sentence summary", "rsvp_url": "URL or null", "has_free_food": true/false, "category": "academic or social or career or arts or sports or other"}}

Important:
- title should be a clean event name, not the email subject line verbatim
- date must be in YYYY-MM-DD format
- times in 24-hour HH:MM format
- category must be exactly one of: academic, social, career, arts, sports, other
- has_free_food is true ONLY if free food/drinks/snacks are explicitly mentioned
- If multiple events are described, return a JSON array of objects"""

VALID_CATEGORIES = {"academic", "social", "career", "arts", "sports", "other"}

# Timeout for each Ollama call in seconds
_OLLAMA_TIMEOUT = 30.0


def _get_ollama_client() -> ollama.Client:
    """Create an Ollama client pointing at the configured URL.

    Returns:
        An ``ollama.Client`` instance.
    """
    return ollama.Client(host=settings.ollama_url, timeout=_OLLAMA_TIMEOUT)


def _chat_sync(client: ollama.Client, model: str, prompt: str) -> str:
    """Send a chat message to Ollama and return the response text.

    Args:
        client: Ollama client instance.
        model: Model name to use.
        prompt: User prompt text.

    Returns:
        The model's response content as a string.
    """
    response = client.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0},
    )
    return response["message"]["content"].strip()


async def _chat(client: ollama.Client, model: str, prompt: str) -> str:
    """Async wrapper around the synchronous Ollama chat call.

    Args:
        client: Ollama client instance.
        model: Model name to use.
        prompt: User prompt text.

    Returns:
        The model's response content as a string.
    """
    return await asyncio.to_thread(_chat_sync, client, model, prompt)


def _resolve_model(client: ollama.Client) -> str:
    """Determine which Ollama model to use.

    Tries the configured model first, then falls back to ``gemma3:1b``.

    Args:
        client: Ollama client instance.

    Returns:
        Model name string.

    Raises:
        ConnectionError: If Ollama is unreachable.
        RuntimeError: If no suitable model is found.
    """
    primary = settings.ollama_model
    fallback = "gemma3:1b"

    try:
        models_resp = client.list()
        available = {m.model for m in models_resp.models}
    except Exception as exc:
        raise ConnectionError(f"Cannot reach Ollama at {settings.ollama_url}: {exc}") from exc

    if primary in available:
        return primary
    # Check without tag
    primary_base = primary.split(":")[0]
    for m in available:
        if m.startswith(primary_base):
            logger.info("Exact model %s not found, using %s", primary, m)
            return m

    if fallback in available:
        logger.warning("Model %s not available, falling back to %s", primary, fallback)
        return fallback
    for m in available:
        if m.startswith("gemma"):
            logger.warning("Using available gemma model: %s", m)
            return m

    raise RuntimeError(f"No suitable model found. Available: {available}")


def _parse_extraction_json(raw: str) -> list[dict]:
    """Parse the LLM extraction response into a list of event dicts.

    Handles both single objects and arrays, and strips markdown code fences.

    Args:
        raw: Raw LLM response string.

    Returns:
        List of event dictionaries.

    Raises:
        ValueError: If the JSON cannot be parsed.
    """
    # Strip markdown code fences
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    parsed = json.loads(cleaned)
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return parsed
    raise ValueError(f"Unexpected JSON type: {type(parsed)}")


def _normalize_category(cat: str | None) -> EventCategory:
    """Convert a category string to an EventCategory enum value.

    Args:
        cat: Category string from LLM output.

    Returns:
        Matching EventCategory, defaults to OTHER.
    """
    if not cat:
        return EventCategory.OTHER
    cat_lower = cat.lower().strip()
    if cat_lower in VALID_CATEGORIES:
        return EventCategory(cat_lower)
    return EventCategory.OTHER


def _build_event(
    data: dict,
    org: str | None,
    fallback_rsvp: str | None,
    fallback_free_food: bool,
    subject: str,
    body: str,
) -> EventCreate:
    """Convert an extracted event dict into an EventCreate schema.

    Applies fallback values for RSVP URL and free food detection.

    Args:
        data: Extracted event data dict from LLM.
        org: Organization name from email headers.
        fallback_rsvp: RSVP URL from regex extraction.
        fallback_free_food: Free food flag from regex detection.
        subject: Original email subject.
        body: Original email body.

    Returns:
        EventCreate instance.
    """
    # Title
    title = _clean_title(data.get("title") or subject)

    # Date + times
    date_str = data.get("date")
    start_time_str = data.get("start_time")
    end_time_str = data.get("end_time")

    try:
        event_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None
    except (ValueError, TypeError):
        event_date = None

    start_time = None
    if start_time_str:
        try:
            parts = start_time_str.split(":")
            start_time = time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            pass

    end_time = None
    if end_time_str and end_time_str != "null":
        try:
            parts = end_time_str.split(":")
            end_time = time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            pass

    if event_date and start_time:
        start_dt = datetime.combine(event_date, start_time)
    elif event_date:
        start_dt = datetime.combine(event_date, time(0, 0))
    else:
        start_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    end_dt = datetime.combine(event_date, end_time) if event_date and end_time else None

    # Location
    location = data.get("location")
    if location == "null" or location is None:
        location = None

    # Description
    description = data.get("description")
    if description == "null" or description is None:
        description = None

    # RSVP URL: prefer LLM, fall back to regex
    rsvp_url = data.get("rsvp_url")
    if not rsvp_url or rsvp_url == "null":
        rsvp_url = fallback_rsvp

    # Free food: prefer explicit LLM answer, fall back to regex
    has_free_food = data.get("has_free_food")
    if not isinstance(has_free_food, bool):
        has_free_food = fallback_free_food

    # Category
    category = _normalize_category(data.get("category"))

    return EventCreate(
        title=title,
        description=description,
        start_time=start_dt,
        end_time=end_dt,
        location=location,
        source_name=org,
        rsvp_url=rsvp_url,
        has_free_food=has_free_food,
        category=category,
    )


async def parse_event_with_llm(
    subject: str,
    body: str,
    sender: str | None = None,
    list_id: str = "",
    list_sender: str = "",
) -> list[EventCreate]:
    """Parse an email for events using a local Ollama LLM.

    Performs two LLM calls: classification (EVENT vs NOT_EVENT) then
    extraction of structured event data. Falls back to the regex parser
    if Ollama is unavailable or returns unparseable results.

    Args:
        subject: Email subject line.
        body: Email body text.
        sender: Sender email address.
        list_id: List-Id header value.
        list_sender: Sender header value (LISTSERV).

    Returns:
        List of EventCreate schemas (may be empty).
    """
    # Pre-compute shared values
    org = match_organization(sender, body, list_id=list_id, list_sender=list_sender)
    full_text = f"{subject}\n{body}"
    fallback_rsvp = extract_rsvp_url(full_text)
    fallback_free_food = detect_free_food(full_text)

    try:
        client = _get_ollama_client()
        model = _resolve_model(client)
    except (ConnectionError, RuntimeError) as exc:
        logger.warning("Ollama unavailable (%s), falling back to regex parser", exc)
        return parse_event_email(
            subject, body, sender, list_id=list_id, list_sender=list_sender,
        )

    # Step 1: Classification
    try:
        classification_prompt = CLASSIFICATION_PROMPT.format(
            subject=subject,
            body_preview=body[:1000],
        )
        classification = await _chat(client, model, classification_prompt)
        classification_clean = classification.strip().upper()

        if "NOT_EVENT" in classification_clean:
            logger.debug("LLM classified email as NOT_EVENT: %s", subject)
            return []

        if "EVENT" not in classification_clean:
            logger.warning(
                "Ambiguous LLM classification '%s' for '%s', treating as EVENT",
                classification,
                subject,
            )
    except Exception as exc:
        logger.warning("LLM classification failed (%s), falling back to regex", exc)
        return parse_event_email(
            subject, body, sender, list_id=list_id, list_sender=list_sender,
        )

    # Step 2: Extraction
    try:
        extraction_prompt = EXTRACTION_PROMPT.format(
            subject=subject,
            body_preview=body[:2000],
        )
        raw_response = await _chat(client, model, extraction_prompt)
        event_dicts = _parse_extraction_json(raw_response)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "LLM extraction JSON parse failed (%s), falling back to regex", exc,
        )
        return parse_event_email(
            subject, body, sender, list_id=list_id, list_sender=list_sender,
        )
    except Exception as exc:
        logger.warning("LLM extraction failed (%s), falling back to regex", exc)
        return parse_event_email(
            subject, body, sender, list_id=list_id, list_sender=list_sender,
        )

    # Build EventCreate objects
    events: list[EventCreate] = []
    for data in event_dicts:
        try:
            event = _build_event(
                data, org, fallback_rsvp, fallback_free_food, subject, body,
            )
            events.append(event)
        except Exception as exc:
            logger.warning("Failed to build event from LLM data: %s", exc)
            continue

    if not events:
        logger.warning("LLM returned no valid events, falling back to regex")
        return parse_event_email(
            subject, body, sender, list_id=list_id, list_sender=list_sender,
        )

    return events
