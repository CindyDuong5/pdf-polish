# app/web/server.py
from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import FastAPI, HTTPException, Request
from google.cloud import pubsub_v1
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.gmail_client import GmailClient  # ✅ unified auth path
from app.models import GmailJob, GmailState
import logging
logger = logging.getLogger(__name__)

app = FastAPI(title="PDF Polish Gmail Push Webhook", version="0.1.0")

# Cache GmailClient/service across requests within a single Cloud Run instance
_GMAIL_CLIENT: GmailClient | None = None


def _env_required(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val


def _get_gmail_service():
    global _GMAIL_CLIENT
    if _GMAIL_CLIENT is None:
        _GMAIL_CLIENT = GmailClient()
    _GMAIL_CLIENT.ensure_latest_token()  # ✅ picks up Secret Manager latest without redeploy
    return _GMAIL_CLIENT.service


def _db() -> Session:
    return SessionLocal()


def _get_or_create_state(db: Session) -> GmailState:
    state = db.query(GmailState).filter(GmailState.id == "main").one_or_none()
    if not state:
        state = GmailState(id="main", last_history_id=None)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def _decode_pubsub_push(payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """
    Pub/Sub push payload:
    {
      "message": { "data": "base64...", ... },
      "subscription": "..."
    }

    Gmail push data (decoded base64) is JSON with:
    { "emailAddress": "...", "historyId": "12345" }
    """
    msg = payload.get("message") or {}
    data_b64 = msg.get("data")
    if not data_b64:
        return None, None

    try:
        raw = base64.b64decode(data_b64).decode("utf-8")
        data = json.loads(raw)
        return data.get("emailAddress"), data.get("historyId")
    except Exception:
        return None, None


def _extract_message_ids_from_history(history_list: List[Dict[str, Any]]) -> Set[str]:
    mids: Set[str] = set()

    for h in history_list or []:
        # Most reliable for "new mail" is messagesAdded
        for added in h.get("messagesAdded", []) or []:
            m = added.get("message") or {}
            mid = m.get("id")
            if mid:
                mids.add(mid)

        # Fallback: sometimes "messages" is present
        for m in h.get("messages", []) or []:
            mid = m.get("id")
            if mid:
                mids.add(mid)

    return mids


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/")
def root():
    # Avoid confusing 404s from casual browser checks / health probes.
    return {"ok": True, "service": "gmail-pdf-webhook"}


def _topic_exists(topic_name: str) -> bool:
    """
    Validate the Pub/Sub topic exists. topic_name must be full resource path:
      projects/<project>/topics/<topic>
    """
    client = pubsub_v1.PublisherClient()
    try:
        client.get_topic(request={"topic": topic_name})
        return True
    except Exception:
        return False


@app.post("/gmail/renew-watch")
def renew_watch():
    """
    Called by Cloud Scheduler daily (or more often).
    Creates/renews Gmail watch -> Pub/Sub topic.
    Stores initial last_history_id if empty.
    """
    topic_name = _env_required("GMAIL_PUBSUB_TOPIC")

    # Ensure topic is full path (common gotcha)
    if not topic_name.startswith("projects/") or "/topics/" not in topic_name:
        raise HTTPException(
            status_code=500,
            detail=(
                "GMAIL_PUBSUB_TOPIC must be a full topic resource path like "
                "'projects/<project>/topics/<topic>'. "
                f"Got: {topic_name}"
            ),
        )

    if not _topic_exists(topic_name):
        raise HTTPException(status_code=500, detail=f"GMAIL_PUBSUB_TOPIC does not exist: {topic_name}")

    watch_body = {
        "topicName": topic_name,
        # Optional:
        # "labelIds": ["INBOX"],
        # "labelFilterAction": "include",
    }

    service = _get_gmail_service()

    try:
        resp = service.users().watch(userId="me", body=watch_body).execute()
    except Exception as e:
        # Keep detail for debugging; logs will have stack trace if unhandled
        logger.exception("users.watch failed")
        raise HTTPException(status_code=500, detail=f"users.watch failed: {e}")

    history_id = resp.get("historyId")

    db = _db()
    try:
        state = _get_or_create_state(db)

        # If state is empty, initialize it to returned historyId.
        # If already set, keep it (overwriting could skip items).
        if not state.last_history_id and history_id:
            state.last_history_id = str(history_id)
            db.commit()

        return {
            "ok": True,
            "topicName": topic_name,
            "watch_historyId": history_id,
            "stored_last_history_id": state.last_history_id,
            "expiration": resp.get("expiration"),
        }
    finally:
        db.close()


async def _handle_pubsub_push(request: Request) -> Dict[str, Any]:
    """
    Single handler used by BOTH endpoints:
      - /pubsub/gmail   (new)
      - /webhooks/gmail (legacy)
    This prevents endpoint mismatch issues forever.
    """
    payload = await request.json()
    email_address, pushed_history_id = _decode_pubsub_push(payload)

    # If Pub/Sub payload is malformed, still ACK 200 so Pub/Sub doesn't retry forever
    if not pushed_history_id:
        return {"ok": True, "note": "No historyId in push payload; acked."}

    service = _get_gmail_service()

    db = _db()
    try:
        state = _get_or_create_state(db)

        # First push ever (or state not initialized):
        # store historyId and return. This prevents scanning from "nothing".
        if not state.last_history_id:
            state.last_history_id = str(pushed_history_id)
            db.commit()
            return {
                "ok": True,
                "emailAddress": email_address,
                "note": "Initialized last_history_id from first push.",
                "stored_last_history_id": state.last_history_id,
            }

        start_history_id = state.last_history_id

        enqueued = 0
        skipped = 0
        message_ids: Set[str] = set()

        page_token: Optional[str] = None
        newest_history_id: Optional[str] = None

        while True:
            try:
                req = service.users().history().list(
                    userId="me",
                    startHistoryId=start_history_id,
                    historyTypes=["messageAdded"],
                    pageToken=page_token,
                )
                resp = req.execute()
            except Exception as e:
                # Common case: "startHistoryId too old" (HTTP 404).
                # For MVP: reset cursor to pushed historyId so we recover and continue.
                state.last_history_id = str(pushed_history_id)
                db.commit()
                return {
                    "ok": True,
                    "emailAddress": email_address,
                    "warning": (
                        f"history.list failed from startHistoryId={start_history_id}. "
                        "Cursor reset to pushed historyId."
                    ),
                    "error": str(e),
                    "stored_last_history_id": state.last_history_id,
                }

            newest_history_id = resp.get("historyId") or newest_history_id
            history_list = resp.get("history", []) or []
            message_ids |= _extract_message_ids_from_history(history_list)

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        # Enqueue message IDs (idempotent)
        for mid in message_ids:
            job = GmailJob(gmail_message_id=mid, label=None, status="QUEUED", error=None)
            db.add(job)
            try:
                db.commit()
                enqueued += 1
            except IntegrityError:
                db.rollback()
                skipped += 1

        # Advance cursor
        if newest_history_id:
            state.last_history_id = str(newest_history_id)
        else:
            # fallback: at least advance to pushed id
            state.last_history_id = str(pushed_history_id)

        db.commit()

        return {
            "ok": True,
            "emailAddress": email_address,
            "pushed_history_id": pushed_history_id,
            "start_history_id": start_history_id,
            "new_last_history_id": state.last_history_id,
            "message_ids_found": len(message_ids),
            "enqueued": enqueued,
            "skipped_duplicates": skipped,
        }
    finally:
        db.close()


@app.post("/pubsub/gmail")
async def pubsub_gmail(request: Request):
    """
    Primary endpoint: configure Pub/Sub push to hit this.
    """
    return await _handle_pubsub_push(request)


@app.post("/webhooks/gmail")
async def gmail_webhook_legacy(request: Request):
    """
    Legacy endpoint (older configs used this).
    Keep forever so endpoint mismatches never break ingestion.
    """
    return await _handle_pubsub_push(request)


@app.get("/debug/config")
def debug_config():
    return {
        "topic": os.getenv("GMAIL_PUBSUB_TOPIC"),
        "service": "gmail-pdf-webhook",
        "uses": "GmailClient (Secret Manager via GMAIL_PROJECT_ID + GMAIL_TOKEN_SECRET)",
    }

@app.get("/debug/version")
def debug_version():
    return {"version": "2026-02-25-healthz-v1"}