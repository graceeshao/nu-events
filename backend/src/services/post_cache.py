"""Simple file-based cache for processed Instagram post shortcodes.

Prevents re-classifying the same post across scraper runs.
Stores shortcodes in a JSON file — lightweight and persistent.
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE_FILE = Path(__file__).parent.parent.parent / "processed_posts.json"
_cache: set[str] | None = None


def _load_cache() -> set[str]:
    """Load processed shortcodes from disk."""
    global _cache
    if _cache is not None:
        return _cache

    if _CACHE_FILE.exists():
        try:
            with open(_CACHE_FILE) as f:
                data = json.load(f)
            _cache = set(data)
            logger.info("Loaded %d processed shortcodes from cache", len(_cache))
        except Exception:
            _cache = set()
    else:
        _cache = set()

    return _cache


def is_processed(shortcode: str) -> bool:
    """Check if a post has already been processed."""
    return shortcode in _load_cache()


def mark_processed(shortcode: str) -> None:
    """Mark a post as processed and persist to disk."""
    cache = _load_cache()
    cache.add(shortcode)
    _save_cache()


def mark_batch_processed(shortcodes: list[str]) -> None:
    """Mark multiple posts as processed."""
    cache = _load_cache()
    cache.update(shortcodes)
    _save_cache()


def _save_cache() -> None:
    """Persist cache to disk."""
    if _cache is None:
        return
    try:
        with open(_CACHE_FILE, "w") as f:
            json.dump(sorted(_cache), f)
    except Exception as exc:
        logger.warning("Failed to save post cache: %s", exc)


def cache_size() -> int:
    """Return number of cached shortcodes."""
    return len(_load_cache())
