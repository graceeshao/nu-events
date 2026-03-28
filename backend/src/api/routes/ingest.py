"""API routes for email ingestion and event extraction.

Provides endpoints to submit event-announcement emails (as JSON or raw
text) and automatically extract calendar events from them.
"""

import re
from datetime import datetime

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import get_db
from src.models.email_ingest import IngestedEmail
from src.schemas.event import EventRead
from src.services.email_parser import parse_event_email
from src.services.event_service import create_event

router = APIRouter()


class EmailIngestRequest(BaseModel):
    """Request body for the structured email ingest endpoint."""

    subject: str = Field("", description="Email subject line")
    body: str = Field(..., description="Email body text")
    sender: str | None = Field(None, description="Sender email address")


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
        parsed_events = parse_event_email(
            subject=payload.subject,
            body=payload.body,
            sender=payload.sender,
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


def _parse_raw_email(raw: str) -> tuple[str, str, str | None]:
    """Extract Subject, From, and body from a raw email string.

    Args:
        raw: Raw email text with RFC 822-style headers.

    Returns:
        Tuple of (subject, body, sender).
    """
    subject = ""
    sender = None
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

    body = "\n".join(lines[body_start:]).strip()
    return subject, body, sender


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

    subject, body, sender = _parse_raw_email(raw)

    try:
        parsed_events = parse_event_email(
            subject=subject,
            body=body,
            sender=sender,
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
