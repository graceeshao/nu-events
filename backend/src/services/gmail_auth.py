"""Google OAuth2 authentication for Gmail IMAP access.

Handles the OAuth2 flow:
1. First run: Opens browser for user authorization, saves refresh token
2. Subsequent runs: Uses saved refresh token to get fresh access tokens
"""

import json
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://mail.google.com/"]


def get_gmail_credentials(
    credentials_file: str, token_file: str
) -> Credentials:
    """Obtain valid Gmail OAuth2 credentials.

    Loads cached credentials from *token_file* when available.  If the
    token is expired it is refreshed automatically.  When no cached token
    exists the full OAuth2 authorization flow is triggered (opens a
    browser window).

    Args:
        credentials_file: Path to the Google Cloud OAuth client-secret
            JSON file (``credentials.json``).
        token_file: Path where the refresh/access token is persisted
            (``token.json``).

    Returns:
        A valid ``google.oauth2.credentials.Credentials`` instance.

    Raises:
        FileNotFoundError: If *credentials_file* does not exist and no
            cached token is available.
    """
    creds: Credentials | None = None

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not os.path.exists(credentials_file):
            raise FileNotFoundError(
                f"OAuth credentials file not found: {credentials_file}. "
                "Download it from the Google Cloud Console."
            )
        flow = InstalledAppFlow.from_client_secrets_file(
            credentials_file, SCOPES
        )
        creds = flow.run_local_server(port=0)

    # Persist for next run
    with open(token_file, "w") as f:
        f.write(creds.to_json())

    return creds


def get_oauth2_string(user: str, access_token: str) -> str:
    """Build the XOAUTH2 authentication string for IMAP.

    Args:
        user: Gmail address (e.g. ``graceshao@u.northwestern.edu``).
        access_token: A valid OAuth2 access token.

    Returns:
        The XOAUTH2 string expected by ``IMAP4.authenticate()``.
    """
    return f"user={user}\x01auth=Bearer {access_token}\x01\x01"
