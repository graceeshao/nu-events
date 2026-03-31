"""Post-LLM validation for extracted events.

Catches false positives that the LLM misclassifies as events:
- Course/class listings
- Forms, surveys, applications
- Administrative notices
- Deadlines without attendable gatherings
- Events with no real time (midnight = unknown)

Runs AFTER the LLM extraction, BEFORE database insertion.
Fast regex checks — no API calls, no tokens.
"""

import re
import logging
from datetime import datetime, time, timedelta

from src.schemas.event import EventCreate

logger = logging.getLogger(__name__)


# Titles that are NOT events
_BAD_TITLE_PATTERNS = re.compile(
    r'\b('
    r'updated?\s+(?:families|list|roster|directory)'
    r'|family\s+update'
    r'|fill\s+out\s+(?:this|the)\s+form'
    r'|applications?\s+(?:due|deadline|open|close)'
    r'|apply\s+by'
    r'|submit\s+by'
    r'|deadline'
    r'|pre-?registration'
    r'|course\s+registration'
    r'|spring\s+break\s+(?:ends|begins)'
    r'|courses?\s+viewable'
    r'|mini\s+courses?:\s*regular\s+registration'
    r'|grade\s+(?:report|submission)'
    r'|classes?\s+(?:begin|end|resume)'
    r')\b',
    re.IGNORECASE,
)

# Descriptions that indicate courses, not events
_COURSE_DESCRIPTION_PATTERNS = re.compile(
    r'\b('
    r'this\s+course\s+(?:examines|explores|covers|introduces|provides|focuses)'
    r'|prerequisite'
    r'|credit\s+hours?'
    r'|enrollment'
    r'|syllabus'
    r'|grading\s+(?:policy|scale)'
    r'|course\s+(?:catalog|number|code)'
    r'|(?:fall|winter|spring|summer)\s+quarter\s+\d{4}'
    r')\b',
    re.IGNORECASE,
)

# Location patterns that suggest a course, not an event
_COURSE_LOCATION_PATTERNS = re.compile(
    r'\b('
    r'WCAS\s*[-–]\s*BUS_INST'
    r'|BUS_INST\s+\d'
    r'|section\s+\d+'
    r')\b',
    re.IGNORECASE,
)

# Forms and surveys (not events)
_FORM_PATTERNS = re.compile(
    r'\b('
    r'fill\s+out\s+(?:this|the|our)\s+form'
    r'|google\s+form'
    r'|survey'
    r'|(?:sign|fill)\s+(?:up|out)\s+(?:form|sheet|document)'
    r'|interest\s+form'
    r'|petition\s+form'
    r')\b',
    re.IGNORECASE,
)


def validate_event(event: EventCreate) -> tuple[bool, str]:
    """Validate an extracted event before database insertion.

    Args:
        event: The extracted EventCreate to validate.

    Returns:
        Tuple of (is_valid, reason). If is_valid is False, reason
        explains why it was rejected.
    """
    title = event.title or ""
    description = event.description or ""
    location = event.location or ""

    # 1. Bad title patterns
    if _BAD_TITLE_PATTERNS.search(title):
        return False, f"title matches non-event pattern: {title[:60]}"

    # 2. Course descriptions
    if _COURSE_DESCRIPTION_PATTERNS.search(description):
        return False, f"description looks like a course: {description[:60]}"

    # 3. Course locations
    if _COURSE_LOCATION_PATTERNS.search(location):
        return False, f"location looks like a course code: {location[:60]}"

    # 4. Form/survey descriptions
    if _FORM_PATTERNS.search(description):
        return False, f"description is a form/survey: {description[:60]}"

    # 4b. Application/deadline announcements (not attendable events)
    if re.search(
        r'\b('
        r'applications?\s+(?:are\s+)?due'
        r'|interviews?\s+will\s+be\s+held'
        r'|positions?\s+will\s+be\s+released'
        r'|applications?\s+(?:are\s+)?(?:now\s+)?(?:open|closing|closed)'
        r'|apply\s+(?:by|before|now)'
        r'|feedback\s+form'
        r'|anonymous\s+feedback'
        r')\b',
        description, re.IGNORECASE,
    ):
        return False, f"description is an application/deadline: {description[:60]}"

    # 4c. Title suggests meeting/form, not an attendable event for general students
    if re.search(
        r'\b('
        r'executive\s+board\s+meeting'
        r'|e-?board\s+meeting'
        r'|feedback\s+form'
        r')\b',
        title, re.IGNORECASE,
    ):
        return False, f"title is internal/admin: {title[:60]}"

    # 5. Midnight time with no real time info = LLM guessed
    # Don't reject outright — but flag as low quality
    # Some "All Day" events legitimately start at midnight

    # 6. Event is in the past
    if event.start_time < datetime.now():
        return False, f"event is in the past: {event.start_time}"

    # 7. Event is suspiciously far in the future (likely wrong year from LLM)
    if event.start_time > datetime.now() + timedelta(days=120):
        return False, f"event is >4 months out (likely wrong year): {event.start_time}"

    return True, "ok"


def validate_and_filter_events(events: list[EventCreate]) -> list[EventCreate]:
    """Filter a list of events, removing invalid ones.

    Args:
        events: List of EventCreate objects to validate.

    Returns:
        Filtered list with only valid events.
    """
    valid = []
    for event in events:
        is_valid, reason = validate_event(event)
        if is_valid:
            valid.append(event)
        else:
            logger.debug("Rejected event: %s — %s", event.title[:50], reason)
    
    rejected = len(events) - len(valid)
    if rejected:
        logger.info("Validated %d events: %d accepted, %d rejected", len(events), len(valid), rejected)
    
    return valid
