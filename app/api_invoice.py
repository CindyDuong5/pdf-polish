# app/api_invoice.py
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.db import SessionLocal
from app.storage.s3_storage import get_storage
from app.buildops_client import BuildOpsClient
from app.styling.invoice.build_data import build_invoice_pdf_data_from_number
from app.styling.invoice.renderer import render_invoice_styled_draft
from app.services.payment_link import get_invoice_payment_link  # ✅ add

router = APIRouter(tags=["invoice"])


class BuildInvoiceIn(BaseModel):
    invoice_number: str


def _styled_draft_key_for(doc_id: str) -> str:
    d = datetime.now(timezone.utc).date().isoformat()
    return f"styled_draft/{d}/{doc_id}.pdf"


def _final_key_for(doc_id: str) -> str:
    d = datetime.now(timezone.utc).date().isoformat()
    return f"final/{d}/{doc_id}.pdf"


def _property_address_text(fields: dict) -> str | None:
    lines = fields.get("property_address_lines") or []
    joined = "\n".join([str(x).strip() for x in lines if str(x).strip()])
    return joined.strip() or None


def _safe_get_buildops_invoice_id(normalized: dict) -> str | None:
    # prefer explicit fields
    for k in ("buildops_invoice_id", "invoice_id", "id"):
        v = normalized.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


@router.post("/api/invoices/build")
def build_invoice_from_number(body: BuildInvoiceIn):
    inv_num = (body.invoice_number or "").strip()
    if not inv_num:
        raise HTTPException(status_code=400, detail="invoice_number required")

    bo = BuildOpsClient()
    normalized = build_invoice_pdf_data_from_number(bo, inv_num)

    # ✅ fetch payment link NOW so UI can show it
    payment_url = None
    try:
        buildops_invoice_id = _safe_get_buildops_invoice_id(normalized)
        if buildops_invoice_id:
            payment_url = get_invoice_payment_link(buildops_invoice_id)
    except Exception:
        payment_url = None  # do not block invoice generation

    if payment_url:
        normalized["payment_url"] = payment_url  # ✅ store in fields

    doc_id = str(uuid4())
    storage = get_storage()

    logo_path = os.getenv("MAINLINE_LOGO_PATH") or os.getenv("INVOICE_LOGO_PATH")

    pdf_bytes = render_invoice_styled_draft(
        normalized,
        logo_path=logo_path,
    )

    draft_key = _styled_draft_key_for(doc_id)
    storage.upload_pdf_bytes(draft_key, pdf_bytes)

    bill_email = (normalized.get("billClient_email") or normalized.get("client_email") or "").strip() or None
    bill_name = (normalized.get("billClient_name") or "").strip() or None
    prop_addr = _property_address_text(normalized)

    with SessionLocal() as db:
        db.execute(
            text(
                """
                INSERT INTO public.documents (
                    id,
                    doc_type,
                    status,
                    customer_name,
                    customer_email,
                    property_address,
                    invoice_number,
                    original_s3_key,
                    styled_draft_s3_key,
                    extracted_fields,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    'INVOICE',
                    'DRAFT',
                    :customer_name,
                    :customer_email,
                    :property_address,
                    :invoice_number,
                    :original_s3_key,
                    :styled_draft_s3_key,
                    CAST(:extracted_fields AS jsonb),
                    now(),
                    now()
                )
                """
            ),
            {
                "id": doc_id,
                "customer_name": bill_name,
                "customer_email": bill_email,
                "property_address": prop_addr,
                "invoice_number": inv_num,
                "original_s3_key": draft_key,
                "styled_draft_s3_key": draft_key,
                "extracted_fields": json.dumps(normalized),
            },
        )
        db.commit()

    url = storage.presign_get_url(
        key=draft_key,
        expires_seconds=3600,
        download_filename=f"INVOICE_{inv_num}.pdf",
        inline=True,
    )

    return {
        "ok": True,
        "doc_id": doc_id,
        "invoice_number": inv_num,
        "styled_draft_s3_key": draft_key,
        "url": url,
        "payment_url": payment_url,  # ✅ return to frontend too
    }


@router.post("/api/documents/{doc_id}/invoice/save-final")
def save_final_invoice(doc_id: str, body: dict = Body(...)):
    fields = body.get("fields")
    if not isinstance(fields, dict):
        raise HTTPException(status_code=400, detail="Missing fields")

    # ✅ keep payment_url if present; if missing, try to refetch
    if not fields.get("payment_url"):
        try:
            buildops_invoice_id = _safe_get_buildops_invoice_id(fields)
            if buildops_invoice_id:
                fields["payment_url"] = get_invoice_payment_link(buildops_invoice_id)
        except Exception:
            pass

    storage = get_storage()
    logo_path = os.getenv("MAINLINE_LOGO_PATH") or os.getenv("INVOICE_LOGO_PATH")

    final_bytes = render_invoice_styled_draft(
        fields,
        logo_path=logo_path,
    )

    fk = _final_key_for(doc_id)
    storage.upload_pdf_bytes(fk, final_bytes)

    bill_email = (fields.get("billClient_email") or fields.get("client_email") or "").strip() or None
    bill_name = (fields.get("billClient_name") or "").strip() or None
    prop_addr = _property_address_text(fields)

    with SessionLocal() as db:
        db.execute(
            text(
                """
                UPDATE public.documents
                SET
                    final_s3_key = :k,
                    status = 'FINALIZED',
                    customer_email = COALESCE(:email, customer_email),
                    customer_name = COALESCE(:name, customer_name),
                    property_address = COALESCE(:addr, property_address),
                    user_overrides = CAST(:fields AS jsonb),
                    updated_at = now(),
                    error = null
                WHERE id = :id
                """
            ),
            {
                "id": doc_id,
                "k": fk,
                "email": bill_email,
                "name": bill_name,
                "addr": prop_addr,
                "fields": json.dumps(fields),
            },
        )
        db.commit()

    return {"ok": True, "final_s3_key": fk, "payment_url": fields.get("payment_url")}


@router.post("/api/documents/{doc_id}/save-final")
def save_final_invoice_alias(doc_id: str, body: dict = Body(...)):
    return save_final_invoice(doc_id, body)