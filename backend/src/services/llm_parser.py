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
You classify university emails. Read the ENTIRE email body carefully.

Does this email describe or announce one or more ATTENDABLE EVENTS?

ATTENDABLE EVENT = A specific gathering where people physically show up or join online at a scheduled date and time. Examples: talks, lectures, concerts, workshops, movie nights, socials, meetings, info sessions, study breaks, performances, panels, conferences, dinners, shows.

NOT AN EVENT (even if dates are mentioned):
- Subscription confirmations and welcome messages
- Course announcements / course registration / pre-registration
- Job/internship postings and hiring notices
- Application or recruitment DEADLINES ("Apply by Friday", "Deadline March 31")
- Company recruiting emails (e.g. recruiting programs, launch programs, "opportunities")
- Election/voting emails ("Vote for your new board", "JUST VOTE")
- Newsletters that only summarize past events or link to other things without specific events
- Administrative notices, policy updates
- Org recruitment that only has a deadline but no specific attendable gathering

IS an event (people physically show up or join live):
- Competitions (case competitions, hackathons) — attendable
- Conferences, panels, talks, lectures, workshops, seminars
- Social events, performances, dinners, movie nights, cultural shows
- Info sessions — attendable even if about careers/business
- Club recruitment IF the email describes a specific gathering with date+time+place (e.g. "Rush info session at Norris on Friday at 7pm" = EVENT, but "Apply to rush by Friday" = NOT EVENT)
- Volunteering events with a specific time and place

KEY DISTINCTION: Look for a specific time AND place where people gather. Deadlines and application dates are NOT events. "Register by March 31" is a deadline. "Join us March 31 at 3pm in Tech L160" is an event.

Read the FULL email body — events are often buried in the text, not just the subject line. One email may contain multiple events.

Subject: {subject}
Full email body:
{body_preview}

Respond with ONLY one word: EVENT or NOT_EVENT"""

EXTRACTION_PROMPT = """\
Extract event details from this university email. Return ONLY valid JSON — no markdown, no backticks, no explanation text.

TODAY'S DATE: {today}
CURRENT ACADEMIC YEAR: {academic_year}

Subject: {subject}
Body: {body_preview}

Return this JSON structure (use null for unknown fields):
{{"title": "...", "date": "YYYY-MM-DD", "start_time": "HH:MM", "end_time": "HH:MM or null", "location": "...", "description": "...", "rsvp_url": "URL or null", "has_free_food": true/false, "category": "academic or social or career or arts or sports or other"}}

CRITICAL RULES FOR DATES:
- The current year is {current_year}. If the email does not explicitly state a year, assume {current_year}.
- Only use a different year if the email EXPLICITLY mentions one (e.g. "2027", "Spring 2027").
- "This Friday", "next Tuesday", "March 31" with no year → {current_year}.
- Dates should be in the FUTURE relative to today ({today}). If a date would be in the past for {current_year}, it likely already happened — still record it with {current_year} unless a different year is explicit.

CRITICAL RULES FOR TITLE:
- The title must be a clean, human-readable event name — like what you'd see on a calendar
- Do NOT copy the email subject verbatim. Extract the actual event name from the body.
- Remove ALL unnecessary words: "TOMORROW!", "THIS SATURDAY!", "Fwd:", "Re:", "[EVENT]", "[STUDENT ORG]", urgency words, dates, times
- Examples of BAD titles: "CELEBRASIA TOMORROW!", "JUST VOTE... JUST VOTE", "EVENT TODAY! Grad School Tell-All", "Next Week's Events at Buffett"
- Examples of GOOD titles: "Celebrasia", "CSA Board Elections", "Grad School Tell-All and Dinner", "Buffett Institute Speaker Series"
- If the email contains a specific event name in the body, use THAT as the title
- Use title case (capitalize major words)

OTHER RULES:
- date in YYYY-MM-DD format
- times in 24-hour HH:MM format
- description: 1-2 sentences summarizing what the event is about
- category: exactly one of academic, social, career, arts, sports, other
- has_free_food: true ONLY if free food/drinks/snacks are explicitly mentioned
- rsvp_url: include any registration, RSVP, or signup links found in the email
- If the email describes MULTIPLE separate events, return a JSON array of objects
- Read the full body carefully — event details are often buried in the text"""

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

    # Year sanity check: if the LLM hallucinated a year far from current,
    # clamp to current year (unless the email explicitly mentions that year).
    if event_date is not None:
        from datetime import date as _date
        _current_year = _date.today().year
        # Allow current year and next year only; anything else is likely wrong
        if event_date.year < _current_year or event_date.year > _current_year + 1:
            try:
                event_date = event_date.replace(year=_current_year)
            except ValueError:
                # e.g. Feb 29 in a non-leap year
                event_date = event_date.replace(year=_current_year, day=28)

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

    # --- Pre-filters: skip obvious non-events without calling the LLM ---
    subject_lower = subject.lower().strip()
    body_lower = body.lower().strip()

    # Subscription confirmations, welcome messages, and their replies
    skip_subject_patterns = [
        "you are now subscribed to the",
        "confirm your subscription to the",
        "re: subscribe",
    ]
    # Also catch "Welcome to X!" (but not "Welcome to the event!")
    if any(p in subject_lower for p in skip_subject_patterns):
        logger.debug("Pre-filter: subscription email skipped: %s", subject)
        return []

    # Welcome messages from LISTSERV
    if subject_lower.startswith("welcome to") and (
        "LISTSERV" in (sender or "") or "listserv" in body_lower[:200]
    ):
        logger.debug("Pre-filter: LISTSERV welcome email skipped: %s", subject)
        return []

    # Job/internship postings (common CBI [POSTING] tag)
    if "[posting]" in subject_lower:
        logger.debug("Pre-filter: job posting skipped: %s", subject)
        return []

    job_phrases = [
        "is hiring", "we are hiring", "job alert",
        "internship posting", "now hiring",
    ]
    if any(p in subject_lower for p in job_phrases):
        logger.debug("Pre-filter: job posting skipped: %s", subject)
        return []

    # Voting/election emails (not attendable events) — catch Re:/Fwd: chains too
    clean_subject = re.sub(r'^(re:\s*|fwd:\s*)+', '', subject_lower, flags=re.IGNORECASE).strip()
    if re.search(r'\bjust vote\b', clean_subject) or clean_subject.endswith("elections"):
        if not re.search(r'\b(at|in|room|hall|center|norris|tech)\b', body_lower[:500]):
            logger.debug("Pre-filter: election/voting email skipped: %s", subject)
            return []

    # Course pre-registration (not an event)
    if "pre-registration" in clean_subject or "pre registration" in clean_subject:
        logger.debug("Pre-filter: course registration skipped: %s", subject)
        return []

    # Application deadlines (not events)
    if re.match(r'^apply\s+to\b', clean_subject) and re.search(r'\bby\s+(friday|monday|tuesday|wednesday|thursday|saturday|sunday|\d)', clean_subject):
        logger.debug("Pre-filter: application deadline skipped: %s", subject)
        return []

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
            body_preview=body,
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
        from datetime import date as _date
        _today = _date.today()
        _year = _today.year
        # Academic year: if we're past August, it's YYYY-(YYYY+1), else (YYYY-1)-YYYY
        _ay = f"{_year}-{_year+1}" if _today.month >= 8 else f"{_year-1}-{_year}"
        extraction_prompt = EXTRACTION_PROMPT.format(
            subject=subject,
            body_preview=body,
            today=_today.isoformat(),
            current_year=_year,
            academic_year=_ay,
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
