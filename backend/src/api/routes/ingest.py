"""API routes for email ingestion and event extraction.

Provides endpoints to submit event-announcement emails (as JSON or raw
text) and automatically extract calendar events from them.
"""

import logging
import re
from datetime import datetime

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database.session import get_db
from src.models.email_ingest import IngestedEmail
from src.schemas.event import EventRead
from src.services.email_parser import parse_event_email
from src.services.event_service import create_event
from src.services.llm_parser import parse_event_with_llm

logger = logging.getLogger(__name__)

router = APIRouter()


class EmailIngestRequest(BaseModel):
    """Request body for the structured email ingest endpoint."""

    subject: str = Field("", description="Email subject line")
    body: str = Field(..., description="Email body text")
    sender: str | None = Field(None, description="Sender email address")
    list_id: str = Field("", description="List-Id header (from LISTSERV)")
    list_sender: str = Field("", description="Sender header (from LISTSERV, e.g. owner-ANIME@...)")


class EmailIngestResponse(BaseModel):
    """Response from the email ingest endpoint."""

    status: str
    events_created: int
    events: list[EventRead]


@router.post("/email", response_model=EmailIngestResponse)
async def ingest_email(
    payload: EmailIngestRequest,
    db: AsyncSession = Depends(get_db),
) -> EmailIngestResponse:
    """Ingest a structured email and extract events from it.

    Accepts a JSON body with subject, body, and optional sender.
    Parses the email for event data using regex heuristics and creates
    events in the database.
    """
    try:
        if settings.use_llm_parser:
            try:
                parsed_events = await parse_event_with_llm(
                    subject=payload.subject,
                    body=payload.body,
                    sender=payload.sender,
                    list_id=payload.list_id,
                    list_sender=payload.list_sender,
                )
            except Exception:
                logger.warning("LLM parser failed, falling back to regex")
                parsed_events = parse_event_email(
                    subject=payload.subject,
                    body=payload.body,
                    sender=payload.sender,
                    list_id=payload.list_id,
                    list_sender=payload.list_sender,
                )
        else:
            parsed_events = parse_event_email(
                subject=payload.subject,
                body=payload.body,
                sender=payload.sender,
                list_id=payload.list_id,
                list_sender=payload.list_sender,
            )

        created: list[EventRead] = []
        for event_in in parsed_events:
            event = await create_event(db, event_in)
            created.append(EventRead.model_validate(event))

        status = "processed" if created else "no_events_found"
        record = IngestedEmail(
            subject=payload.subject,
            sender=payload.sender,
            body=payload.body,
            events_created=len(created),
            status=status,
        )
        db.add(record)
        await db.flush()

        return EmailIngestResponse(
            status=status,
            events_created=len(created),
            events=created,
        )
    except Exception as exc:
        record = IngestedEmail(
            subject=payload.subject,
            sender=payload.sender,
            body=payload.body,
            events_created=0,
            status="error",
            error_message=str(exc),
        )
        db.add(record)
        await db.flush()
        raise


def _parse_raw_email(raw: str) -> dict[str, str | None]:
    """Extract headers and body from a raw email string.

    Args:
        raw: Raw email text with RFC 822-style headers.

    Returns:
        Dict with keys: subject, body, sender, list_id, list_sender.
    """
    subject = ""
    sender = None
    list_id = ""
    list_sender = ""
    body_start = 0

    lines = raw.split("\n")
    for i, line in enumerate(lines):
        if line.strip() == "":
            body_start = i + 1
            break
        subj_match = re.match(r'^Subject:\s*(.+)', line, re.IGNORECASE)
        if subj_match:
            subject = subj_match.group(1).strip()
        from_match = re.match(r'^From:\s*(.+)', line, re.IGNORECASE)
        if from_match:
            sender = from_match.group(1).strip()
        listid_match = re.match(r'^List-Id:\s*(.+)', line, re.IGNORECASE)
        if listid_match:
            list_id = listid_match.group(1).strip()
        sender_match = re.match(r'^Sender:\s*(.+)', line, re.IGNORECASE)
        if sender_match:
            list_sender = sender_match.group(1).strip()

    body = "\n".join(lines[body_start:]).strip()
    return {
        "subject": subject,
        "body": body,
        "sender": sender,
        "list_id": list_id,
        "list_sender": list_sender,
    }


@router.post("/raw", response_model=EmailIngestResponse)
async def ingest_raw(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> EmailIngestResponse:
    """Ingest a raw email (text/plain) and extract events from it.

    Parses RFC 822-style Subject/From headers and extracts the body.
    """
    raw_bytes = await request.body()
    raw = raw_bytes.decode("utf-8", errors="replace")

    parsed = _parse_raw_email(raw)
    subject = parsed["subject"]
    body = parsed["body"]
    sender = parsed["sender"]
    list_id = parsed["list_id"]
    list_sender = parsed["list_sender"]

    try:
        if settings.use_llm_parser:
            try:
                parsed_events = await parse_event_with_llm(
                    subject=subject,
                    body=body,
                    sender=sender,
                    list_id=list_id,
                    list_sender=list_sender,
                )
            except Exception:
                logger.warning("LLM parser failed, falling back to regex")
                parsed_events = parse_event_email(
                    subject=subject,
                    body=body,
                    sender=sender,
                    list_id=list_id,
                    list_sender=list_sender,
                )
        else:
            parsed_events = parse_event_email(
                subject=subject,
                body=body,
                sender=sender,
                list_id=list_id,
                list_sender=list_sender,
            )

        created: list[EventRead] = []
        for event_in in parsed_events:
            event = await create_event(db, event_in)
            created.append(EventRead.model_validate(event))

        status = "processed" if created else "no_events_found"
        record = IngestedEmail(
            subject=subject,
            sender=sender,
            body=body,
            events_created=len(created),
            status=status,
        )
        db.add(record)
        await db.flush()

        return EmailIngestResponse(
            status=status,
            events_created=len(created),
            events=created,
        )
    except Exception as exc:
        record = IngestedEmail(
            subject=subject,
            sender=sender,
            body=body,
            events_created=0,
            status="error",
            error_message=str(exc),
        )
        db.add(record)
        await db.flush()
        raise
