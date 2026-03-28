"""Fast regex-based pre-filter for Instagram captions.

Screens captions BEFORE sending them to the LLM, saving ~70% of
Ollama calls. Only captions that look like they might describe
an attendable event get passed to the LLM.

This runs in microseconds vs 10-30 seconds per LLM call.
"""

import re
from datetime import date

# --- Positive signals: looks like it might be an event ---

# Date patterns
_DATE_PATTERNS = re.compile(
    r'\b('
    r'\d{1,2}/\d{1,2}'                           # 3/28, 04/05
    r'|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}'  # March 28, Apr 5
    r'|\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)'  # 28th of March
    r'|(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)'  # Day names
    r'|(?:this|next)\s+(?:mon|tue|wed|thu|fri|sat|sun)'  # this Friday
    r'|tonight|tomorrow|today'
    r')\b',
    re.IGNORECASE,
)

# Time patterns
_TIME_PATTERNS = re.compile(
    r'\b('
    r'\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM|a\.m\.|p\.m\.)'  # 7pm, 7:00 PM
    r'|\d{1,2}\s*[-–]\s*\d{1,2}\s*(?:am|pm)'                # 7-9pm
    r'|noon|midnight'
    r')\b',
    re.IGNORECASE,
)

# Event action words
_EVENT_WORDS = re.compile(
    r'\b('
    r'join\s+us|come\s+(?:out|through|to|hang)|pull\s+up|rsvp|register'
    r'|sign\s+up|don\'?t\s+miss|save\s+the\s+date|mark\s+your\s+calendar'
    r'|tickets?|free\s+(?:event|admission|entry)|open\s+to\s+(?:all|everyone)'
    r'|doors?\s+(?:open|at)|(?:see|catch)\s+you\s+there'
    r'|link\s+in\s+bio|swipe\s+up'
    r')\b',
    re.IGNORECASE,
)

# Event type words
_EVENT_TYPE_WORDS = re.compile(
    r'\b('
    r'meeting|workshop|info\s*session|panel|talk|lecture|seminar'
    r'|concert|performance|show|screening|showcase|recital'
    r'|social|mixer|gala|banquet|dinner|brunch|potluck'
    r'|game\s+night|movie\s+night|trivia|karaoke|open\s+mic'
    r'|fundraiser|benefit|charity|volunteering'
    r'|competition|tournament|hackathon|case\s+comp'
    r'|rush|recruitment|audition|tryout'
    r'|practice|rehearsal|meeting'
    r'|celebration|festival|cultural\s+show'
    r')\b',
    re.IGNORECASE,
)

# Location signals
_LOCATION_PATTERNS = re.compile(
    r'\b('
    r'norris|tech|kresge|fisk|harris|scott|ford|pick.staiger'
    r'|cahn|lutkin|welsh.ryan|henry\s+crown|annenberg|wirtz'
    r'|allison|bobb|elder|foster|willard|shepard|sargent'
    r'|jacobs|pancoe|garage|mudd|deering|block\s+museum'
    r'|room\s+\d+|auditorium|hall|theater|theatre|lounge|ballroom'
    r'|guild|studio|center|campus|quad|lakefill'
    r'|evanston|chicago|downtown'
    r')\b',
    re.IGNORECASE,
)

# --- Negative signals: probably NOT an event ---

_NOT_EVENT_PATTERNS = re.compile(
    r'\b('
    r'throwback|tbt|#tbt|recap|highlights?|looking\s+back'
    r'|congratulations?|congrats|shoutout|shout\s*out|s/o'
    r'|happy\s+birthday|welcome\s+(?:to\s+the\s+team|our\s+new)'
    r'|meet\s+(?:the|our)\s+(?:team|board|e-?board|exec)'
    r'|we\'?re\s+hiring|apply\s+(?:now|to\s+(?:be|join))|applications?\s+(?:open|due|close)'
    r'|deadline|due\s+(?:date|by)|submit\s+by'
    r'|thank\s+you|thanks\s+(?:to|for)|grateful'
    r')\b',
    re.IGNORECASE,
)


def caption_looks_like_event(caption: str) -> tuple[bool, int]:
    """Fast check if a caption might describe an event.

    Scores the caption on event-like signals and returns whether it
    passes the threshold. This is intentionally permissive — false
    positives are fine (the LLM catches them), false negatives are bad.

    Args:
        caption: Instagram post caption text.

    Returns:
        Tuple of (passes_threshold, score).
    """
    if not caption or len(caption) < 30:
        return False, 0

    text = caption.lower()
    score = 0

    # Positive signals
    if _DATE_PATTERNS.search(caption):
        score += 3
    if _TIME_PATTERNS.search(caption):
        score += 3
    if _EVENT_WORDS.search(caption):
        score += 2
    if _EVENT_TYPE_WORDS.search(caption):
        score += 2
    if _LOCATION_PATTERNS.search(caption):
        score += 2

    # Negative signals
    if _NOT_EVENT_PATTERNS.search(caption):
        score -= 3

    # Very short captions are unlikely events
    if len(caption) < 80:
        score -= 1

    # Threshold: need at least some date/time signal + something else
    return score >= 3, score
