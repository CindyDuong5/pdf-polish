# scripts/gmail_watch.py
import json
from pathlib import Path
import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from scripts.gmail_auth import SCOPES

# adjust if token.json is elsewhere
TOKEN_PATH = Path(__file__).resolve().parents[1] / "token.json"
TOPIC_NAME = os.environ["GMAIL_PUBSUB_TOPIC"]

def main():
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    service = build("gmail", "v1", credentials=creds)

    body = {
        "topicName": TOPIC_NAME,
        "labelIds": ["INBOX"],
    }

    resp = service.users().watch(
        userId="me",
        body=body
    ).execute()

    print(json.dumps(resp, indent=2))

if __name__ == "__main__":
    main()
