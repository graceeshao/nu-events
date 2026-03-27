"""Tests for the scraper system.

Verifies the base scraper interface and the Northwestern scraper with
mocked HTTP responses.
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.scrapers.base import BaseScraper
from src.scrapers.northwestern_events import NorthwesternEventsScraper
from src.schemas.event import EventCreate


class TestBaseScraper:
    """Test the abstract BaseScraper interface."""

    def test_cannot_instantiate_directly(self) -> None:
        """BaseScraper cannot be instantiated without implementing abstract methods."""
        with pytest.raises(TypeError):
            BaseScraper()  # type: ignore[abstract]

    @pytest.mark.asyncio
    async def test_concrete_scraper_run(self) -> None:
        """A concrete scraper's run() calls fetch then parse."""

        class MockScraper(BaseScraper):
            name = "mock"

            async def fetch(self):
                return "raw data"

            async def parse(self, raw_data):
                return [
                    EventCreate(
                        title="Mock Event",
                        start_time=datetime(2025, 6, 1, 10, 0),
                    )
                ]

        scraper = MockScraper()
        events = await scraper.run()
        assert len(events) == 1
        assert events[0].title == "Mock Event"

    @pytest.mark.asyncio
    async def test_run_propagates_fetch_error(self) -> None:
        """run() propagates exceptions from fetch()."""

        class FailingScraper(BaseScraper):
            name = "failing"

            async def fetch(self):
                raise ConnectionError("Network down")

            async def parse(self, raw_data):
                return []

        scraper = FailingScraper()
        with pytest.raises(ConnectionError, match="Network down"):
            await scraper.run()


class TestNorthwesternEventsScraper:
    """Test the Northwestern events scraper with mocked responses."""

    @pytest.mark.asyncio
    async def test_fetch_returns_html(self) -> None:
        """fetch() returns HTML string from the events page."""
        scraper = NorthwesternEventsScraper()
        mock_html = "<html><body>Events</body></html>"

        with patch("src.scrapers.northwestern_events.httpx.AsyncClient") as MockClient:
            mock_response = AsyncMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = lambda: None

            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = await scraper.fetch()
            assert result == mock_html

    @pytest.mark.asyncio
    async def test_parse_empty_html(self) -> None:
        """parse() returns empty list for HTML with no event cards."""
        scraper = NorthwesternEventsScraper()
        events = await scraper.parse("<html><body><p>No events</p></body></html>")
        assert events == []

    @pytest.mark.asyncio
    async def test_parse_with_event_cards(self) -> None:
        """parse() extracts events from HTML with matching selectors."""
        scraper = NorthwesternEventsScraper()
        html = """
        <html><body>
            <div class="event-card">
                <h3 class="event-title">Spring Concert</h3>
                <time class="event-date" datetime="2025-05-20T19:00:00">May 20</time>
                <p class="event-description">Live music on the lakefill.</p>
                <span class="event-location">Norris Lawn</span>
                <a href="/events/spring-concert">Details</a>
            </div>
        </body></html>
        """
        events = await scraper.parse(html)
        assert len(events) == 1
        assert events[0].title == "Spring Concert"
        assert events[0].location == "Norris Lawn"
        assert events[0].source_name == "Northwestern Events"

    @pytest.mark.asyncio
    async def test_parse_skips_invalid_cards(self) -> None:
        """parse() skips cards missing required fields (title or date)."""
        scraper = NorthwesternEventsScraper()
        html = """
        <html><body>
            <div class="event-card">
                <span class="event-location">Somewhere</span>
            </div>
            <div class="event-card">
                <h3 class="event-title">Valid Event</h3>
                <time class="event-date" datetime="2025-06-01T10:00:00">Jun 1</time>
            </div>
        </body></html>
        """
        events = await scraper.parse(html)
        assert len(events) == 1
        assert events[0].title == "Valid Event"

    def test_parse_date_iso(self) -> None:
        """_parse_date handles ISO datetime strings."""
        result = NorthwesternEventsScraper._parse_date("2025-05-20T19:00:00")
        assert result == datetime(2025, 5, 20, 19, 0, 0)

    def test_parse_date_verbose(self) -> None:
        """_parse_date handles 'Month Day, Year' format."""
        result = NorthwesternEventsScraper._parse_date("May 20, 2025")
        assert result == datetime(2025, 5, 20)

    def test_parse_date_invalid(self) -> None:
        """_parse_date returns None for unrecognized formats."""
        result = NorthwesternEventsScraper._parse_date("not a date")
        assert result is None
