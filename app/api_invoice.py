# app/api_invoice.py
from __future__ import annotations

import json
import os
import requests
from datetime import datetime, timezone
from typing import Optional, List
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.db import SessionLocal
from app.storage.s3_storage import get_storage
from app.buildops_client import BuildOpsClient
from app.email.smtp_sender import send_email_brevo_smtp, EmailAttachment
from app.email.template_router import (
    email_kind_for,
    template_for_kind,
    render_html,
    build_subject,
)
from app.services.payment_link import get_invoice_payment_link
from app.services.additional_documents import (
    list_additional_documents,
    build_additional_email_attachments,
)
from app.styling.invoice.build_data import build_invoice_pdf_data_from_number
from app.styling.invoice.renderer import render_invoice_styled_draft

router = APIRouter(tags=["invoice"])


class BuildInvoiceIn(BaseModel):
    invoice_number: str


class SendInvoiceEmailIn(BaseModel):
    # accept both (frontend uses `to` + `cc`)
    to_email: Optional[str] = None
    to: Optional[str] = None

    cc_emails: Optional[List[str]] = None
    cc: Optional[List[str]] = None
    bcc_emails: Optional[List[str]] = None
    bcc: Optional[List[str]] = None

    subject: Optional[str] = None

class GetPaymentLinkIn(BaseModel):
    force_over_limit: bool = False


def _parse_money(v) -> float:
    s = str(v or "").strip()
    if not s:
        return 0.0
    cleaned = "".join(ch for ch in s if ch.isdigit() or ch in ".-")
    try:
        return float(cleaned)
    except Exception:
        return 0.0


def _invoice_total_amount(fields: dict) -> float:
    if not isinstance(fields, dict):
        return 0.0
    for key in ("total", "invoice_total", "amount_due", "balance"):
        if key in fields:
            amt = _parse_money(fields.get(key))
            if amt:
                return amt
    return 0.0


def _styled_draft_key_for(doc_id: str) -> str:
    d = datetime.now(timezone.utc).date().isoformat()
    return f"styled_draft/invoices/{d}/{doc_id}.pdf"


def _final_key_for(doc_id: str) -> str:
    d = datetime.now(timezone.utc).date().isoformat()
    return f"final/invoices/{d}/{doc_id}.pdf"


def _property_address_text(fields: dict) -> str | None:
    lines = fields.get("property_address_lines") or []
    joined = "\n".join([str(x).strip() for x in lines if str(x).strip()])
    return joined.strip() or None


def _safe_get_buildops_invoice_id(fields: dict) -> str | None:
    for k in ("buildops_invoice_id", "invoice_id", "id"):
        v = fields.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _best_fields(row: dict) -> dict:
    uo = row.get("user_overrides") or {}
    ex = row.get("extracted_fields") or {}
    if isinstance(uo, dict) and uo:
        return uo
    return ex if isinstance(ex, dict) else {}


def _find_existing_active_invoice(db, buildops_invoice_id: str | None, invoice_number: str | None):
    if buildops_invoice_id:
        row = db.execute(
            text(
                """
                SELECT *
                FROM public.documents
                WHERE doc_type = 'INVOICE'
                  AND status <> 'REPLACED'
                  AND (
                    extracted_fields->>'buildops_invoice_id' = :boid
                    OR user_overrides->>'buildops_invoice_id' = :boid
                  )
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"boid": buildops_invoice_id},
        ).mappings().first()
        if row:
            return dict(row)

    if invoice_number:
        row = db.execute(
            text(
                """
                SELECT *
                FROM public.documents
                WHERE doc_type = 'INVOICE'
                  AND status <> 'REPLACED'
                  AND invoice_number = :invoice_number
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"invoice_number": invoice_number},
        ).mappings().first()
        if row:
            return dict(row)

    return None


@router.post("/api/invoices/{doc_id}/payment-link")
def create_invoice_payment_link(
    doc_id: str,
    body: GetPaymentLinkIn = Body(default=GetPaymentLinkIn()),
):
    with SessionLocal() as db:
        row = db.execute(
            text("SELECT * FROM public.documents WHERE id = :id"),
            {"id": doc_id},
        ).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

        row = dict(row)

        if (row.get("status") or "").upper() == "REPLACED":
            raise HTTPException(
                status_code=409,
                detail="This invoice has been replaced by a newer version.",
            )

        fields = _best_fields(row)

        doc_type = (row.get("doc_type") or "").upper()
        if "INVOICE" not in doc_type:
            raise HTTPException(
                status_code=409,
                detail=f"Not an invoice document (doc_type={row.get('doc_type')})",
            )

        total_amount = _invoice_total_amount(fields)
        if total_amount > 5000 and not body.force_over_limit:
            raise HTTPException(
                status_code=409,
                detail=f"Invoice total ${total_amount:,.2f} is over $5,000. Confirmation required.",
            )

        buildops_invoice_id = _safe_get_buildops_invoice_id(fields)
        if not buildops_invoice_id:
            raise HTTPException(status_code=400, detail="Missing BuildOps invoice id")

        try:
            payment_url = get_invoice_payment_link(buildops_invoice_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get payment link: {e}")

        merged_fields = dict(fields)
        merged_fields["payment_url"] = payment_url

        db.execute(
            text(
                """
                UPDATE public.documents
                SET
                    user_overrides = CAST(:fields AS jsonb),
                    updated_at = now(),
                    error = null
                WHERE id = :id
                """
            ),
            {"id": doc_id, "fields": json.dumps(merged_fields)},
        )
        db.commit()

        return {
            "ok": True,
            "doc_id": doc_id,
            "payment_url": payment_url,
            "total_amount": total_amount,
            "forced": bool(body.force_over_limit and total_amount > 5000),
        }


@router.post("/api/invoices/build")
def build_invoice_from_number(body: BuildInvoiceIn):
    inv_num = (body.invoice_number or "").strip()
    if not inv_num:
        raise HTTPException(status_code=400, detail="invoice_number required")

    bo = BuildOpsClient()
    normalized = build_invoice_pdf_data_from_number(bo, inv_num)

    normalized_invoice_number = (normalized.get("invoice_number") or inv_num or "").strip()
    buildops_invoice_id = _safe_get_buildops_invoice_id(normalized)

    doc_id = str(uuid4())
    storage = get_storage()

    logo_path = os.getenv("MAINLINE_LOGO_PATH") or os.getenv("INVOICE_LOGO_PATH")
    pdf_bytes = render_invoice_styled_draft(normalized, logo_path=logo_path)

    draft_key = _styled_draft_key_for(doc_id)
    storage.upload_pdf_bytes(draft_key, pdf_bytes)

    bill_email = (normalized.get("billClient_email") or normalized.get("client_email") or "").strip() or None
    bill_name = (normalized.get("billClient_name") or "").strip() or None
    prop_addr = _property_address_text(normalized)

    with SessionLocal() as db:
        old_row = _find_existing_active_invoice(db, buildops_invoice_id, normalized_invoice_number)

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
                "invoice_number": normalized_invoice_number,
                "original_s3_key": draft_key,
                "styled_draft_s3_key": draft_key,
                "extracted_fields": json.dumps(normalized),
            },
        )

        if old_row:
            db.execute(
                text(
                    """
                    UPDATE public.documents
                    SET
                        status = 'REPLACED',
                        updated_at = now()
                    WHERE id = :old_id
                    """
                ),
                {"old_id": old_row["id"]},
            )

        db.commit()

    url = storage.presign_get_url(
        key=draft_key,
        expires_seconds=3600,
        download_filename=f"INVOICE_{normalized_invoice_number}.pdf",
        inline=True,
    )

    return {
        "ok": True,
        "doc_id": doc_id,
        "invoice_number": normalized_invoice_number,
        "styled_draft_s3_key": draft_key,
        "url": url,
        "payment_url": normalized.get("payment_url"),
    }


@router.post("/api/documents/{doc_id}/invoice/save-final")
def save_final_invoice(doc_id: str, body: dict = Body(...)):
    fields = body.get("fields")
    if not isinstance(fields, dict):
        raise HTTPException(status_code=400, detail="Missing fields")

    with SessionLocal() as db:
        doc = db.execute(
            text("SELECT id, doc_type, customer_email, status FROM public.documents WHERE id=:id"),
            {"id": doc_id},
        ).mappings().first()

        if not doc:
            raise HTTPException(status_code=404, detail="Not found")

        dt = (doc.get("doc_type") or "").upper()
        if "INVOICE" not in dt:
            raise HTTPException(
                status_code=409,
                detail=f"Not an invoice document (doc_type={doc.get('doc_type')})",
            )

        if (doc.get("status") or "").upper() == "REPLACED":
            raise HTTPException(
                status_code=409,
                detail="This invoice has been replaced by a newer version.",
            )

    storage = get_storage()
    logo_path = os.getenv("MAINLINE_LOGO_PATH") or os.getenv("INVOICE_LOGO_PATH")
    final_bytes = render_invoice_styled_draft(fields, logo_path=logo_path)

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


@router.post("/api/documents/{doc_id}/invoice/send")
def send_final_invoice_email(doc_id: str, body: SendInvoiceEmailIn):
    storage = get_storage()

    with SessionLocal() as db:
        row = db.execute(
            text("SELECT * FROM public.documents WHERE id = :id"),
            {"id": doc_id},
        ).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

        row = dict(row)

        if (row.get("status") or "").upper() == "REPLACED":
            raise HTTPException(
                status_code=409,
                detail="This invoice has been replaced by a newer version.",
            )

        fields = _best_fields(row)

        final_key = row.get("final_s3_key")
        if not final_key:
            raise HTTPException(
                status_code=400,
                detail="Invoice not finalized yet. Please Save Final first.",
            )

        invoice_number = (row.get("invoice_number") or fields.get("invoice_number") or "").strip()
        customer_name = (row.get("customer_name") or fields.get("billClient_name") or "Customer").strip()
        property_address = row.get("property_address") or _property_address_text(fields)
        payment_url = fields.get("payment_url")

        to_email = (
            (body.to_email or body.to)
            or row.get("customer_email")
            or fields.get("billClient_email")
            or ""
        ).strip()
        if not to_email:
            raise HTTPException(
                status_code=400,
                detail="Missing to_email (and no customer_email on document)",
            )

        cc = body.cc_emails or body.cc or []
        cc = [e.strip() for e in cc if isinstance(e, str) and e.strip()]

        bcc = body.bcc_emails or body.bcc or []
        bcc = [e.strip() for e in bcc if isinstance(e, str) and e.strip()]

        view_url = storage.public_url(final_key)

        try:
            pdf_bytes = storage.download_bytes(final_key)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to download PDF for attachment: {e}",
            )

        additional_docs = list_additional_documents(db, doc_id)
        additional_attachments = build_additional_email_attachments(db, storage, doc_id)
        additional_document_names = [str(x.get("display_name") or "").strip() for x in additional_docs if str(x.get("display_name") or "").strip()]
        
        kind = email_kind_for("INVOICE")
        tpl = template_for_kind(kind)

        default_subject = build_subject(kind, "INVOICE", invoice_number or doc_id)
        subject = (body.subject or "").strip() or default_subject

        html = render_html(
            tpl,
            {
                "invoice_number": invoice_number or "",
                "customer_name": customer_name,
                "property_address": property_address or "",
                "view_url": view_url,
                "payment_url": payment_url or "",
                "additional_document_names": additional_document_names,
            },
        )

        text_body = f"Invoice #{invoice_number}\nView: {view_url}\n"

        if additional_document_names:
            text_body += "\nAdditional Documents:\n"
            for name in additional_document_names:
                text_body += f"- {name}\n"

        if payment_url:
            text_body += f"\nPay by Credit Card: {payment_url}\n"

        send_email_brevo_smtp(
            to_email=to_email,
            subject=subject,
            html_body=html,
            text_body=text_body,
            cc_emails=cc,
            bcc_emails=bcc,
            attachments=(
                EmailAttachment(
                    filename=f"Invoice-{invoice_number or doc_id}.pdf",
                    content_type="application/pdf",
                    data=pdf_bytes,
                ),
                *additional_attachments,
            ),
            from_value=os.getenv(
                "EMAIL_FROM",
                "Mainline Fire Protection <support@mainlinefire.com>",
            ),
            reply_to=os.getenv(
                "EMAIL_REPLY_TO",
                "support@mainlinefire.com",
            ),
        )
        sent_cc = ", ".join(cc) if cc else None
        sent_bcc = ", ".join(bcc) if bcc else None
        db.execute(
            text(
                """
                UPDATE public.documents
                SET
                    sent_to = :to_email,
                    sent_cc = :sent_cc,
                    sent_bcc = :sent_bcc,
                    sent_at = now(),
                    updated_at = now(),
                    error = null,
                    status = 'SENT'
                WHERE id = :id
                """
            ),
            {"id": doc_id, "to_email": to_email, "sent_cc": sent_cc, "sent_bcc": sent_bcc},
        )
        db.commit()

    return {
        "ok": True,
        "to": to_email,
        "cc": cc,
        "bcc": bcc,
        "view_url": view_url,
        "payment_url": payment_url,
        "subject": subject,
    }