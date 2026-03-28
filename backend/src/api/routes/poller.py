"""API routes for the Gmail IMAP poller.

Provides manual trigger and status endpoints for the poller service.
"""

import os
from datetime import datetime

from fastapi import APIRouter

from src.config import settings
from src.services.gmail_poller import GmailPoller

router = APIRouter()

# Module-level poller instance (lazily created on first trigger)
_poller: GmailPoller | None = None


def _get_poller() -> GmailPoller:
    """Return the singleton GmailPoller instance."""
    global _poller
    if _poller is None:
        _poller = GmailPoller(
            credentials_file=settings.gmail_credentials_file,
            token_file=settings.gmail_token_file,
            label=settings.gmail_label,
            imap_host=settings.gmail_imap_host,
            imap_port=settings.gmail_imap_port,
        )
    return _poller


@router.post("/trigger")
async def trigger_poll() -> dict:
    """Trigger a single poll cycle and return the results.

    Useful for manual testing or webhook-based invocation.
    """
    poller = _get_poller()
    result = await poller.poll_once()
    return {"status": "ok", "result": result}


@router.get("/status")
async def poller_status() -> dict:
    """Return the current poller configuration and last-run info."""
    poller = _get_poller()
    credentials_configured = os.path.exists(settings.gmail_credentials_file)
    token_exists = os.path.exists(settings.gmail_token_file)

    return {
        "credentials_configured": credentials_configured,
        "token_exists": token_exists,
        "gmail_label": settings.gmail_label,
        "poll_interval_seconds": settings.gmail_poll_interval_seconds,
        "last_poll_time": (
            poller.last_poll_time.isoformat() if poller.last_poll_time else None
        ),
        "last_poll_result": poller.last_poll_result,
    }
