"""Tests for dedup key generation.

Verifies determinism, normalization, and edge-case handling of
the generate_dedup_key function.
"""

from datetime import datetime

from src.services.dedup import generate_dedup_key


class TestGenerateDedupKey:
    """Test suite for generate_dedup_key."""

    def test_deterministic(self) -> None:
        """Same inputs always produce the same key."""
        dt = datetime(2025, 3, 15, 14, 0)
        key1 = generate_dedup_key("Concert", dt, "Pick-Staiger Hall")
        key2 = generate_dedup_key("Concert", dt, "Pick-Staiger Hall")
        assert key1 == key2

    def test_different_title_different_key(self) -> None:
        """Different titles produce different keys."""
        dt = datetime(2025, 3, 15, 14, 0)
        key1 = generate_dedup_key("Concert A", dt, "Pick-Staiger Hall")
        key2 = generate_dedup_key("Concert B", dt, "Pick-Staiger Hall")
        assert key1 != key2

    def test_different_time_different_key(self) -> None:
        """Different start times produce different keys."""
        key1 = generate_dedup_key("Concert", datetime(2025, 3, 15, 14, 0), "Hall")
        key2 = generate_dedup_key("Concert", datetime(2025, 3, 16, 14, 0), "Hall")
        assert key1 != key2

    def test_different_location_different_key(self) -> None:
        """Different locations produce different keys."""
        dt = datetime(2025, 3, 15, 14, 0)
        key1 = generate_dedup_key("Concert", dt, "Hall A")
        key2 = generate_dedup_key("Concert", dt, "Hall B")
        assert key1 != key2

    def test_case_insensitive(self) -> None:
        """Keys are case-insensitive (normalized to lowercase)."""
        dt = datetime(2025, 3, 15, 14, 0)
        key1 = generate_dedup_key("CONCERT", dt, "HALL")
        key2 = generate_dedup_key("concert", dt, "hall")
        assert key1 == key2

    def test_whitespace_normalized(self) -> None:
        """Extra whitespace is collapsed."""
        dt = datetime(2025, 3, 15, 14, 0)
        key1 = generate_dedup_key("  Big   Concert  ", dt, "  The   Hall  ")
        key2 = generate_dedup_key("Big Concert", dt, "The Hall")
        assert key1 == key2

    def test_none_location(self) -> None:
        """None location is handled gracefully."""
        dt = datetime(2025, 3, 15, 14, 0)
        key1 = generate_dedup_key("Concert", dt, None)
        key2 = generate_dedup_key("Concert", dt, None)
        assert key1 == key2

    def test_none_vs_empty_location_same(self) -> None:
        """None location and empty string produce the same key."""
        dt = datetime(2025, 3, 15, 14, 0)
        key1 = generate_dedup_key("Concert", dt, None)
        key2 = generate_dedup_key("Concert", dt, "")
        assert key1 == key2

    def test_key_length(self) -> None:
        """Dedup key is always 32 hex characters."""
        dt = datetime(2025, 3, 15, 14, 0)
        key = generate_dedup_key("Concert", dt, "Hall")
        assert len(key) == 32
        assert all(c in "0123456789abcdef" for c in key)
