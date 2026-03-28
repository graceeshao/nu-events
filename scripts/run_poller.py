#!/usr/bin/env python3
"""Run the Gmail IMAP poller as a standalone process.

Usage:
    python scripts/run_poller.py [--once] [--interval SECONDS]

Options:
    --once          Poll once and exit (useful for cron)
    --interval      Override polling interval in seconds (default: 900)
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure the backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from src.config import settings
from src.services.gmail_poller import GmailPoller


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Gmail event poller.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Poll once and exit (useful for cron jobs)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=settings.gmail_poll_interval_seconds,
        help="Polling interval in seconds (default: %(default)s)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    poller = GmailPoller(
        credentials_file=settings.gmail_credentials_file,
        token_file=settings.gmail_token_file,
        label=settings.gmail_label,
        imap_host=settings.gmail_imap_host,
        imap_port=settings.gmail_imap_port,
    )

    if args.once:
        result = asyncio.run(poller.poll_once())
        print(f"Poll complete: {result}")
    else:
        print(f"Starting continuous poller (interval={args.interval}s) ...")
        asyncio.run(poller.run_forever(interval_seconds=args.interval))


if __name__ == "__main__":
    main()
