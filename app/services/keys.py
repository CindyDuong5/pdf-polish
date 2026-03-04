# app/services/keys.py
from __future__ import annotations
from datetime import datetime, timezone


def utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def day_from_key(key: str | None) -> str:
    # expected: original/YYYY-MM-DD/<uuid>.pdf
    if not key:
        return utc_day()
    parts = key.split("/")
    if len(parts) >= 3 and parts[1]:
        return parts[1]
    return utc_day()


def styled_draft_key(original_key: str, doc_id: str) -> str:
    day = day_from_key(original_key)
    return f"styled_draft/{day}/{doc_id}.pdf"


# --- NEW: namespaced final key ---
def final_key_for(original_key: str, doc_id: str, doc_type: str) -> str:
    day = day_from_key(original_key)
    dt = (doc_type or "").upper()

    if "INVOICE" in dt:
        folder = "invoices"
    elif "SERVICE_QUOTE" in dt or "PROJECT_QUOTE" in dt or "QUOTE" in dt:
        folder = "quotes"
    elif "JOB_REPORT" in dt or "JOB" in dt or "REPORT" in dt:
        folder = "job_reports"
    else:
        folder = "other"

    return f"final/{folder}/{day}/{doc_id}.pdf"


# --- OLD: keep for now (optional) ---
def final_key(original_key: str, doc_id: str) -> str:
    day = day_from_key(original_key)
    return f"final/{day}/{doc_id}.pdf"