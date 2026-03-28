"""Tests for the email parser and ingest endpoints."""

from datetime import date, time, datetime

import pytest

from src.services.email_parser import (
    extract_dates,
    extract_location,
    extract_times,
    match_organization,
    parse_event_email,
)


# ---------------------------------------------------------------------------
# Date extraction
# ---------------------------------------------------------------------------

class TestExtractDates:
    """Tests for extract_dates()."""

    def test_long_form_with_year(self):
        """'March 27, 2026' parses correctly."""
        dates = extract_dates("Join us on March 27, 2026 for fun!", date(2026, 1, 1))
        assert date(2026, 3, 27) in dates

    def test_abbreviated_month(self):
        """'Mar 27, 2026' parses correctly."""
        dates = extract_dates("Event on Mar 27, 2026", date(2026, 1, 1))
        assert date(2026, 3, 27) in dates

    def test_ordinal_suffix(self):
        """'March 27th' parses correctly."""
        dates = extract_dates("Happening March 27th!", date(2026, 1, 1))
        assert date(2026, 3, 27) in dates

    def test_numeric_date(self):
        """'3/27/2026' parses correctly."""
        dates = extract_dates("Event on 3/27/2026", date(2026, 1, 1))
        assert date(2026, 3, 27) in dates

    def test_numeric_date_short_year(self):
        """'03/27/26' parses correctly."""
        dates = extract_dates("Event on 03/27/26", date(2026, 1, 1))
        assert date(2026, 3, 27) in dates

    def test_weekday_prefix(self):
        """'Friday, March 28' parses correctly."""
        dates = extract_dates("Come on Friday, March 28, 2026!", date(2026, 1, 1))
        assert date(2026, 3, 28) in dates

    def test_this_friday(self):
        """'this Friday' resolves to the upcoming Friday."""
        ref = date(2026, 3, 23)  # Monday
        dates = extract_dates("See you this Friday!", ref)
        assert len(dates) >= 1
        assert dates[0] == date(2026, 3, 27)  # Friday

    def test_next_tuesday(self):
        """'next Tuesday' resolves to Tuesday of the following week."""
        ref = date(2026, 3, 23)  # Monday
        dates = extract_dates("next Tuesday meeting", ref)
        assert len(dates) >= 1
        assert dates[0] == date(2026, 3, 31)  # Tuesday next week

    def test_no_year_infers_current(self):
        """Date without year uses reference year (or next year if past)."""
        dates = extract_dates("Party on December 25", date(2026, 1, 1))
        assert date(2026, 12, 25) in dates

    def test_multiple_dates(self):
        """Multiple dates in one text are all found."""
        text = "Monday 3/31 at 4pm\nWednesday 4/2 at 7pm\nFriday 4/4 at 8pm"
        dates = extract_dates(text, date(2026, 1, 1))
        assert date(2026, 3, 31) in dates
        assert date(2026, 4, 2) in dates
        assert date(2026, 4, 4) in dates


# ---------------------------------------------------------------------------
# Time extraction
# ---------------------------------------------------------------------------

class TestExtractTimes:
    """Tests for extract_times()."""

    def test_simple_time(self):
        """'7:00 PM' parses to 19:00."""
        times = extract_times("Event at 7:00 PM")
        assert len(times) >= 1
        assert times[0][0] == time(19, 0)

    def test_compact_time(self):
        """'7pm' parses to 19:00."""
        times = extract_times("at 7pm")
        assert len(times) >= 1
        assert times[0][0] == time(19, 0)

    def test_time_range_dash(self):
        """'7-9pm' parses to (19:00, 21:00)."""
        times = extract_times("7-9pm")
        assert len(times) >= 1
        assert times[0] == (time(19, 0), time(21, 0))

    def test_time_range_full(self):
        """'7:00 PM - 9:00 PM' parses correctly."""
        times = extract_times("7:00 PM - 9:00 PM")
        assert len(times) >= 1
        assert times[0] == (time(19, 0), time(21, 0))

    def test_time_range_from_to(self):
        """'from 7pm to 9pm' parses correctly."""
        times = extract_times("from 7pm to 9pm")
        assert len(times) >= 1
        assert times[0] == (time(19, 0), time(21, 0))

    def test_time_with_colon_no_space(self):
        """'7:00pm' parses to 19:00."""
        times = extract_times("at 7:00pm")
        assert len(times) >= 1
        assert times[0][0] == time(19, 0)

    def test_am_time(self):
        """'10:30 AM' parses to 10:30."""
        times = extract_times("Starts 10:30 AM")
        assert len(times) >= 1
        assert times[0][0] == time(10, 30)

    def test_range_with_mixed_ampm(self):
        """'3:30 PM - 4:30 PM' parses correctly."""
        times = extract_times("Time: 3:30 PM - 4:30 PM")
        assert len(times) >= 1
        assert times[0] == (time(15, 30), time(16, 30))


# ---------------------------------------------------------------------------
# Location extraction
# ---------------------------------------------------------------------------

class TestExtractLocation:
    """Tests for extract_location()."""

    def test_labeled_location(self):
        """'Location: Tech L160' is found."""
        loc = extract_location("Location: Tech L160")
        assert loc is not None
        assert "Tech" in loc

    def test_where_label(self):
        """'Where: Norris University Center, Room 201' is found."""
        loc = extract_location("Where: Norris University Center, Room 201")
        assert loc is not None
        assert "Norris" in loc

    def test_known_building(self):
        """NU building name in text is detected."""
        loc = extract_location("Come to Cahn Auditorium for the show!")
        assert loc is not None
        assert "Cahn Auditorium" in loc

    def test_building_with_room(self):
        """Building + room number is captured."""
        loc = extract_location("Location: Tech L160")
        assert loc is not None
        assert "Tech" in loc

    def test_no_location(self):
        """Returns None when no location found."""
        loc = extract_location("No place mentioned here.")
        assert loc is None

    def test_norris_full_name(self):
        """'Norris University Center' is preferred over just 'Norris'."""
        loc = extract_location("at Norris University Center")
        assert loc == "Norris University Center"


# ---------------------------------------------------------------------------
# Organization matching
# ---------------------------------------------------------------------------

class TestMatchOrganization:
    """Tests for match_organization()."""

    def test_from_sender_email(self):
        """Extracts org name from sender local part."""
        org = match_organization("filmclub@u.northwestern.edu", "")
        assert org is not None
        assert "film" in org.lower()

    def test_no_sender(self):
        """Returns None when no sender."""
        org = match_organization(None, "some body text")
        assert org is None


# ---------------------------------------------------------------------------
# Full email parsing
# ---------------------------------------------------------------------------

class TestParseEventEmail:
    """Tests for parse_event_email()."""

    def test_single_event_email(self):
        """Movie night email produces one event."""
        subject = "Movie Night this Friday!"
        body = (
            "Hey Wildcats! Join Northwestern Film Club for our weekly movie night.\n\n"
            "When: Friday, March 28, 2026 at 7:00 PM\n"
            "Where: Norris University Center, Room 201\n"
            "What: We'll be screening \"Everything Everywhere All At Once\"\n\n"
            "Free popcorn! All are welcome.\n"
            "RSVP: filmclub@u.northwestern.edu"
        )
        events = parse_event_email(
            subject, body,
            sender="filmclub@u.northwestern.edu",
            reference_date=date(2026, 3, 25),
        )
        assert len(events) == 1
        ev = events[0]
        assert ev.title == subject
        assert ev.start_time == datetime(2026, 3, 28, 19, 0)
        assert ev.location is not None
        assert "Norris" in ev.location

    def test_seminar_with_time_range(self):
        """CS seminar email parses date and time range."""
        subject = "CS Department Seminar Series"
        body = (
            "The CS department invites you to a talk by Prof. Smith on\n"
            "\"Machine Learning for Climate Science\"\n\n"
            "Date: Tuesday, April 1, 2026\n"
            "Time: 3:30 PM - 4:30 PM\n"
            "Location: Tech L160\n\n"
            "Abstract: In this talk we will explore..."
        )
        events = parse_event_email(
            subject, body,
            reference_date=date(2026, 3, 25),
        )
        assert len(events) == 1
        ev = events[0]
        assert ev.start_time == datetime(2026, 4, 1, 15, 30)
        assert ev.end_time == datetime(2026, 4, 1, 16, 30)
        assert ev.location is not None
        assert "Tech" in ev.location

    def test_multi_event_email(self):
        """Email with multiple events produces multiple EventCreate."""
        subject = "Multiple events next week"
        body = (
            "Mark your calendars!\n\n"
            "Monday 3/31 at 4pm - Study Break in Norris (free snacks)\n"
            "Wednesday 4/2 at 7pm - Guest Speaker at Tech Auditorium\n"
            "Friday 4/4 at 8pm - Dance Show at Cahn Auditorium\n"
        )
        events = parse_event_email(
            subject, body,
            reference_date=date(2026, 3, 25),
        )
        assert len(events) == 3

        # Check dates are correct
        starts = sorted(ev.start_time for ev in events)
        assert starts[0].date() == date(2026, 3, 31)
        assert starts[1].date() == date(2026, 4, 2)
        assert starts[2].date() == date(2026, 4, 4)

    def test_no_events_found(self):
        """Email with no date info returns empty list."""
        events = parse_event_email(
            "Hello", "This is just a regular email with no events."
        )
        assert events == []


# ---------------------------------------------------------------------------
# Ingest API endpoints
# ---------------------------------------------------------------------------

class TestIngestAPI:
    """Tests for the /ingest/* endpoints."""

    @pytest.mark.asyncio
    async def test_ingest_email_endpoint(self, client):
        """POST /ingest/email processes a structured email."""
        payload = {
            "subject": "Movie Night!",
            "body": "Come on Friday, March 28, 2026 at 7pm to Norris for movies!",
            "sender": "filmclub@u.northwestern.edu",
        }
        resp = await client.post("/ingest/email", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "processed"
        assert data["events_created"] >= 1
        assert len(data["events"]) >= 1

    @pytest.mark.asyncio
    async def test_ingest_email_no_events(self, client):
        """POST /ingest/email with no date returns no_events_found."""
        payload = {
            "subject": "Hello",
            "body": "Just checking in, no events here.",
        }
        resp = await client.post("/ingest/email", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "no_events_found"
        assert data["events_created"] == 0

    @pytest.mark.asyncio
    async def test_ingest_raw_endpoint(self, client):
        """POST /ingest/raw processes a raw email with headers."""
        raw = (
            "Subject: CS Seminar\n"
            "From: cs-dept@northwestern.edu\n"
            "\n"
            "Talk on April 1, 2026 at 3:30 PM in Tech L160.\n"
        )
        resp = await client.post(
            "/ingest/raw",
            content=raw,
            headers={"Content-Type": "text/plain"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "processed"
        assert data["events_created"] >= 1
