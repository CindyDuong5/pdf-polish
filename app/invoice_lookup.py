# app/invoice_lookup.py
from __future__ import annotations

import os
import requests
from typing import Any, Dict


INVOICE_ID_LOOKUP_URL = os.getenv(
    "INVOICE_ID_LOOKUP_URL",
    "https://getinvoiceid-722522316664.northamerica-northeast2.run.app",
).rstrip("/")

INVOICE_ID_LOOKUP_API_KEY = os.getenv("INVOICE_ID_LOOKUP_API_KEY", "")


def _extract_id(payload: Dict[str, Any]) -> str:
    """
    Accept a few possible response shapes.
    """
    # Shape A: {"id": "..."}
    if payload.get("id"):
        return str(payload["id"]).strip()

    # Shape B: {"invoice_id": "..."} or {"invoiceId": "..."}
    if payload.get("invoice_id"):
        return str(payload["invoice_id"]).strip()
    if payload.get("invoiceId"):
        return str(payload["invoiceId"]).strip()

    # Shape C: {"data": {"id": "..."}}
    data = payload.get("data")
    if isinstance(data, dict) and data.get("id"):
        return str(data["id"]).strip()

    return ""


def get_invoice_id_by_number(invoice_number: str) -> str:
    invoice_number = str(invoice_number).strip()
    if not invoice_number:
        raise ValueError("invoice_number is required")

    if not INVOICE_ID_LOOKUP_API_KEY:
        raise RuntimeError("Missing INVOICE_ID_LOOKUP_API_KEY env var")

    r = requests.post(
        INVOICE_ID_LOOKUP_URL,
        headers={
            "X-API-Key": INVOICE_ID_LOOKUP_API_KEY,
            "Content-Type": "application/json",
        },
        json={"invoice_number": invoice_number},
        timeout=20,
    )

    # If your service returns non-2xx, show the body
    if not (200 <= r.status_code < 300):
        raise RuntimeError(f"Lookup service HTTP {r.status_code}: {r.text}")

    try:
        payload = r.json()
    except Exception:
        raise RuntimeError(f"Lookup service returned non-JSON: {r.text}")

    inv_id = _extract_id(payload)

    if not inv_id:
        # SUPER IMPORTANT: show exactly what came back
        raise RuntimeError(
            "Lookup service returned no invoice id.\n"
            f"invoice_number={invoice_number}\n"
            f"response_json={payload}"
        )

    return inv_id