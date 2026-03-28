"""Gmail IMAP poller for ingesting event emails.

Connects to Gmail via IMAP using OAuth2, reads unread emails from a
configured label (default: NU-Events), parses them for event data,
and creates events in the database.
"""

import asyncio
import base64
import email as email_lib
import imaplib
import logging
import re
from datetime import datetime
from email.header import decode_header
from email.utils import parseaddr
from typing import Any

from src.database.session import async_session_factory
from src.models.email_ingest import IngestedEmail
from src.services.email_parser import parse_event_email
from src.services.event_service import create_event
from src.services.gmail_auth import get_gmail_credentials, get_oauth2_string

logger = logging.getLogger(__name__)


def _decode_header_value(raw: str | None) -> str:
    """Decode an RFC 2047 encoded email header into a plain string."""
    if not raw:
        return ""
    parts: list[str] = []
    for fragment, charset in decode_header(raw):
        if isinstance(fragment, bytes):
            parts.append(fragment.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(fragment)
    return " ".join(parts)


def _extract_body(msg: email_lib.message.Message) -> str:
    """Extract the best plain-text body from an email message.

    Prefers ``text/plain`` parts; falls back to ``text/html`` with tags
    stripped.
    """
    text_parts: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            # Skip attachments
            if part.get("Content-Disposition", "").startswith("attachment"):
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if content_type == "text/plain":
                text_parts.append(decoded)
            elif content_type == "text/html":
                html_parts.append(decoded)
    else:
        payload = msg.get_payload(decode=True)
        if payload is not None:
            charset = msg.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html_parts.append(decoded)
            else:
                text_parts.append(decoded)

    if text_parts:
        return "\n".join(text_parts)
    if html_parts:
        html = "\n".join(html_parts)
        return re.sub(r"<[^>]+>", " ", html).strip()
    return ""


def _get_user_email(creds: Any) -> str:
    """Retrieve the Gmail address associated with the OAuth credentials.

    Checks the GMAIL_USER_EMAIL env var first, then tries Google's
    tokeninfo endpoint. Falls back to an empty string if neither works.
    """
    import os

    # Prefer explicit env var
    env_email = os.environ.get("GMAIL_USER_EMAIL", "")
    if env_email:
        return env_email

    # Try tokeninfo (only works if email scope was requested)
    try:
        import urllib.request
        import json as _json

        req = urllib.request.Request(
            f"https://oauth2.googleapis.com/tokeninfo?access_token={creds.token}"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            info = _json.loads(resp.read())
            return info.get("email", "")
    except Exception:
        logger.warning("Could not determine user email from token; set GMAIL_USER_EMAIL env var")
        return ""


def _sync_poll(
    credentials_file: str,
    token_file: str,
    label: str,
    imap_host: str,
    imap_port: int,
) -> list[dict[str, Any]]:
    """Synchronous IMAP fetch — intended to run via ``asyncio.to_thread()``.

    Returns a list of dicts with keys ``subject``, ``sender``, ``body``,
    ``uid`` for every UNSEEN message in *label*.
    """
    creds = get_gmail_credentials(credentials_file, token_file)

    # Get the user's email from the token metadata or via tokeninfo
    user_email = _get_user_email(creds)
    logger.info("Authenticating as %s", user_email)

    # Build the XOAUTH2 auth string (raw bytes — imaplib handles base64)
    oauth2_str = get_oauth2_string(user_email, creds.token)

    imap = imaplib.IMAP4_SSL(imap_host, imap_port)
    imap.authenticate("XOAUTH2", lambda _: oauth2_str.encode())

    # Select the label folder
    status, data = imap.select(f'"{label}"')
    if status != "OK":
        logger.error("Failed to select label '%s': %s", label, data)
        imap.logout()
        return []

    # Search for unread messages
    status, msg_ids = imap.search(None, "UNSEEN")
    if status != "OK" or not msg_ids or not msg_ids[0]:
        logger.info("No UNSEEN messages in '%s'.", label)
        imap.logout()
        return []

    ids = msg_ids[0].split()
    logger.info("Found %d UNSEEN message(s) in '%s'.", len(ids), label)

    results: list[dict[str, Any]] = []
    for mid in ids:
        status, msg_data = imap.fetch(mid, "(RFC822)")
        if status != "OK" or not msg_data or not msg_data[0]:
            logger.warning("Failed to fetch message %s", mid)
            continue

        raw_email = msg_data[0][1]
        msg = email_lib.message_from_bytes(raw_email)

        subject = _decode_header_value(msg.get("Subject"))
        _, sender = parseaddr(msg.get("From", ""))
        list_id = msg.get("List-Id", "") or ""
        list_sender = msg.get("Sender", "") or ""
        body = _extract_body(msg)

        results.append(
            {
                "subject": subject,
                "sender": sender,
                "body": body,
                "uid": mid,
                "list_id": list_id,
                "list_sender": list_sender,
            }
        )

        # Mark as SEEN (IMAP already does this on FETCH with RFC822,
        # but be explicit)
        imap.store(mid, "+FLAGS", "\\Seen")

    imap.logout()
    return results


class GmailPoller:
    """Polls a Gmail label for event emails and ingests them.

    Args:
        credentials_file: Path to the Google OAuth client-secret JSON.
        token_file: Path to the persisted OAuth token JSON.
        label: Gmail label / IMAP folder to poll.
        imap_host: IMAP server hostname.
        imap_port: IMAP server port (SSL).
    """

    def __init__(
        self,
        credentials_file: str,
        token_file: str,
        label: str = "NU-Events",
        imap_host: str = "imap.gmail.com",
        imap_port: int = 993,
    ) -> None:
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.label = label
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.last_poll_time: datetime | None = None
        self.last_poll_result: dict[str, Any] | None = None

    async def poll_once(self) -> dict[str, int]:
        """Execute a single poll cycle.

        Fetches UNSEEN messages from the configured Gmail label, parses
        each for events, persists them, and records the ingested email.

        Returns:
            Summary dict with ``emails_processed`` and ``events_created``.
        """
        logger.info(
            "Starting poll cycle for label '%s' on %s:%d",
            self.label,
            self.imap_host,
            self.imap_port,
        )

        messages = await asyncio.to_thread(
            _sync_poll,
            self.credentials_file,
            self.token_file,
            self.label,
            self.imap_host,
            self.imap_port,
        )

        emails_processed = 0
        events_created = 0

        async with async_session_factory() as db:
            for msg in messages:
                subject = msg["subject"]
                sender = msg["sender"]
                body = msg["body"]
                list_id = msg.get("list_id", "")
                list_sender = msg.get("list_sender", "")

                try:
                    parsed_events = parse_event_email(
                        subject, body, sender,
                        list_id=list_id, list_sender=list_sender,
                    )
                    for event_in in parsed_events:
                        await create_event(db, event_in)
                        events_created += 1

                    record = IngestedEmail(
                        subject=subject,
                        sender=sender,
                        body=body,
                        events_created=len(parsed_events),
                        status="processed",
                    )
                    db.add(record)
                    emails_processed += 1
                except Exception:
                    logger.exception(
                        "Error processing email '%s' from %s", subject, sender
                    )
                    record = IngestedEmail(
                        subject=subject,
                        sender=sender,
                        body=body,
                        events_created=0,
                        status="error",
                        error_message="Parse/ingest failure",
                    )
                    db.add(record)
                    emails_processed += 1

            await db.commit()

        summary = {
            "emails_processed": emails_processed,
            "events_created": events_created,
        }
        self.last_poll_time = datetime.now()
        self.last_poll_result = summary
        logger.info("Poll complete: %s", summary)
        return summary

    async def run_forever(self, interval_seconds: int = 900) -> None:
        """Continuously poll at *interval_seconds* intervals.

        Errors are logged but never crash the loop.
        """
        logger.info(
            "Starting continuous poller (interval=%ds, label='%s').",
            interval_seconds,
            self.label,
        )
        while True:
            try:
                await self.poll_once()
            except Exception:
                logger.exception("Poll cycle failed; will retry next interval.")
            await asyncio.sleep(interval_seconds)
