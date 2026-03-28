"""Extract event information from email text using pattern matching.

Looks for common patterns in event announcement emails:
- Date patterns: "March 27, 2026", "3/27/2026", "Friday, March 27"
- Time patterns: "7:00 PM", "7-9pm", "at 7pm"
- Location patterns: "Location: ...", "Where: ...", "at Norris University Center"
- Known NU buildings: Tech, Norris, Kresge, Fisk, Harris, Pick-Staiger, etc.
"""

import re
from datetime import date, datetime, time, timedelta

from dateutil import parser as dateutil_parser

from src.schemas.event import EventCreate

NU_BUILDINGS = [
    "Norris University Center", "Norris", "Tech", "Technological Institute",
    "Kresge", "Fisk Hall", "Harris Hall", "University Hall", "Annie May Swift",
    "Pick-Staiger", "Lutkin Hall", "Cahn Auditorium", "Ryan Field",
    "Welsh-Ryan Arena", "Henry Crown", "Deering Library", "Main Library",
    "Mudd Library", "Block Museum", "Dearborn Observatory", "Pancoe",
    "Simpson Querrey", "Louis Simpson", "Jacobs Center", "Ford Motor Company",
    "Garage", "Parkes Hall", "1800 Sherman", "Scott Hall", "Annenberg Hall",
    "McCormick Tribune", "Wirtz Center", "Shanley Hall", "Allison Hall",
    "Elder Hall", "Foster House", "Willard", "Plex",
    "Bobb Hall", "Rogers House", "Sargent Hall", "Shepard Hall",
]

# Sort by length descending so longer names match first (e.g. "Norris University Center" before "Norris")
NU_BUILDINGS_SORTED = sorted(NU_BUILDINGS, key=len, reverse=True)

WEEKDAY_NAMES = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
}

# Regex for time patterns
_TIME_RE = re.compile(
    r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM|a\.m\.|p\.m\.)',
    re.IGNORECASE,
)

# Time range: "7-9pm", "7:00 PM - 9:00 PM", "from 7pm to 9pm"
_TIME_RANGE_RE = re.compile(
    r'(?:from\s+)?'
    r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM|a\.m\.|p\.m\.)?'
    r'\s*[-–—to]+\s*'
    r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM|a\.m\.|p\.m\.)',
    re.IGNORECASE,
)

# Date: "March 27, 2026" / "Mar 27, 2026" / "March 27th, 2026"
_DATE_LONG_RE = re.compile(
    r'(january|february|march|april|may|june|july|august|september|october|november|december'
    r'|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)'
    r'\.?\s+(\d{1,2})(?:st|nd|rd|th)?'
    r'(?:\s*[-–,]\s*(\d{4}|\d{2}))?',
    re.IGNORECASE,
)

# Date: "3/27/2026" / "03/27/26"
_DATE_NUMERIC_RE = re.compile(
    r'(\d{1,2})/(\d{1,2})/(\d{2,4})',
)

# Date: "3/31" / "4/2" (no year)
_DATE_NUMERIC_NOYEAR_RE = re.compile(
    r'(\d{1,2})/(\d{1,2})(?!\s*/|\d)',
)

# Relative day: "this Friday" / "next Tuesday"
_RELATIVE_DAY_RE = re.compile(
    r'(this|next)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
    re.IGNORECASE,
)

# "Friday, March 27" (weekday prefix before a long date)
_WEEKDAY_DATE_RE = re.compile(
    r'(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*,?\s*'
    r'(january|february|march|april|may|june|july|august|september|october|november|december'
    r'|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)'
    r'\.?\s+(\d{1,2})(?:st|nd|rd|th)?'
    r'(?:\s*[-–,]\s*(\d{4}|\d{2}))?',
    re.IGNORECASE,
)

# Location label patterns
_LOCATION_LABEL_RE = re.compile(
    r'(?:location|where|place|venue)\s*:\s*(.+)',
    re.IGNORECASE,
)


def _clean_title(title: str, max_len: int = 490) -> str:
    """Clean and truncate an event title to fit the database constraint.

    Strips leading/trailing whitespace and punctuation fragments,
    and truncates with ellipsis if needed.
    """
    title = title.strip().strip(",;:–—-").strip()
    if not title:
        return "Untitled Event"
    if len(title) > max_len:
        title = title[:max_len].rsplit(" ", 1)[0] + "…"
    return title


def _parse_ampm(ampm: str) -> str:
    """Normalize AM/PM indicator."""
    return ampm.replace(".", "").upper().strip()


def _build_time(hour: int, minute: int, ampm: str) -> time:
    """Convert 12-hour time to a time object."""
    ampm = _parse_ampm(ampm)
    if ampm == "PM" and hour != 12:
        hour += 12
    elif ampm == "AM" and hour == 12:
        hour = 0
    return time(hour, minute)


def extract_dates(text: str, reference_date: date | None = None) -> list[date]:
    """Find all date mentions in *text*.

    Args:
        text: Email body or subject text.
        reference_date: Base date for resolving relative references
            (defaults to today).

    Returns:
        List of ``date`` objects found, in order of appearance.
    """
    if reference_date is None:
        reference_date = date.today()

    found: list[date] = []

    # Relative days: "this Friday", "next Tuesday"
    for match in _RELATIVE_DAY_RE.finditer(text):
        modifier = match.group(1).lower()
        day_name = match.group(2).lower()
        target_wd = WEEKDAY_NAMES[day_name]
        current_wd = reference_date.weekday()
        delta = (target_wd - current_wd) % 7
        if delta == 0:
            delta = 7
        if modifier == "next":
            delta += 7 if delta <= 7 and modifier == "next" and delta == (target_wd - current_wd) % 7 else 0
            # "next" means the occurrence in the following week
            delta = (target_wd - current_wd) % 7
            if delta == 0:
                delta = 7
            delta += 7  # always push to next week for "next"
            delta -= 7  # undo double-add; just add 7 if same week already passed
            # Simpler: "next X" = first X that is >7 days away OR in the next calendar week
            days_ahead = (target_wd - current_wd) % 7
            if days_ahead == 0:
                days_ahead = 7
            delta = days_ahead + 7
        found.append(reference_date + timedelta(days=delta))

    # Weekday + month-day: "Friday, March 28"
    for match in _WEEKDAY_DATE_RE.finditer(text):
        month_str = match.group(1).lower().rstrip(".")
        day = int(match.group(2))
        year_str = match.group(3)
        month = MONTH_NAMES.get(month_str)
        if month is None:
            continue
        if year_str:
            year = int(year_str)
            if year < 100:
                year += 2000
        else:
            year = reference_date.year
            # If date already passed this year, assume next year
            try:
                candidate = date(year, month, day)
            except ValueError:
                continue
            if candidate < reference_date:
                year += 1
        try:
            found.append(date(year, month, day))
        except ValueError:
            continue

    # Long-form dates: "March 27, 2026"
    # Avoid re-matching dates already captured by _WEEKDAY_DATE_RE
    for match in _DATE_LONG_RE.finditer(text):
        # Check if this match is part of a weekday-date (skip if preceded by weekday)
        start = match.start()
        prefix = text[max(0, start - 20):start].lower()
        if any(wd in prefix for wd in WEEKDAY_NAMES):
            continue
        month_str = match.group(1).lower().rstrip(".")
        day = int(match.group(2))
        year_str = match.group(3)
        month = MONTH_NAMES.get(month_str)
        if month is None:
            continue
        if year_str:
            year = int(year_str)
            if year < 100:
                year += 2000
        else:
            year = reference_date.year
            try:
                candidate = date(year, month, day)
            except ValueError:
                continue
            if candidate < reference_date:
                year += 1
        try:
            d = date(year, month, day)
            if d not in found:
                found.append(d)
        except ValueError:
            continue

    # Numeric dates with year: "3/27/2026"
    numeric_with_year_spans: list[tuple[int, int]] = []
    for match in _DATE_NUMERIC_RE.finditer(text):
        month = int(match.group(1))
        day = int(match.group(2))
        year = int(match.group(3))
        if year < 100:
            year += 2000
        try:
            d = date(year, month, day)
            if d not in found:
                found.append(d)
            numeric_with_year_spans.append((match.start(), match.end()))
        except ValueError:
            continue

    # Numeric dates without year: "3/31", "4/2"
    for match in _DATE_NUMERIC_NOYEAR_RE.finditer(text):
        # Skip if already consumed by a full numeric date
        if any(s <= match.start() < e for s, e in numeric_with_year_spans):
            continue
        month = int(match.group(1))
        day = int(match.group(2))
        if month < 1 or month > 12 or day < 1 or day > 31:
            continue
        year = reference_date.year
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if candidate < reference_date:
            year += 1
        try:
            d = date(year, month, day)
            if d not in found:
                found.append(d)
        except ValueError:
            continue

    return found


def extract_times(text: str) -> list[tuple[time, time | None]]:
    """Find all time mentions in *text*.

    Args:
        text: Email body or subject text.

    Returns:
        List of (start_time, end_time_or_None) tuples.
    """
    results: list[tuple[time, time | None]] = []
    used_spans: list[tuple[int, int]] = []

    # First look for time ranges
    for match in _TIME_RANGE_RE.finditer(text):
        h1 = int(match.group(1))
        m1 = int(match.group(2) or 0)
        ampm1 = match.group(3)
        h2 = int(match.group(4))
        m2 = int(match.group(5) or 0)
        ampm2 = match.group(6)

        # If first time has no AM/PM, inherit from second
        if ampm1 is None:
            ampm1 = ampm2

        t1 = _build_time(h1, m1, ampm1)
        t2 = _build_time(h2, m2, ampm2)
        results.append((t1, t2))
        used_spans.append((match.start(), match.end()))

    # Then standalone times (skip those already consumed by ranges)
    for match in _TIME_RE.finditer(text):
        # Skip if overlapping with a range match
        if any(s <= match.start() < e for s, e in used_spans):
            continue
        h = int(match.group(1))
        m = int(match.group(2) or 0)
        ampm = match.group(3)
        t = _build_time(h, m, ampm)
        results.append((t, None))

    return results


def extract_location(text: str) -> str | None:
    """Find location mentions in *text*.

    Checks for explicit labels ("Location: ...", "Where: ...") first,
    then falls back to scanning for known NU building names.

    Args:
        text: Email body or subject text.

    Returns:
        Location string if found, else None.
    """
    # Check for labeled locations
    for match in _LOCATION_LABEL_RE.finditer(text):
        loc = match.group(1).strip()
        # Take the rest of the line
        loc = loc.split("\n")[0].strip()
        if loc:
            return loc

    # Scan for known NU buildings with surrounding context
    text_lower = text.lower()
    for building in NU_BUILDINGS_SORTED:
        idx = text_lower.find(building.lower())
        if idx != -1:
            # Try to capture room number after building name
            after = text[idx + len(building):idx + len(building) + 40]
            room_match = re.match(r'[\s,]*(?:Room\s+)?(\w{1,10})', after, re.IGNORECASE)
            if room_match and re.search(r'\d', room_match.group(1)):
                return f"{building}, {room_match.group(0).strip().lstrip(',').strip()}"
            # Check for "in <building>" or "at <building>" pattern — return building
            prefix_start = max(0, idx - 5)
            prefix = text[prefix_start:idx].lower().strip()
            if prefix.endswith(("in", "at", ":")) or idx == 0 or text[idx - 1] in ("\n", " "):
                return building

    return None


def _extract_listserv_name(list_id: str, list_sender: str) -> str | None:
    """Extract the LISTSERV list name from List-Id or Sender headers.

    Examples:
        - List-Id: ``ANIME.LISTSERV.IT.NORTHWESTERN.EDU`` → ``ANIME``
        - List-Id: ``<ANIME.LISTSERV.IT.NORTHWESTERN.EDU>`` → ``ANIME``
        - Sender: ``owner-ANIME@LISTSERV.IT.NORTHWESTERN.EDU`` → ``ANIME``

    Args:
        list_id: Value of the List-Id email header.
        list_sender: Value of the Sender email header.

    Returns:
        Uppercase list name if found, else None.
    """
    # Try List-Id first: "ANIME.LISTSERV.IT.NORTHWESTERN.EDU"
    if list_id:
        cleaned = list_id.strip().strip("<>").strip()
        parts = cleaned.split(".")
        if len(parts) >= 2 and "LISTSERV" in cleaned.upper():
            # The list name is everything before ".LISTSERV"
            listserv_idx = next(
                (i for i, p in enumerate(parts) if p.upper() == "LISTSERV"),
                None,
            )
            if listserv_idx and listserv_idx > 0:
                return ".".join(parts[:listserv_idx]).upper()

    # Try Sender: "owner-ANIME@LISTSERV.IT.NORTHWESTERN.EDU"
    if list_sender and "LISTSERV" in list_sender.upper():
        # Extract email from "Name <email>" format
        if "<" in list_sender:
            list_sender = list_sender.split("<")[1].split(">")[0]
        local = list_sender.split("@")[0]
        if local.lower().startswith("owner-"):
            return local[6:].upper()

    return None


def match_organization(
    sender: str | None,
    body: str,
    list_id: str = "",
    list_sender: str = "",
) -> str | None:
    """Try to identify the sending organization.

    Checks LISTSERV headers first (List-Id, Sender), then falls back to
    heuristics on the From address.

    Args:
        sender: Email address of the sender (From header).
        body: Email body text.
        list_id: Value of the List-Id header (from LISTSERV).
        list_sender: Value of the Sender header (from LISTSERV).

    Returns:
        Organization name guess, or None.
    """
    # Try LISTSERV headers for list name
    listserv_name = _extract_listserv_name(list_id, list_sender)
    if listserv_name:
        # Try to look up the org in the database by listserv_name.
        # For now, return the list name formatted nicely.
        # The poller can do the DB lookup and override later.
        return f"LISTSERV:{listserv_name}"

    if sender:
        # Extract the local part before @
        local = sender.split("@")[0].lower().replace(".", " ").replace("-", " ").replace("_", " ")
        return local.title() if local else None
    return None


def parse_event_email(
    subject: str,
    body: str,
    sender: str | None = None,
    reference_date: date | None = None,
    list_id: str = "",
    list_sender: str = "",
) -> list[EventCreate]:
    """Parse an email for event information and return EventCreate schemas.

    One email might announce multiple events. Each event needs at minimum
    a date and a title (derived from the subject or body).

    Args:
        subject: Email subject line.
        body: Email body text.
        sender: Sender email address (optional).
        reference_date: Base date for relative date resolution.
        list_id: Value of the List-Id header (from LISTSERV).
        list_sender: Value of the Sender header (from LISTSERV).

    Returns:
        List of EventCreate schemas (may be empty if no events found).
    """
    # Prefer explicit dates in body over relative dates in subject
    dates = extract_dates(body, reference_date=reference_date)
    if not dates:
        dates = extract_dates(subject, reference_date=reference_date)
    full_text = f"{subject}\n{body}"
    times = extract_times(full_text)
    location = extract_location(body)
    org = match_organization(sender, body, list_id=list_id, list_sender=list_sender)

    if not dates:
        return []

    events: list[EventCreate] = []

    # Check if this looks like a multi-event email (multiple dates with inline descriptions)
    # Heuristic: if multiple dates AND the body has line-by-line event descriptions
    lines = body.strip().split("\n")
    multi_event_lines: list[tuple[date, time | None, time | None, str, str | None]] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        line_dates = extract_dates(line, reference_date=reference_date)
        line_times = extract_times(line)
        if line_dates:
            # This line contains an event
            d = line_dates[0]
            t_start = line_times[0][0] if line_times else None
            t_end = line_times[0][1] if line_times else None
            line_location = extract_location(line)
            # Extract event description from the line (remove date/time cruft)
            desc = line
            # Remove common prefixes like "Monday 3/31 at 4pm - "
            desc = re.sub(
                r'^(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*',
                '', desc, flags=re.IGNORECASE
            )
            desc = re.sub(r'^\d{1,2}/\d{1,2}(?:/\d{2,4})?\s*', '', desc)
            desc = re.sub(r'(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)\s*', '', desc, flags=re.IGNORECASE)
            desc = re.sub(r'^[-–—]\s*', '', desc).strip()
            multi_event_lines.append((d, t_start, t_end, desc, line_location))

    if len(multi_event_lines) > 1:
        # Multi-event email
        for d, t_start, t_end, desc, line_loc in multi_event_lines:
            title = _clean_title(desc.split("(")[0].strip() if desc else subject)
            if not title or title == "Untitled Event":
                title = _clean_title(subject)
            start_dt = datetime.combine(d, t_start) if t_start else datetime.combine(d, time(0, 0))
            end_dt = datetime.combine(d, t_end) if t_end else None
            events.append(EventCreate(
                title=title,
                description=desc or None,
                start_time=start_dt,
                end_time=end_dt,
                location=line_loc or location,
                source_name=org,
            ))
    else:
        # Single event email
        d = dates[0]
        t_start = times[0][0] if times else None
        t_end = times[0][1] if times else None
        start_dt = datetime.combine(d, t_start) if t_start else datetime.combine(d, time(0, 0))
        end_dt = datetime.combine(d, t_end) if t_end else None

        events.append(EventCreate(
            title=_clean_title(subject),
            description=body,
            start_time=start_dt,
            end_time=end_dt,
            location=location,
            source_name=org,
        ))

    return events
