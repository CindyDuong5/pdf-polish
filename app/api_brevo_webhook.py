# app/api_brevo_webhook.py

from __future__ import annotations

import json
import re

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.db import SessionLocal

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _extract_doc_id(payload: dict) -> str | None:
    custom = (
        payload.get("X-Mailin-custom")
        or payload.get("x-mailin-custom")
        or payload.get("headers", {}).get("X-Mailin-custom")
        or payload.get("headers", {}).get("x-mailin-custom")
        or ""
    )

    custom = str(custom)

    m = re.search(r"doc_id:([a-f0-9-]{36})", custom, re.IGNORECASE)
    if m:
        return m.group(1)

    return None

def _normalize_event(event: str) -> str:
    e = str(event or "").strip().lower().replace(" ", "_")

    # Best / most useful statuses
    if e in ("clicked", "click"):
        return "CLICKED"

    if e in ("unique_opened", "opened", "open", "first_opening"):
        return "OPENED"

    if e in ("delivered", "delivery"):
        return "DELIVERED"

    if e in ("sent", "request"):
        return "SENT"

    # Problem statuses
    if e in ("hard_bounced", "hard_bounce"):
        return "HARD_BOUNCED"

    if e in ("soft_bounced", "soft_bounce", "deferred"):
        return "SOFT_BOUNCED"

    if e in ("blocked", "invalid", "error"):
        return "FAILED"

    if e in ("complaint", "spam"):
        return "SPAM_COMPLAINT"

    if e in ("unsubscribed", "unsubscribe"):
        return "UNSUBSCRIBED"

    # Privacy/proxy opens are not real human opens
    if e in ("loaded_by_proxy", "proxy_open"):
        return "AUTO_OPENED"

    return e.upper()

@router.post("/brevo")
async def brevo_webhook(request: Request):
    payload = await request.json()

    doc_id = _extract_doc_id(payload)

    if not doc_id:
        return {"ok": True, "ignored": True}

    event = _normalize_event(payload.get("event"))
    recipient_email = str(payload.get("email") or "").strip().lower() or None

    with SessionLocal() as db:
        db.execute(
            text(
                """
                INSERT INTO public.email_events (
                    doc_id,
                    brevo_message_id,
                    recipient_email,
                    event,
                    subject,
                    mirror_link,
                    link_clicked,
                    raw_payload,
                    created_at
                )
                VALUES (
                    :doc_id,
                    :brevo_message_id,
                    :recipient_email,
                    :event,
                    :subject,
                    :mirror_link,
                    :link_clicked,
                    CAST(:raw_payload AS jsonb),
                    now()
                )
                """
            ),
            {
                "doc_id": doc_id,
                "brevo_message_id": payload.get("message-id"),
                "recipient_email": recipient_email,
                "event": event,
                "subject": payload.get("subject"),
                "mirror_link": payload.get("mirror_link"),
                "link_clicked": payload.get("link"),
                "raw_payload": json.dumps(payload),
            },
        )
        db.commit()

    return {"ok": True}