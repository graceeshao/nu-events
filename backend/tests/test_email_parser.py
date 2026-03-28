"""Tests for the email parser and ingest endpoints."""

from datetime import date, time, datetime

import pytest

from src.services.email_parser import (
    _extract_listserv_name,
    detect_free_food,
    extract_dates,
    extract_location,
    extract_rsvp_url,
    extract_short_description,
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

    def test_from_list_id_header(self):
        """Extracts org from List-Id header (LISTSERV format)."""
        org = match_organization(
            "random@gmail.com", "",
            list_id="ANIME.LISTSERV.IT.NORTHWESTERN.EDU",
        )
        assert org == "LISTSERV:ANIME"

    def test_from_list_id_with_brackets(self):
        """Extracts org from List-Id with angle brackets."""
        org = match_organization(
            None, "",
            list_id="<ACTUARIALCLUB.LISTSERV.IT.NORTHWESTERN.EDU>",
        )
        assert org == "LISTSERV:ACTUARIALCLUB"

    def test_from_sender_header_owner(self):
        """Extracts org from Sender header with owner- prefix."""
        org = match_organization(
            "someone@gmail.com", "",
            list_sender="owner-CS-PM-ANNOUNCE@LISTSERV.IT.NORTHWESTERN.EDU",
        )
        assert org == "LISTSERV:CS-PM-ANNOUNCE"

    def test_listserv_takes_priority(self):
        """List-Id takes priority over From address."""
        org = match_organization(
            "random-person@gmail.com", "",
            list_id="FILMCLUB.LISTSERV.IT.NORTHWESTERN.EDU",
        )
        assert org == "LISTSERV:FILMCLUB"
        assert "random" not in org.lower()


class TestExtractListservName:
    """Tests for _extract_listserv_name()."""

    def test_list_id_standard(self):
        assert _extract_listserv_name("ANIME.LISTSERV.IT.NORTHWESTERN.EDU", "") == "ANIME"

    def test_list_id_with_brackets(self):
        assert _extract_listserv_name("<AI_SAFETY.LISTSERV.IT.NORTHWESTERN.EDU>", "") == "AI_SAFETY"

    def test_sender_owner_prefix(self):
        assert _extract_listserv_name("", "owner-ARCHERY@LISTSERV.IT.NORTHWESTERN.EDU") == "ARCHERY"

    def test_sender_with_name(self):
        assert _extract_listserv_name("", "Archery Club <owner-ARCHERY@LISTSERV.IT.NORTHWESTERN.EDU>") == "ARCHERY"

    def test_no_listserv_headers(self):
        assert _extract_listserv_name("", "") is None

    def test_non_listserv_list_id(self):
        assert _extract_listserv_name("some.random.list", "") is None


# ---------------------------------------------------------------------------
# RSVP URL extraction
# ---------------------------------------------------------------------------

class TestExtractRsvpUrl:
    """Tests for extract_rsvp_url()."""

    def test_finds_eventbrite_url(self):
        """Finds Eventbrite URLs."""
        text = "Register here: https://www.eventbrite.com/e/some-event-123"
        url = extract_rsvp_url(text)
        assert url is not None
        assert "eventbrite.com" in url

    def test_finds_google_forms_url(self):
        """Finds Google Forms URLs."""
        text = "RSVP at https://docs.google.com/forms/d/e/abc123/viewform"
        url = extract_rsvp_url(text)
        assert url is not None
        assert "docs.google.com/forms" in url

    def test_finds_forms_gle_url(self):
        """Finds forms.gle short URLs."""
        text = "Sign up: https://forms.gle/abc123"
        url = extract_rsvp_url(text)
        assert url is not None
        assert "forms.gle" in url

    def test_finds_bitly_url_near_rsvp(self):
        """Finds bit.ly URLs."""
        text = "RSVP here: https://bit.ly/event-signup"
        url = extract_rsvp_url(text)
        assert url is not None
        assert "bit.ly" in url

    def test_prefers_rsvp_keyword_url(self):
        """Prefers URLs near RSVP keywords over random URLs."""
        text = (
            "Check our website: https://example.com/home\n"
            "RSVP at https://forms.gle/abc123\n"
        )
        url = extract_rsvp_url(text)
        assert url is not None
        assert "forms.gle" in url

    def test_returns_none_no_urls(self):
        """Returns None when no URLs present."""
        assert extract_rsvp_url("No links here, just text.") is None

    def test_returns_none_no_rsvp_urls(self):
        """Returns None when URLs exist but none are RSVP-related."""
        text = "Check out https://example.com for more info."
        assert extract_rsvp_url(text) is None

    def test_finds_luma_url(self):
        """Finds lu.ma URLs."""
        text = "Register: https://lu.ma/some-event"
        url = extract_rsvp_url(text)
        assert url is not None
        assert "lu.ma" in url


# ---------------------------------------------------------------------------
# Free food detection
# ---------------------------------------------------------------------------

class TestDetectFreeFood:
    """Tests for detect_free_food()."""

    def test_free_pizza(self):
        assert detect_free_food("Join us for free pizza!")

    def test_free_food(self):
        assert detect_free_food("FREE FOOD at the event")

    def test_food_provided(self):
        assert detect_free_food("Food will be provided.")

    def test_lunch_provided(self):
        assert detect_free_food("Lunch provided for attendees.")

    def test_refreshments_served(self):
        assert detect_free_food("Refreshments will be served.")

    def test_complimentary_lunch(self):
        assert detect_free_food("Complimentary lunch included.")

    def test_free_snacks(self):
        assert detect_free_food("Free snacks and drinks!")

    def test_food_and_drinks(self):
        assert detect_free_food("Come for food and drinks.")

    def test_pizza_provided(self):
        assert detect_free_food("Pizza provided!")

    def test_free_cookies(self):
        assert detect_free_food("Free cookies for everyone.")

    def test_rejects_free_to_attend(self):
        """'free to attend' should not trigger."""
        assert not detect_free_food("This event is free to attend.")

    def test_rejects_gluten_free(self):
        """'gluten-free' should not trigger."""
        assert not detect_free_food("We offer gluten-free options.")

    def test_rejects_free_parking(self):
        """'free parking' should not trigger."""
        assert not detect_free_food("Free parking is available.")

    def test_no_food_mentions(self):
        assert not detect_free_food("Join us for a great time!")


# ---------------------------------------------------------------------------
# Short description extraction
# ---------------------------------------------------------------------------

class TestExtractShortDescription:
    """Tests for extract_short_description()."""

    def test_what_line(self):
        """Extracts from 'What:' lines."""
        body = "When: Friday\nWhat: A screening of Inception\nWhere: Norris"
        desc = extract_short_description("Movie Night", body)
        assert desc is not None
        assert "Inception" in desc

    def test_skips_greetings(self):
        """Skips greeting lines."""
        body = "Hey Wildcats!\nJoin us for an amazing concert.\nIt will be great."
        desc = extract_short_description("Concert", body)
        assert desc is not None
        assert "Hey" not in desc
        assert "concert" in desc.lower()

    def test_stops_at_signature(self):
        """Stops at email signatures."""
        body = "Great event happening.\n--\nJohn Smith\nPresident"
        desc = extract_short_description("Event", body)
        assert desc is not None
        assert "John" not in desc
        assert "Great event" in desc

    def test_truncates_to_max_len(self):
        """Respects max_len."""
        body = "A" * 300
        desc = extract_short_description("Test", body, max_len=100)
        assert desc is not None
        assert len(desc) <= 100

    def test_returns_none_for_empty(self):
        """Returns None for empty body."""
        assert extract_short_description("Test", "") is None

    def test_first_sentences(self):
        """Extracts first meaningful sentences."""
        body = (
            "The CS department invites you to a talk by Prof. Smith on "
            "Machine Learning for Climate Science. "
            "This will be an exciting presentation."
        )
        desc = extract_short_description("CS Seminar", body)
        assert desc is not None
        assert "CS department" in desc


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

    def test_single_event_has_rsvp_and_free_food(self):
        """Email with RSVP link and free food mention populates new fields."""
        subject = "Movie Night this Friday!"
        body = (
            "Hey Wildcats! Join Northwestern Film Club for our weekly movie night.\n\n"
            "When: Friday, March 28, 2026 at 7:00 PM\n"
            "Where: Norris University Center, Room 201\n"
            "What: We'll be screening \"Everything Everywhere All At Once\"\n\n"
            "Free popcorn! All are welcome.\n"
            "RSVP: https://forms.gle/abc123\n"
        )
        events = parse_event_email(
            subject, body,
            sender="filmclub@u.northwestern.edu",
            reference_date=date(2026, 3, 25),
        )
        assert len(events) == 1
        ev = events[0]
        assert ev.has_free_food is True
        assert ev.rsvp_url is not None
        assert "forms.gle" in ev.rsvp_url

    def test_single_event_no_free_food(self):
        """Email without free food mention has has_free_food=False."""
        subject = "CS Department Seminar"
        body = (
            "The CS department invites you to a talk.\n"
            "Date: Tuesday, April 1, 2026\n"
            "Time: 3:30 PM - 4:30 PM\n"
            "Location: Tech L160\n"
        )
        events = parse_event_email(
            subject, body,
            reference_date=date(2026, 3, 25),
        )
        assert len(events) == 1
        assert events[0].has_free_food is False
        assert events[0].rsvp_url is None

    def test_description_extracted(self):
        """Short description is extracted for single event emails."""
        subject = "Movie Night!"
        body = (
            "What: A screening of Inception at the Norris theater.\n"
            "When: March 28, 2026 at 7pm\n"
            "Where: Norris\n"
        )
        events = parse_event_email(
            subject, body,
            reference_date=date(2026, 3, 25),
        )
        assert len(events) == 1
        assert events[0].description is not None
        assert "Inception" in events[0].description


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


# ---------------------------------------------------------------------------
# Event Confidence Scoring
# ---------------------------------------------------------------------------

class TestScoreEventConfidence:
    """Tests for score_event_confidence()."""

    def test_real_event_high_score(self):
        """A clear event (time + location + event language) scores high."""
        from src.services.email_parser import score_event_confidence
        score = score_event_confidence(
            "Movie Night this Friday!",
            "Join us for a movie screening at Norris University Center.",
            has_time=True, has_location=True,
            event_date=date(2026, 3, 28),
            reference_date=date(2026, 3, 27),
        )
        assert score >= 3

    def test_course_announcement_low_score(self):
        """A course announcement scores below threshold."""
        from src.services.email_parser import score_event_confidence
        score = score_event_confidence(
            "Fall Quarter Course Offering",
            "Students can take a fall-quarter POLI_SCI 390 course, taught by Professor Smith. "
            "Enrollment begins November 9. Prerequisites: POLI_SCI 201.",
            has_time=False, has_location=False,
            event_date=date(2020, 11, 9),
            reference_date=date(2026, 3, 27),
        )
        assert score < 3

    def test_job_posting_low_score(self):
        """A job posting scores below threshold."""
        from src.services.email_parser import score_event_confidence
        score = score_event_confidence(
            "We're Hiring! Research Assistant Position",
            "We are looking for a part-time research assistant. Application deadline March 31. "
            "Please submit your resume and cover letter.",
            has_time=False, has_location=False,
            event_date=date(2026, 3, 31),
            reference_date=date(2026, 3, 27),
        )
        assert score < 3

    def test_event_with_when_where(self):
        """An email with When:/Where: structure scores high."""
        from src.services.email_parser import score_event_confidence
        score = score_event_confidence(
            "CS Department Talk",
            "When: Friday, March 28 at 3:30 PM\nWhere: Tech L160\nTalk on ML.",
            has_time=True, has_location=True,
            event_date=date(2026, 3, 28),
            reference_date=date(2026, 3, 27),
        )
        assert score >= 3

    def test_past_date_penalized(self):
        """Events in the past get score penalty."""
        from src.services.email_parser import score_event_confidence
        score = score_event_confidence(
            "Last week's event",
            "This happened last week.",
            has_time=True, has_location=False,
            event_date=date(2026, 3, 20),
            reference_date=date(2026, 3, 27),
        )
        future_score = score_event_confidence(
            "Next week's event",
            "Join us next week.",
            has_time=True, has_location=False,
            event_date=date(2026, 4, 3),
            reference_date=date(2026, 3, 27),
        )
        assert score < future_score

    def test_course_email_filtered_in_parse(self):
        """parse_event_email returns empty for course announcements."""
        events = parse_event_email(
            "Fall Quarter Course",
            "Accepted students take a fall-quarter POLI_SCI 390 course, taught by "
            "Professor Smith. Enrollment begins November 9, 2026. Prerequisites: none.",
            reference_date=date(2026, 3, 27),
        )
        assert events == []
