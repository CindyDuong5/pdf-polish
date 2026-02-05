from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Read-only Gmail access (safest for intake)
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def main():
    load_dotenv()

    creds_path = Path(os.getenv("GMAIL_CREDENTIALS_PATH", "./credentials.json")).resolve()
    token_path = Path(os.getenv("GMAIL_TOKEN_PATH", "./token.json")).resolve()

    if not creds_path.exists():
        raise FileNotFoundError(f"credentials.json not found at: {creds_path}")

    creds: Credentials | None = None

    # Load existing token if present
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    # Refresh or create token
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token.json
        token_path.write_text(creds.to_json(), encoding="utf-8")

    print(f"✅ Saved token to: {token_path}")

    # Quick sanity: call Gmail API
    service = build("gmail", "v1", credentials=creds)

    profile = service.users().getProfile(userId="me").execute()
    print("✅ Gmail profile:", profile.get("emailAddress"))

    # List labels to confirm your setup
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    label_names = sorted([l["name"] for l in labels])
    print("\nFound labels (showing any that start with buildops/):")
    for name in label_names:
        if name.startswith("buildops/"):
            print(" -", name)

    print("\nDone.")

if __name__ == "__main__":
    main()
