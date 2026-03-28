"""Tests for the LLM-based event parser.

Mocks Ollama API calls to test classification, extraction, fallback
behavior, and error handling without requiring a running Ollama instance.
"""

import json
from collections import namedtuple
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.services.llm_parser import (
    _build_event,
    _normalize_category,
    _parse_extraction_json,
    parse_event_with_llm,
)
from src.models.event import EventCategory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ModelInfo = namedtuple("ModelInfo", ["model"])


def _make_list_response(model_names: list[str]):
    """Create a mock ollama.list() response."""
    mock = MagicMock()
    mock.models = [ModelInfo(model=name) for name in model_names]
    return mock


def _make_chat_response(content: str) -> dict:
    """Create a mock ollama.chat() response dict."""
    return {"message": {"content": content}}


SAMPLE_EVENT_JSON = json.dumps({
    "title": "Movie Night",
    "date": "2026-04-03",
    "start_time": "19:00",
    "end_time": "21:00",
    "location": "Norris University Center",
    "description": "Join us for a fun movie night with free popcorn!",
    "rsvp_url": "https://lu.ma/movie-night",
    "has_free_food": True,
    "category": "social",
})

SAMPLE_MULTI_JSON = json.dumps([
    {
        "title": "Movie Night",
        "date": "2026-04-03",
        "start_time": "19:00",
        "end_time": None,
        "location": "Norris",
        "description": "Movie screening.",
        "rsvp_url": None,
        "has_free_food": True,
        "category": "social",
    },
    {
        "title": "Study Break",
        "date": "2026-04-04",
        "start_time": "15:00",
        "end_time": "16:00",
        "location": "Tech",
        "description": "Free snacks and games.",
        "rsvp_url": None,
        "has_free_food": True,
        "category": "social",
    },
])


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


class TestParseExtractionJson:
    """Tests for _parse_extraction_json."""

    def test_single_object(self):
        result = _parse_extraction_json('{"title": "Test"}')
        assert result == [{"title": "Test"}]

    def test_array(self):
        result = _parse_extraction_json('[{"title": "A"}, {"title": "B"}]')
        assert len(result) == 2

    def test_strips_markdown_fences(self):
        raw = '```json\n{"title": "Test"}\n```'
        result = _parse_extraction_json(raw)
        assert result == [{"title": "Test"}]

    def test_invalid_json_raises(self):
        with pytest.raises((json.JSONDecodeError, ValueError)):
            _parse_extraction_json("not json at all")


class TestNormalizeCategory:
    """Tests for _normalize_category."""

    def test_valid_categories(self):
        assert _normalize_category("academic") == EventCategory.ACADEMIC
        assert _normalize_category("Social") == EventCategory.SOCIAL
        assert _normalize_category("CAREER") == EventCategory.CAREER

    def test_invalid_returns_other(self):
        assert _normalize_category("unknown") == EventCategory.OTHER
        assert _normalize_category(None) == EventCategory.OTHER
        assert _normalize_category("") == EventCategory.OTHER


class TestBuildEvent:
    """Tests for _build_event."""

    def test_basic_build(self):
        data = {
            "title": "Test Event",
            "date": "2026-04-03",
            "start_time": "14:00",
            "end_time": "15:30",
            "location": "Tech",
            "description": "A test event.",
            "rsvp_url": "https://example.com/rsvp",
            "has_free_food": False,
            "category": "academic",
        }
        event = _build_event(data, "TestOrg", None, False, "Subject", "Body")
        assert event.title == "Test Event"
        assert event.start_time == datetime(2026, 4, 3, 14, 0)
        assert event.end_time == datetime(2026, 4, 3, 15, 30)
        assert event.location == "Tech"
        assert event.category == EventCategory.ACADEMIC
        assert event.has_free_food is False

    def test_fallback_rsvp(self):
        data = {
            "title": "Event",
            "date": "2026-04-03",
            "start_time": "14:00",
            "end_time": None,
            "location": None,
            "description": None,
            "rsvp_url": None,
            "has_free_food": None,
            "category": None,
        }
        event = _build_event(
            data, None, "https://fallback.com/rsvp", True, "Subj", "Body",
        )
        assert event.rsvp_url == "https://fallback.com/rsvp"
        assert event.has_free_food is True

    def test_null_string_handling(self):
        data = {
            "title": "Event",
            "date": "2026-04-03",
            "start_time": "10:00",
            "end_time": "null",
            "location": "null",
            "description": "null",
            "rsvp_url": "null",
            "has_free_food": False,
            "category": "other",
        }
        event = _build_event(data, None, None, False, "Subj", "Body")
        assert event.end_time is None
        assert event.location is None
        assert event.description is None
        assert event.rsvp_url is None


# ---------------------------------------------------------------------------
# Integration tests for parse_event_with_llm (mocked Ollama)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestParseEventWithLlm:
    """Tests for the main parse_event_with_llm function."""

    @patch("src.services.llm_parser.settings")
    @patch("src.services.llm_parser._get_ollama_client")
    async def test_event_classified_and_extracted(self, mock_get_client, mock_settings):
        """An EVENT email should be classified then extracted."""
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.ollama_model = "gemma3:4b"

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.list.return_value = _make_list_response(["gemma3:4b"])

        # First call: classification, second call: extraction
        mock_client.chat.side_effect = [
            _make_chat_response("EVENT"),
            _make_chat_response(SAMPLE_EVENT_JSON),
        ]

        events = await parse_event_with_llm(
            subject="Movie Night Friday!",
            body="Join us Friday at 7pm at Norris for movie night! Free popcorn!",
            sender="fun@northwestern.edu",
        )

        assert len(events) == 1
        assert events[0].title == "Movie Night"
        assert events[0].has_free_food is True
        assert events[0].category == EventCategory.SOCIAL

    @patch("src.services.llm_parser.settings")
    @patch("src.services.llm_parser._get_ollama_client")
    async def test_not_event_returns_empty(self, mock_get_client, mock_settings):
        """A NOT_EVENT email should return an empty list."""
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.ollama_model = "gemma3:4b"

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.list.return_value = _make_list_response(["gemma3:4b"])
        mock_client.chat.return_value = _make_chat_response("NOT_EVENT")

        events = await parse_event_with_llm(
            subject="Spring Quarter Registration",
            body="Reminder: Spring quarter course registration opens Monday.",
        )

        assert events == []
        # Should only call chat once (classification)
        assert mock_client.chat.call_count == 1

    @patch("src.services.llm_parser.settings")
    @patch("src.services.llm_parser._get_ollama_client")
    async def test_ollama_down_falls_back_to_regex(self, mock_get_client, mock_settings):
        """When Ollama is unreachable, should fall back to regex parser."""
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.ollama_model = "gemma3:4b"

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.list.side_effect = Exception("Connection refused")

        events = await parse_event_with_llm(
            subject="Talk by Dr. Jones on April 3 at 12:30pm",
            body="The Buffett Institute invites you to a talk by Dr. Jones on April 3 at 12:30pm in Kresge.",
        )

        # Regex parser should handle this (it has date, time, location)
        # It may or may not produce events depending on confidence, but it shouldn't crash
        assert isinstance(events, list)

    @patch("src.services.llm_parser.settings")
    @patch("src.services.llm_parser._get_ollama_client")
    async def test_malformed_json_falls_back(self, mock_get_client, mock_settings):
        """Malformed JSON from LLM should fall back to regex parser."""
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.ollama_model = "gemma3:4b"

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.list.return_value = _make_list_response(["gemma3:4b"])

        mock_client.chat.side_effect = [
            _make_chat_response("EVENT"),
            _make_chat_response("Sure! Here's the event info: {broken json"),
        ]

        events = await parse_event_with_llm(
            subject="Workshop March 28 at 3pm",
            body="Workshop on resume writing, March 28 at 3pm, Career Services. RSVP required.",
        )

        # Should fall back to regex and still return a valid list
        assert isinstance(events, list)

    @patch("src.services.llm_parser.settings")
    @patch("src.services.llm_parser._get_ollama_client")
    async def test_multiple_events_in_one_email(self, mock_get_client, mock_settings):
        """Multiple events in one email should all be extracted."""
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.ollama_model = "gemma3:4b"

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.list.return_value = _make_list_response(["gemma3:4b"])

        mock_client.chat.side_effect = [
            _make_chat_response("EVENT"),
            _make_chat_response(SAMPLE_MULTI_JSON),
        ]

        events = await parse_event_with_llm(
            subject="This Week's Events",
            body="Movie Night Fri 7pm Norris. Study Break Sat 3pm Tech.",
        )

        assert len(events) == 2
        assert events[0].title == "Movie Night"
        assert events[1].title == "Study Break"

    @patch("src.services.llm_parser.settings")
    @patch("src.services.llm_parser._get_ollama_client")
    async def test_model_fallback(self, mock_get_client, mock_settings):
        """When primary model isn't available, should fall back to gemma3:1b."""
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.ollama_model = "gemma3:4b"

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        # Only gemma3:1b is available
        mock_client.list.return_value = _make_list_response(["gemma3:1b"])

        mock_client.chat.side_effect = [
            _make_chat_response("EVENT"),
            _make_chat_response(SAMPLE_EVENT_JSON),
        ]

        events = await parse_event_with_llm(
            subject="Movie Night",
            body="Join us Friday at 7pm at Norris!",
        )

        assert len(events) == 1
        # Verify it used gemma3:1b in the chat calls
        call_args = mock_client.chat.call_args_list
        assert call_args[0][1]["model"] == "gemma3:1b"

    @patch("src.services.llm_parser.settings")
    @patch("src.services.llm_parser._get_ollama_client")
    async def test_classification_error_falls_back(self, mock_get_client, mock_settings):
        """If classification call raises, should fall back to regex."""
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.ollama_model = "gemma3:4b"

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.list.return_value = _make_list_response(["gemma3:4b"])
        mock_client.chat.side_effect = Exception("Model error")

        events = await parse_event_with_llm(
            subject="Talk April 3 at 12:30pm in Kresge",
            body="The Buffett Institute invites you to a talk on April 3 at 12:30pm in Kresge.",
        )

        assert isinstance(events, list)

    @patch("src.services.llm_parser.settings")
    @patch("src.services.llm_parser._get_ollama_client")
    async def test_extraction_with_markdown_fences(self, mock_get_client, mock_settings):
        """LLM response wrapped in markdown code fences should still parse."""
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.ollama_model = "gemma3:4b"

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.list.return_value = _make_list_response(["gemma3:4b"])

        fenced = f"```json\n{SAMPLE_EVENT_JSON}\n```"
        mock_client.chat.side_effect = [
            _make_chat_response("EVENT"),
            _make_chat_response(fenced),
        ]

        events = await parse_event_with_llm(
            subject="Movie Night",
            body="Movie night at Norris, 7pm Friday.",
        )

        assert len(events) == 1
        assert events[0].title == "Movie Night"

    @patch("src.services.llm_parser.settings")
    @patch("src.services.llm_parser._get_ollama_client")
    async def test_org_matching_passthrough(self, mock_get_client, mock_settings):
        """Organization matching via list_id/list_sender should work."""
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.ollama_model = "gemma3:4b"

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.list.return_value = _make_list_response(["gemma3:4b"])

        mock_client.chat.side_effect = [
            _make_chat_response("EVENT"),
            _make_chat_response(SAMPLE_EVENT_JSON),
        ]

        events = await parse_event_with_llm(
            subject="Movie Night",
            body="Movie night at Norris, 7pm Friday.",
            list_id="ANIME.LISTSERV.IT.NORTHWESTERN.EDU",
        )

        assert len(events) == 1
        assert events[0].source_name == "LISTSERV:ANIME"
