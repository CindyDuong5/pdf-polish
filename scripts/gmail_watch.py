
# scripts/gmail_watch.py
# scripts/gmail_watch.py
import json
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# adjust if token.json is elsewhere
TOKEN_PATH = Path(__file__).resolve().parents[1] / "token.json"

TOPIC_NAME = "projects/pdf-polish-gmail-intake-484818/topics/gmail-intake"

def main():
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
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
