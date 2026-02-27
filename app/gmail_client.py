# app/gmail_client.py
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def _load_secret_text_and_version(project_id: str, secret_name: str) -> tuple[str, str]:
    """
    Returns (secret_payload_text, version_resource_name)

    version_resource_name looks like:
      projects/<proj>/secrets/<secret>/versions/<N>
    """
    from google.cloud import secretmanager  # pip: google-cloud-secret-manager

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    resp = client.access_secret_version(request={"name": name})
    return resp.payload.data.decode("utf-8"), resp.name


@dataclass
class GmailMessageMeta:
    message_id: str
    thread_id: str
    subject: Optional[str]
    from_email: Optional[str]
    internal_date: Optional[datetime]  # UTC


class GmailClient:
    """
    Gmail client that supports two auth modes:
      - Cloud Run: Secret Manager token JSON via GMAIL_PROJECT_ID + GMAIL_TOKEN_SECRET
      - Local dev: token.json via GMAIL_TOKEN_PATH (or ./token.json)

    Additionally, when running on Cloud Run, it can auto-reload credentials if
    Secret Manager "latest" token version changes (no redeploy needed).
    """

    def __init__(self):
        # local dev convenience (Cloud Run ignores .env unless baked in)
        load_dotenv()

        self.project_id = os.getenv("GMAIL_PROJECT_ID")
        self.token_secret = os.getenv("GMAIL_TOKEN_SECRET")  # e.g. gmail-token-json

        self._secret_version_name: Optional[str] = None
        self._auth_source: str = ""

        creds, auth_source, version_name = self._load_creds()
        self._auth_source = auth_source
        self._secret_version_name = version_name

        print(f"GmailClient auth source = {auth_source}")
        self.service = build("gmail", "v1", credentials=creds)

    def _load_creds(self) -> tuple[Credentials, str, Optional[str]]:
        if self.project_id and self.token_secret:
            token_text, version_name = _load_secret_text_and_version(self.project_id, self.token_secret)
            token_info = json.loads(token_text)
            print("GMAIL TOKEN SECRET VERSION =", version_name)
            print("TOKEN SCOPES =", token_info.get("scopes"))
            print("HAS REFRESH TOKEN =", bool(token_info.get("refresh_token")))

            # ✅ Use scopes stored in token JSON if present, fallback to SCOPES
            creds = Credentials.from_authorized_user_info(token_info, SCOPES)
            return creds, f"secret_manager:{self.token_secret}", version_name

        # Local fallback
        token_path = Path(os.getenv("GMAIL_TOKEN_PATH", "./token.json")).resolve()
        if not token_path.exists():
            raise FileNotFoundError(
                f"token.json not found at: {token_path}. "
                "Set GMAIL_PROJECT_ID+GMAIL_TOKEN_SECRET for Cloud Run, "
                "or run scripts/gmail_auth.py locally."
            )

        # ✅ Same idea locally: token file already includes scopes, but keep SCOPES as fallback
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        return creds, f"file:{token_path}", None

    def ensure_latest_token(self) -> None:
        if not (self.project_id and self.token_secret):
            return  # local mode

        token_text, latest_version_name = _load_secret_text_and_version(self.project_id, self.token_secret)
        if self._secret_version_name != latest_version_name:
            print(
                f"Gmail token rotated: {self._secret_version_name} -> {latest_version_name}. Reloading Gmail service..."
            )
            token_info = json.loads(token_text)

            # ✅ Use token's scopes if present
            creds = Credentials.from_authorized_user_info(token_info, SCOPES)

            self._secret_version_name = latest_version_name
            self.service = build("gmail", "v1", credentials=creds)

    def list_message_ids_by_label(self, label_name: str, max_results: int = 10) -> List[str]:
        """Return Gmail message IDs for a label."""
        self.ensure_latest_token()

        # Gmail API expects label IDs; label names work if they exist as a label.
        label_id = self._get_label_id_by_name(label_name)
        if not label_id:
            raise ValueError(f"Label not found: {label_name}")

        resp = (
            self.service.users()
            .messages()
            .list(userId="me", labelIds=[label_id], maxResults=max_results)
            .execute()
        )
        msgs = resp.get("messages", []) or []
        return [m["id"] for m in msgs]

    def fetch_message_meta(self, message_id: str) -> GmailMessageMeta:
        self.ensure_latest_token()

        msg = (
            self.service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            )
            .execute()
        )
        headers = {h["name"].lower(): h.get("value") for h in msg.get("payload", {}).get("headers", [])}

        internal_ms = msg.get("internalDate")
        internal_dt = None
        if internal_ms:
            internal_dt = datetime.fromtimestamp(int(internal_ms) / 1000, tz=timezone.utc)

        return GmailMessageMeta(
            message_id=msg["id"],
            thread_id=msg.get("threadId", ""),
            subject=headers.get("subject"),
            from_email=headers.get("from"),
            internal_date=internal_dt,
        )

    def download_pdf_attachments(self, message_id: str) -> List[Tuple[str, bytes]]:
        """Return list of (filename, pdf_bytes)."""
        self.ensure_latest_token()

        msg = self.service.users().messages().get(userId="me", id=message_id, format="full").execute()

        payload = msg.get("payload", {}) or {}
        parts = payload.get("parts", []) or []
        found: List[Tuple[str, bytes]] = []

        def walk(parts_list):
            for p in parts_list:
                mime = (p.get("mimeType") or "").lower()
                filename = p.get("filename") or ""
                body = p.get("body") or {}

                # Nested multiparts
                if p.get("parts"):
                    walk(p["parts"])

                # Attachments usually have attachmentId; some have inline data
                if mime == "application/pdf" and (body.get("attachmentId") or body.get("data")):
                    pdf_bytes = self._get_part_bytes(message_id, body)
                    if not filename:
                        filename = "attachment.pdf"
                    found.append((filename, pdf_bytes))

        walk(parts)
        return found

    def _get_part_bytes(self, message_id: str, body: dict) -> bytes:
        if body.get("data"):
            data = body["data"]
            return base64.urlsafe_b64decode(data.encode("utf-8"))

        attach_id = body.get("attachmentId")
        if not attach_id:
            raise ValueError("No attachmentId/data found for attachment part")

        att = (
            self.service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attach_id)
            .execute()
        )
        data = att["data"]
        return base64.urlsafe_b64decode(data.encode("utf-8"))

    def _get_label_id_by_name(self, label_name: str) -> Optional[str]:
        self.ensure_latest_token()

        labels = self.service.users().labels().list(userId="me").execute().get("labels", []) or []
        for l in labels:
            if l.get("name") == label_name:
                return l.get("id")
        return None