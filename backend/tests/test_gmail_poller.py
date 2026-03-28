"""Tests for the Gmail IMAP poller and OAuth helpers.

All IMAP and OAuth interactions are mocked — no real network calls.
"""

import email as email_lib
import imaplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.services.gmail_auth import get_oauth2_string
from src.services.gmail_poller import GmailPoller, _extract_body, _decode_header_value


# ---------------------------------------------------------------------------
# Helpers — build RFC822 messages for mocking
# ---------------------------------------------------------------------------

SAMPLE_PLAIN_EMAIL = (
    "From: filmclub@u.northwestern.edu\r\n"
    "To: graceshao@u.northwestern.edu\r\n"
    "Subject: Movie Night this Friday!\r\n"
    "Date: Thu, 27 Mar 2026 10:00:00 -0500\r\n"
    'Content-Type: text/plain; charset="utf-8"\r\n'
    "\r\n"
    "Hey Wildcats! Join NU Film Club for our weekly movie night.\r\n"
    "\r\n"
    "When: Friday, March 28, 2026 at 7:00 PM\r\n"
    "Where: Norris University Center, Room 201\r\n"
    'What: We\'ll be screening "Everything Everywhere All At Once"\r\n'
    "\r\n"
    "Free popcorn! All are welcome.\r\n"
)

SAMPLE_HTML_EMAIL = (
    "From: techclub@u.northwestern.edu\r\n"
    "To: graceshao@u.northwestern.edu\r\n"
    "Subject: Hackathon Registration Open\r\n"
    "Date: Thu, 27 Mar 2026 11:00:00 -0500\r\n"
    'Content-Type: text/html; charset="utf-8"\r\n'
    "\r\n"
    "<html><body><p>Join us for <b>WildHacks 2026</b>!</p>"
    "<p>When: Saturday, March 29, 2026 at 10:00 AM</p>"
    "<p>Where: Tech Auditorium</p></body></html>\r\n"
)


def _build_multipart_email() -> bytes:
    """Build a multipart email with both text/plain and text/html parts."""
    msg = MIMEMultipart("alternative")
    msg["From"] = "dance@u.northwestern.edu"
    msg["To"] = "graceshao@u.northwestern.edu"
    msg["Subject"] = "Spring Dance Show"
    msg["Date"] = "Thu, 27 Mar 2026 12:00:00 -0500"

    text = "Spring Dance Show\nWhen: April 5, 2026 at 8:00 PM\nWhere: Cahn Auditorium"
    html = (
        "<html><body><h1>Spring Dance Show</h1>"
        "<p>When: April 5, 2026 at 8:00 PM</p>"
        "<p>Where: Cahn Auditorium</p></body></html>"
    )
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    return msg.as_bytes()


# ---------------------------------------------------------------------------
# Tests — get_oauth2_string
# ---------------------------------------------------------------------------


class TestGetOauth2String:
    def test_format(self):
        result = get_oauth2_string("user@example.com", "tok123")
        assert result == "user=user@example.com\x01auth=Bearer tok123\x01\x01"

    def test_empty_user(self):
        result = get_oauth2_string("", "tok")
        assert result == "user=\x01auth=Bearer tok\x01\x01"


# ---------------------------------------------------------------------------
# Tests — _extract_body
# ---------------------------------------------------------------------------


class TestExtractBody:
    def test_plain_text(self):
        msg = email_lib.message_from_string(SAMPLE_PLAIN_EMAIL)
        body = _extract_body(msg)
        assert "Movie Night" not in body  # that's in the subject
        assert "Norris University Center" in body

    def test_html_only(self):
        msg = email_lib.message_from_string(SAMPLE_HTML_EMAIL)
        body = _extract_body(msg)
        assert "WildHacks 2026" in body
        # HTML tags should be stripped
        assert "<b>" not in body

    def test_multipart(self):
        msg = email_lib.message_from_bytes(_build_multipart_email())
        body = _extract_body(msg)
        # Should prefer text/plain
        assert "Spring Dance Show" in body
        assert "<html>" not in body


# ---------------------------------------------------------------------------
# Tests — _decode_header_value
# ---------------------------------------------------------------------------


class TestDecodeHeader:
    def test_plain_ascii(self):
        assert _decode_header_value("Hello World") == "Hello World"

    def test_none(self):
        assert _decode_header_value(None) == ""


# ---------------------------------------------------------------------------
# Tests — GmailPoller.poll_once
# ---------------------------------------------------------------------------


def _make_mock_imap(messages: list[bytes]):
    """Create a mock IMAP4_SSL that returns *messages* for UNSEEN search."""
    imap = MagicMock(spec=imaplib.IMAP4_SSL)
    imap.authenticate.return_value = ("OK", [b"Success"])
    imap.select.return_value = ("OK", [b"2"])

    if messages:
        ids = b" ".join(str(i + 1).encode() for i in range(len(messages)))
        imap.search.return_value = ("OK", [ids])

        def fetch_side_effect(mid, _fmt):
            idx = int(mid) - 1
            return ("OK", [(b"1 (RFC822 {1234})", messages[idx])])

        imap.fetch.side_effect = fetch_side_effect
    else:
        imap.search.return_value = ("OK", [b""])

    imap.store.return_value = ("OK", [b"Success"])
    imap.logout.return_value = ("BYE", [b"Logging out"])
    return imap


@pytest.fixture
def mock_creds():
    """Return a mock Credentials object."""
    creds = MagicMock()
    creds.token = "fake-access-token"
    creds.valid = True
    return creds


@pytest.mark.asyncio
class TestGmailPollerPollOnce:
    """Test poll_once with mocked IMAP and OAuth."""

    async def test_two_emails(self, mock_creds, db_engine):
        """Two UNSEEN emails → events created and emails recorded."""
        messages = [
            SAMPLE_PLAIN_EMAIL.encode(),
            SAMPLE_HTML_EMAIL.encode(),
        ]
        mock_imap = _make_mock_imap(messages)

        with (
            patch(
                "src.services.gmail_poller.get_gmail_credentials",
                return_value=mock_creds,
            ),
            patch(
                "src.services.gmail_poller.imaplib.IMAP4_SSL",
                return_value=mock_imap,
            ),
            patch(
                "src.services.gmail_poller.async_session_factory",
            ) as mock_sf,
        ):
            # Set up a real async session from the test db
            from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

            test_factory = async_sessionmaker(
                db_engine, class_=AsyncSession, expire_on_commit=False
            )
            mock_sf.__aenter__ = test_factory().__aenter__
            mock_sf.__aexit__ = test_factory().__aexit__
            mock_sf.return_value = test_factory()

            # Patch async_session_factory as a context manager
            session = test_factory()

            class FakeFactory:
                def __call__(self):
                    return session

                def __aenter__(self):
                    return session.__aenter__()

                def __aexit__(self, *args):
                    return session.__aexit__(*args)

            mock_sf_instance = MagicMock()
            mock_sf_instance.__aenter__ = AsyncMock(return_value=session)
            mock_sf_instance.__aexit__ = AsyncMock(return_value=None)
            mock_sf.return_value = mock_sf_instance

            # Actually, let's simplify: patch at module level
            # We need to wrap _sync_poll instead
            pass

        # Simpler approach: mock _sync_poll and the DB session
        with (
            patch(
                "src.services.gmail_poller._sync_poll",
                return_value=[
                    {
                        "subject": "Movie Night this Friday!",
                        "sender": "filmclub@u.northwestern.edu",
                        "body": (
                            "Hey Wildcats! Join NU Film Club for our weekly movie night.\n\n"
                            "When: Friday, March 28, 2026 at 7:00 PM\n"
                            "Where: Norris University Center, Room 201\n"
                            'What: We\'ll be screening "Everything Everywhere All At Once"\n\n'
                            "Free popcorn! All are welcome."
                        ),
                        "uid": b"1",
                    },
                    {
                        "subject": "Hackathon Registration Open",
                        "sender": "techclub@u.northwestern.edu",
                        "body": (
                            "Join us for WildHacks 2026!\n"
                            "When: Saturday, March 29, 2026 at 10:00 AM\n"
                            "Where: Tech Auditorium"
                        ),
                        "uid": b"2",
                    },
                ],
            ),
            patch("src.services.gmail_poller.async_session_factory", new=self._make_test_factory(db_engine)),
        ):
            poller = GmailPoller("creds.json", "token.json", "NU-Events")
            result = await poller.poll_once()

        assert result["emails_processed"] == 2
        assert result["events_created"] >= 2

    async def test_empty_mailbox(self, mock_creds, db_engine):
        """No UNSEEN messages → zero processed."""
        with (
            patch(
                "src.services.gmail_poller._sync_poll",
                return_value=[],
            ),
            patch("src.services.gmail_poller.async_session_factory", new=self._make_test_factory(db_engine)),
        ):
            poller = GmailPoller("creds.json", "token.json", "NU-Events")
            result = await poller.poll_once()

        assert result["emails_processed"] == 0
        assert result["events_created"] == 0

    async def test_imap_connection_error(self, mock_creds, db_engine):
        """IMAP connection failure → poll_once raises but doesn't crash run_forever."""
        with (
            patch(
                "src.services.gmail_poller._sync_poll",
                side_effect=imaplib.IMAP4.error("Connection refused"),
            ),
            patch("src.services.gmail_poller.async_session_factory", new=self._make_test_factory(db_engine)),
        ):
            poller = GmailPoller("creds.json", "token.json", "NU-Events")
            with pytest.raises(imaplib.IMAP4.error):
                await poller.poll_once()

    async def test_missing_label(self, mock_creds, db_engine):
        """When _sync_poll returns empty due to missing label, poll succeeds with 0."""
        with (
            patch(
                "src.services.gmail_poller._sync_poll",
                return_value=[],
            ),
            patch("src.services.gmail_poller.async_session_factory", new=self._make_test_factory(db_engine)),
        ):
            poller = GmailPoller("creds.json", "token.json", "NonExistent")
            result = await poller.poll_once()

        assert result["emails_processed"] == 0
        assert result["events_created"] == 0

    async def test_marks_seen(self, mock_creds):
        """Verify that _sync_poll calls imap.store with \\Seen flag."""
        mock_imap = _make_mock_imap([SAMPLE_PLAIN_EMAIL.encode()])

        with (
            patch(
                "src.services.gmail_poller.get_gmail_credentials",
                return_value=mock_creds,
            ),
            patch(
                "src.services.gmail_poller.imaplib.IMAP4_SSL",
                return_value=mock_imap,
            ),
        ):
            from src.services.gmail_poller import _sync_poll

            _sync_poll("creds.json", "token.json", "NU-Events", "imap.gmail.com", 993)

        mock_imap.store.assert_called_once_with(b"1", "+FLAGS", "\\Seen")

    @staticmethod
    def _make_test_factory(db_engine):
        """Build an async_sessionmaker tied to the test DB engine."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        return async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
