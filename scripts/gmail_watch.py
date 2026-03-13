# scripts/gmail_watch.py
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from scripts.gmail_auth import SCOPES

load_dotenv()

TOKEN_PATH = Path(os.getenv("GMAIL_TOKEN_PATH", "./token.json")).resolve()
TOPIC_NAME = os.environ["GMAIL_PUBSUB_TOPIC"]


def main() -> None:
    if not TOKEN_PATH.exists():
        raise FileNotFoundError(
            f"token.json not found at: {TOKEN_PATH}. "
            "Run scripts/gmail_auth.py first or set GMAIL_TOKEN_PATH."
        )

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds.expired and creds.refresh_token:
        print(f"Refreshing Gmail credentials from local token: {TOKEN_PATH}")
        creds.refresh(Request())

        # Save refreshed token back to disk so future runs stay healthy
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        print(f"Saved refreshed token to: {TOKEN_PATH}")

    service = build("gmail", "v1", credentials=creds)

    body = {
        "topicName": TOPIC_NAME,
        "labelIds": ["INBOX"],
    }

    resp = service.users().watch(userId="me", body=body).execute()
    print(json.dumps(resp, indent=2))


if __name__ == "__main__":
    main()