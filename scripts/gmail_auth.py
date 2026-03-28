#!/usr/bin/env python3
"""One-time Gmail OAuth authorization.

Run this script to authorize the app to access your Gmail:
    python scripts/gmail_auth.py [--credentials path/to/credentials.json] [--token path/to/token.json]

This opens a browser window where you log in with your NU Google account.
After authorization, a token.json file is saved for future use.
"""

import argparse
import sys
from pathlib import Path

# Ensure the backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from src.config import settings
from src.services.gmail_auth import get_gmail_credentials


def main() -> None:
    parser = argparse.ArgumentParser(description="Authorize Gmail OAuth access.")
    parser.add_argument(
        "--credentials",
        default=settings.gmail_credentials_file,
        help="Path to OAuth client-secret JSON (default: %(default)s)",
    )
    parser.add_argument(
        "--token",
        default=settings.gmail_token_file,
        help="Path to save the OAuth token (default: %(default)s)",
    )
    args = parser.parse_args()

    print(f"Authorizing with credentials from: {args.credentials}")
    creds = get_gmail_credentials(args.credentials, args.token)

    # Try to extract the email from the token id_token or just confirm success
    print(f"\n✅ Authorization successful! Token saved to: {args.token}")
    print(f"📬 Gmail label to poll: {settings.gmail_label}")
    print("\nYou can now run the poller with:")
    print("  python scripts/run_poller.py")


if __name__ == "__main__":
    main()
