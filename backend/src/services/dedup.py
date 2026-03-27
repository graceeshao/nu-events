"""Deduplication key generation for events.

Produces a deterministic key from an event's title, start time, and location
so that repeated scraper runs don't insert duplicate rows.
"""

import hashlib
import re
from datetime import datetime


def _normalize(text: str) -> str:
    """Lowercase, strip whitespace, and collapse multiple spaces."""
    return re.sub(r"\s+", " ", text.strip().lower())


def generate_dedup_key(
    title: str,
    start_time: datetime,
    location: str | None = None,
) -> str:
    """Generate a unique dedup key from event attributes.

    Args:
        title: Event title.
        start_time: Event start datetime.
        location: Event location (optional).

    Returns:
        A SHA-256 hex digest (first 32 chars) used as the dedup_key.
    """
    parts = [
        _normalize(title),
        start_time.isoformat(),
        _normalize(location) if location else "",
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
