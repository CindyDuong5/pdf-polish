# app/services/payment_link.py
from __future__ import annotations

import os
import requests
from typing import Any, Dict, Optional


def get_invoice_payment_link(buildops_invoice_id: str) -> str:
    """
    Calls your WP endpoint to create/get a payment link token for an invoice.

    Env vars required:
      - PAYMENT_LINK_ENDPOINT  (default: your wp-json endpoint)
      - PAYMENT_LINK_API_KEY   (x-api-key value)

    Returns: payment URL as a string.
    Raises: RuntimeError on failure.
    """
    invoice_id = (buildops_invoice_id or "").strip()
    if not invoice_id:
        raise RuntimeError("Missing buildops_invoice_id")

    endpoint = os.getenv("PAYMENT_LINK_ENDPOINT") or "https://28l.dbb.myftpupload.com/wp-json/buildops/v1/token"
    api_key = os.getenv("PAYMENT_LINK_API_KEY")
    if not api_key:
        raise RuntimeError("Missing PAYMENT_LINK_API_KEY")

    r = requests.post(
        endpoint,
        headers={"Content-Type": "application/json", "x-api-key": api_key},
        json={"invoice_id": invoice_id},
        timeout=20,
    )

    if r.status_code >= 400:
        raise RuntimeError(f"Payment link API failed: {r.status_code} {r.text[:500]}")

    data: Dict[str, Any] = r.json() if r.text else {}

    # ✅ Be flexible about response shape
    # Common possibilities: {"url": "..."} or {"payment_url":"..."} or {"token":"...","url":"..."}
    for k in ("url", "payment_url", "paymentUrl", "link"):
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    # If it only returns token, you can build URL here if you know the pattern.
    token = data.get("token")
    if isinstance(token, str) and token.strip():
        # If your site has a known payment page URL pattern, set PAYMENT_LINK_BASE_URL
        base = (os.getenv("PAYMENT_LINK_BASE_URL") or "").rstrip("/")
        if base:
            return f"{base}/{token.strip()}"

        raise RuntimeError("Payment API returned token but no URL. Set PAYMENT_LINK_BASE_URL or return url from API.")

    raise RuntimeError(f"Payment API response missing url/token. Got keys={list(data.keys())}")