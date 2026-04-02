# app/api_invoice.py
from __future__ import annotations

import json
import os
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
from app.services.snowflake import resolve_invoice_recipient_suggestion
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
    return f"styled_draft/invoices/{doc_id}.pdf"


def _final_key_for(doc_id: str) -> str:
    now = datetime.now(timezone.utc)
    d = now.date().isoformat()
    stamp = now.strftime("%Y%m%d%H%M%S")
    return f"final/invoices/{d}/{doc_id}-{stamp}.pdf"


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


def _safe_get_property_id(fields: dict) -> str | None:
    for k in ("customerPropertyId", "property_id", "propertyId"):
        v = fields.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _safe_get_customer_id(fields: dict) -> str | None:
    for k in ("billingCustomerId", "billing_customer_id", "customer_id", "customerId"):
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


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def _unique_emails(items: List[str] | None) -> List[str]:
    out: List[str] = []
    seen = set()

    for raw in items or []:
        email = _normalize_email(raw)
        if not email:
            continue
        if email in seen:
            continue
        seen.add(email)
        out.append(email)

    return out


def _get_invoice_recipient_resolution(fields: dict) -> dict:
    property_id = _safe_get_property_id(fields)
    customer_id = _safe_get_customer_id(fields)
    fallback_email = _normalize_email(fields.get("billClient_email") or fields.get("client_email"))

    try:
        rec = resolve_invoice_recipient_suggestion(
            property_id=property_id,
            customer_id=customer_id,
            primary_email=None,  # do not let Snowflake resolver auto-use bill client fallback
        ) or {}

        to_email = _normalize_email(rec.get("to"))
        cc_emails = _unique_emails(rec.get("cc") or [])
        all_emails = _unique_emails(rec.get("all_emails") or [])
        items = rec.get("items") or []
        source = (rec.get("source") or "").strip()
        property_result = rec.get("property_result") or {}
        customer_result = rec.get("customer_result") or {}

        if to_email:
            if source == "property":
                message = "Recipient auto-selected from Snowflake Property contacts."
            elif source == "customer":
                message = "Recipient auto-selected from Snowflake Customer contacts."
            else:
                message = "Recipient auto-selected from Snowflake contacts."

            return {
                "property_id": property_id,
                "customer_id": customer_id,
                "to": to_email,
                "cc": cc_emails,
                "all_emails": _unique_emails([to_email, *cc_emails, *all_emails]),
                "items": items,
                "source": source or "property",
                "message": message,
                "property_result": property_result,
                "customer_result": customer_result,
            }

        if fallback_email:
            return {
                "property_id": property_id,
                "customer_id": customer_id,
                "to": fallback_email,
                "cc": [],
                "all_emails": [fallback_email],
                "items": [
                    {
                        "email": fallback_email,
                        "full_name": fields.get("billClient_name") or "",
                        "role": "bill_client_email",
                        "source": "bill_client",
                        "selected": True,
                    }
                ],
                "source": "bill_client",
                "message": "No Snowflake billing contact found. Using Bill Client Email as fallback.",
                "property_result": property_result,
                "customer_result": customer_result,
            }

        return {
            "property_id": property_id,
            "customer_id": customer_id,
            "to": "",
            "cc": [],
            "all_emails": [],
            "items": [],
            "source": "manual",
            "message": "No billing contact found in Snowflake and no Bill Client Email is available. Please manually enter the email address.",
            "property_result": property_result,
            "customer_result": customer_result,
        }

    except Exception:
        if fallback_email:
            return {
                "property_id": property_id,
                "customer_id": customer_id,
                "to": fallback_email,
                "cc": [],
                "all_emails": [fallback_email],
                "items": [
                    {
                        "email": fallback_email,
                        "full_name": fields.get("billClient_name") or "",
                        "role": "bill_client_email",
                        "source": "bill_client",
                        "selected": True,
                    }
                ],
                "source": "bill_client",
                "message": "Snowflake lookup failed. Using Bill Client Email as fallback.",
                "property_result": {},
                "customer_result": {},
            }

        return {
            "property_id": property_id,
            "customer_id": customer_id,
            "to": "",
            "cc": [],
            "all_emails": [],
            "items": [],
            "source": "snowflake_error",
            "message": "Unable to retrieve billing contacts from Snowflake. Please manually enter the email address to send the invoice to.",
            "property_result": {},
            "customer_result": {},
        }


def _apply_recipient_fields(fields: dict) -> dict:
    rec = _get_invoice_recipient_resolution(fields)

    fields["property_id"] = rec.get("property_id")
    fields["customer_id"] = rec.get("customer_id")

    fields["invoice_recipient_to"] = rec.get("to") or ""
    fields["invoice_recipient_cc"] = rec.get("cc") or []
    fields["invoice_recipient_all_emails"] = rec.get("all_emails") or []

    # keep old keys too so existing frontend does not break
    fields["property_rep_to"] = rec.get("to") or ""
    fields["property_rep_cc"] = rec.get("cc") or []
    fields["property_rep_all_emails"] = rec.get("all_emails") or []

    fields["recipient_source"] = rec.get("source") or ""
    fields["recipient_message"] = rec.get("message") or ""
    fields["recipient_items"] = rec.get("items") or []
    fields["property_recipient_result"] = rec.get("property_result") or {}
    fields["customer_recipient_result"] = rec.get("customer_result") or {}

    return rec


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
    normalized["hide_labor"] = bool(normalized.get("hide_labor", False))
    normalized["hide_parts"] = bool(normalized.get("hide_parts", False))

    recipient_info = _apply_recipient_fields(normalized)

    normalized_invoice_number = (normalized.get("invoice_number") or inv_num or "").strip()
    buildops_invoice_id = _safe_get_buildops_invoice_id(normalized)

    doc_id = str(uuid4())
    storage = get_storage()

    logo_path = os.getenv("MAINLINE_LOGO_PATH") or os.getenv("INVOICE_LOGO_PATH")
    pdf_bytes = render_invoice_styled_draft(normalized, logo_path=logo_path)

    draft_key = _styled_draft_key_for(doc_id)
    storage.upload_pdf_bytes(draft_key, pdf_bytes)

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
                "customer_email": None,
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
        "property_id": normalized.get("property_id"),
        "customer_id": normalized.get("customer_id"),
        "invoice_recipient_to": normalized.get("invoice_recipient_to"),
        "invoice_recipient_cc": normalized.get("invoice_recipient_cc") or [],
        "property_rep_to": normalized.get("property_rep_to"),
        "property_rep_cc": normalized.get("property_rep_cc") or [],
        "recipient_source": normalized.get("recipient_source"),
        "recipient_message": normalized.get("recipient_message"),
    }


@router.post("/api/documents/{doc_id}/invoice/save-final")
def save_final_invoice(doc_id: str, body: dict = Body(...)):
    fields = body.get("fields")
    if not isinstance(fields, dict):
        raise HTTPException(status_code=400, detail="Missing fields")

    fields["hide_labor"] = bool(fields.get("hide_labor", False))
    fields["hide_parts"] = bool(fields.get("hide_parts", False))

    _apply_recipient_fields(fields)

    with SessionLocal() as db:
        doc = db.execute(
            text(
                """
                SELECT id, doc_type, customer_email, status, final_s3_key
                FROM public.documents
                WHERE id = :id
                """
            ),
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

        old_final_key = doc.get("final_s3_key")

    storage = get_storage()
    logo_path = os.getenv("MAINLINE_LOGO_PATH") or os.getenv("INVOICE_LOGO_PATH")
    final_bytes = render_invoice_styled_draft(fields, logo_path=logo_path)

    fk = _final_key_for(doc_id)
    storage.upload_pdf_bytes(fk, final_bytes)

    bill_name = (fields.get("billClient_name") or "").strip() or None
    prop_addr = _property_address_text(fields)

    try:
        with SessionLocal() as db:
            db.execute(
                text(
                    """
                    UPDATE public.documents
                    SET
                        final_s3_key = :k,
                        status = 'FINALIZED',
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
                    "name": bill_name,
                    "addr": prop_addr,
                    "fields": json.dumps(fields),
                },
            )
            db.commit()
    except Exception:
        try:
            storage.delete_object(fk)
        except Exception:
            pass
        raise

    if old_final_key and old_final_key != fk:
        try:
            storage.delete_object(old_final_key)
        except Exception:
            pass

    return {
        "ok": True,
        "final_s3_key": fk,
        "payment_url": fields.get("payment_url"),
        "property_id": fields.get("property_id"),
        "customer_id": fields.get("customer_id"),
        "invoice_recipient_to": fields.get("invoice_recipient_to"),
        "invoice_recipient_cc": fields.get("invoice_recipient_cc") or [],
        "property_rep_to": fields.get("property_rep_to"),
        "property_rep_cc": fields.get("property_rep_cc") or [],
        "recipient_source": fields.get("recipient_source"),
        "recipient_message": fields.get("recipient_message"),
    }


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
        recipient_info = _apply_recipient_fields(fields)

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

        default_to = _normalize_email(
            fields.get("invoice_recipient_to")
            or fields.get("property_rep_to")
            or recipient_info.get("to")
        )

        to_email = _normalize_email((body.to_email or body.to) or default_to)
        if not to_email:
            raise HTTPException(
                status_code=400,
                detail=fields.get("recipient_message")
                or "No billing contact found under Property level or Customer level. Please manually enter the email address to send the invoice to.",
            )

        default_cc = _unique_emails(
            fields.get("invoice_recipient_cc")
            or fields.get("property_rep_cc")
            or recipient_info.get("cc")
            or []
        )

        body_cc = body.cc_emails or body.cc or []
        cc = _unique_emails(body_cc if body_cc else default_cc)
        cc = [e for e in cc if e != to_email]

        bcc = body.bcc_emails or body.bcc or []
        bcc = _unique_emails(bcc)
        bcc = [e for e in bcc if e != to_email and e not in cc]

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
        additional_document_names = [
            str(x.get("display_name") or "").strip()
            for x in additional_docs
            if str(x.get("display_name") or "").strip()
        ]

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
                    status = 'SENT',
                    user_overrides = CAST(:fields AS jsonb)
                WHERE id = :id
                """
            ),
            {
                "id": doc_id,
                "to_email": to_email,
                "sent_cc": sent_cc,
                "sent_bcc": sent_bcc,
                "fields": json.dumps(fields),
            },
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
        "property_id": fields.get("property_id"),
        "customer_id": fields.get("customer_id"),
        "invoice_recipient_to": fields.get("invoice_recipient_to"),
        "invoice_recipient_cc": fields.get("invoice_recipient_cc") or [],
        "property_rep_to": fields.get("property_rep_to"),
        "property_rep_cc": fields.get("property_rep_cc") or [],
        "recipient_source": fields.get("recipient_source"),
        "recipient_message": fields.get("recipient_message"),
    }

@router.get("/debug/snowflake")
def debug_snowflake():
    try:
        from app.services.snowflake import get_connection

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE()")
        row = cur.fetchone()

        return {
            "ok": True,
            "user": row[0],
            "role": row[1],
            "warehouse": row[2],
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }