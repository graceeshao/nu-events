"""Tests for the scraper system.

Verifies the base scraper interface and the PlanIt Purple scraper with
mocked HTML.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.event import EventCategory
from src.scrapers.base import BaseScraper
from src.scrapers.planitpurple import PlanItPurpleScraper
from src.schemas.event import EventCreate


# ---------------------------------------------------------------------------
# Sample HTML for PlanIt Purple tests
# ---------------------------------------------------------------------------

SAMPLE_ARTICLE_ALL_DAY = """
<article class="event jos" data-jos_animation="fade-up">
    <div class="event-date">
        <div class="month">Mar</div>
        <div class="day">27</div>
        <div class="year">2026</div>
    </div>
    <div class="event-content">
        <div class="recurring"><a href="/event/series/200910">Recurring Event</a></div>
        <h3><a href="/event/636538">2026-2027 Exhibition Submissions: Dittmar Gallery</a></h3>
        <div class="time-location">
            <strong>All Day</strong>
            Norris University Center, Dittmar Gallery, 1999 Campus Drive, Evanston, IL 60208
        </div>
        <div class="tags">
            <a href="/#search=//2//" rel="nofollow" class="category-button">Arts/Humanities</a>
        </div>
    </div>
</article>
"""

SAMPLE_ARTICLE_WITH_TIME = """
<article class="event jos" data-jos_animation="fade-up">
    <div class="event-date">
        <div class="month">Apr</div>
        <div class="day">15</div>
        <div class="year">2026</div>
    </div>
    <div class="event-content">
        <h3><a href="/event/700001">Career Fair 2026</a></h3>
        <div class="time-location">
            <strong>9:00 AM - 10:00 AM</strong>
            Norris Center, Main Hall
        </div>
        <div class="tags">
            <a href="/#search=//5//" rel="nofollow" class="category-button">Career</a>
        </div>
    </div>
</article>
"""

SAMPLE_ARTICLE_NOON = """
<article class="event jos" data-jos_animation="fade-up">
    <div class="event-date">
        <div class="month">May</div>
        <div class="day">1</div>
        <div class="year">2026</div>
    </div>
    <div class="event-content">
        <h3><a href="/event/700002">Lunch Seminar</a></h3>
        <div class="time-location">
            <strong>12:00 PM - 1:00 PM</strong>
            Kresge Hall, Room 101
        </div>
        <div class="tags">
            <a href="/#search=//1//" rel="nofollow" class="category-button">Academic (general)</a>
        </div>
    </div>
</article>
"""

SAMPLE_PAGE_HTML = f"""
<html><body>
{SAMPLE_ARTICLE_ALL_DAY}
{SAMPLE_ARTICLE_WITH_TIME}
{SAMPLE_ARTICLE_NOON}
</body></html>
"""


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


# ---------------------------------------------------------------------------
# PlanIt Purple Scraper Tests
# ---------------------------------------------------------------------------


class TestPlanItPurpleScraper:
    """Test the PlanIt Purple scraper with mocked responses."""

    @pytest.mark.asyncio
    async def test_parse_all_day_event(self) -> None:
        """parse() correctly handles an all-day event."""
        scraper = PlanItPurpleScraper()
        events = await scraper.parse([SAMPLE_ARTICLE_ALL_DAY])
        assert len(events) == 1
        e = events[0]
        assert e.title == "2026-2027 Exhibition Submissions: Dittmar Gallery"
        assert e.start_time == datetime(2026, 3, 27, 0, 0)
        assert e.end_time is None
        assert e.source_url == "https://planitpurple.northwestern.edu/event/636538"
        assert e.category == EventCategory.ARTS
        assert e.source_name == "PlanIt Purple"
        assert "Norris University Center" in (e.location or "")

    @pytest.mark.asyncio
    async def test_parse_timed_event(self) -> None:
        """parse() correctly parses an event with start and end times."""
        scraper = PlanItPurpleScraper()
        events = await scraper.parse([SAMPLE_ARTICLE_WITH_TIME])
        assert len(events) == 1
        e = events[0]
        assert e.title == "Career Fair 2026"
        assert e.start_time == datetime(2026, 4, 15, 9, 0)
        assert e.end_time == datetime(2026, 4, 15, 10, 0)
        assert e.category == EventCategory.CAREER

    @pytest.mark.asyncio
    async def test_parse_noon_event(self) -> None:
        """parse() correctly handles 12:00 PM times."""
        scraper = PlanItPurpleScraper()
        events = await scraper.parse([SAMPLE_ARTICLE_NOON])
        assert len(events) == 1
        e = events[0]
        assert e.title == "Lunch Seminar"
        assert e.start_time == datetime(2026, 5, 1, 12, 0)
        assert e.end_time == datetime(2026, 5, 1, 13, 0)
        assert e.category == EventCategory.ACADEMIC

    @pytest.mark.asyncio
    async def test_parse_multiple_events(self) -> None:
        """parse() extracts all events from a full page."""
        scraper = PlanItPurpleScraper()
        events = await scraper.parse([SAMPLE_PAGE_HTML])
        assert len(events) == 3

    @pytest.mark.asyncio
    async def test_parse_empty_html(self) -> None:
        """parse() returns empty list for HTML with no event articles."""
        scraper = PlanItPurpleScraper()
        events = await scraper.parse(["<html><body><p>No events</p></body></html>"])
        assert events == []

    @pytest.mark.asyncio
    async def test_parse_skips_missing_title(self) -> None:
        """parse() skips articles without a title link."""
        html = """
        <article class="event">
            <div class="event-date">
                <div class="month">Jan</div>
                <div class="day">1</div>
                <div class="year">2026</div>
            </div>
            <div class="event-content">
                <div class="time-location"><strong>All Day</strong></div>
            </div>
        </article>
        """
        scraper = PlanItPurpleScraper()
        events = await scraper.parse([html])
        assert events == []

    def test_parse_time_all_day(self) -> None:
        """_parse_time handles 'All Day'."""
        date = datetime(2026, 3, 27)
        start, end = PlanItPurpleScraper._parse_time("All Day", date)
        assert start == date
        assert end is None

    def test_parse_time_range(self) -> None:
        """_parse_time handles '9:00 AM - 10:00 AM'."""
        date = datetime(2026, 4, 15)
        start, end = PlanItPurpleScraper._parse_time("9:00 AM - 10:00 AM", date)
        assert start == datetime(2026, 4, 15, 9, 0)
        assert end == datetime(2026, 4, 15, 10, 0)

    def test_parse_time_noon_range(self) -> None:
        """_parse_time handles '12:00 PM - 1:00 PM'."""
        date = datetime(2026, 5, 1)
        start, end = PlanItPurpleScraper._parse_time("12:00 PM - 1:00 PM", date)
        assert start == datetime(2026, 5, 1, 12, 0)
        assert end == datetime(2026, 5, 1, 13, 0)

    def test_parse_time_unrecognized(self) -> None:
        """_parse_time falls back to midnight for unrecognized formats."""
        date = datetime(2026, 1, 1)
        start, end = PlanItPurpleScraper._parse_time("TBD", date)
        assert start == date
        assert end is None

    @pytest.mark.asyncio
    async def test_category_mapping(self) -> None:
        """Categories are correctly mapped to EventCategory enum."""
        html = """
        <article class="event">
            <div class="event-date">
                <div class="month">Jun</div>
                <div class="day">10</div>
                <div class="year">2026</div>
            </div>
            <div class="event-content">
                <h3><a href="/event/1">Social Event</a></h3>
                <div class="time-location"><strong>All Day</strong></div>
                <div class="tags">
                    <a class="category-button">Social</a>
                </div>
            </div>
        </article>
        """
        scraper = PlanItPurpleScraper()
        events = await scraper.parse([html])
        assert len(events) == 1
        assert events[0].category == EventCategory.SOCIAL
