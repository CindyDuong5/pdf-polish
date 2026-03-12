# app/api_main.py
from __future__ import annotations

import os

from pathlib import Path
from typing import Literal, List, Optional

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy import text

from app.db import SessionLocal
from app.email.smtp_sender import EmailAttachment, send_email_brevo_smtp
from app.email.template_router import build_subject, email_kind_for, render_html, template_for_kind
from app.security.quote_response_token import make_token, verify_token
from app.services.document_fields import get_fields, set_final
from app.services.keys import final_key_for
from app.services.pdf_stamp import stamp_pdf
from app.services.styling_service import ensure_draft, _mark_older_quote_rows_replaced
from app.services.service_quote_editor import json_to_service_quote, normalize_service_quote_fields
from app.storage.s3_storage import get_storage
from app.styling.service_quote.renderer import render_service_quote
from app.api_invoice import router as invoice_router
from app.services.payment_link import get_invoice_payment_link

app = FastAPI(title="PDF Polish API")

app.include_router(invoice_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://pdf-polish-frontend-722522316664.northamerica-northeast1.run.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"ok": True, "try": ["/docs", "/api/health", "/api/documents"]}


@app.get("/api/health")
def health():
    return {"ok": True}


def _is_replace_blocked_doc(doc_type: str | None) -> bool:
    dt = (doc_type or "").upper()
    return ("INVOICE" in dt) or ("SERVICE_QUOTE" in dt) or ("PROJECT_QUOTE" in dt) or ("QUOTE" in dt)


def _block_replaced_document(
    row: dict,
    detail: str = "This document has been replaced by a newer version.",
):
    dt = (row.get("doc_type") or "").upper()
    status = (row.get("status") or "").upper()

    if _is_replace_blocked_doc(dt) and status == "REPLACED":
        raise HTTPException(status_code=409, detail=detail)


@app.get("/api/documents")
def list_documents(
    q: str | None = None,
    doc_type: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    where = []
    params: dict = {"limit": limit}

    if doc_type:
        where.append("doc_type = :doc_type")
        params["doc_type"] = doc_type

    if status:
        where.append("status = :status")
        params["status"] = status
    else:
        where.append("COALESCE(status, '') <> 'REPLACED'")

    if q:
        where.append(
            "("
            "invoice_number ilike '%' || :q || '%' OR "
            "quote_number ilike '%' || :q || '%' OR "
            "job_report_number ilike '%' || :q || '%' OR "
            "customer_name ilike '%' || :q || '%' OR "
            "property_address ilike '%' || :q || '%'"
            ")"
        )
        params["q"] = q

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    sql = text(
        f"""
        SELECT
          id,
          doc_type,
          status,
          customer_name,
          customer_email,
          property_address,
          invoice_number,
          quote_number,
          job_report_number,
          original_s3_key,
          styled_draft_s3_key,
          final_s3_key,
          sent_to,
          sent_cc,
          sent_at,
          created_at,
          updated_at,
          quote_po_number,
          quote_note,
          quote_reject_reason,
          quote_responded_at,
          error
        FROM public.documents
        {where_sql}
        ORDER BY created_at DESC
        LIMIT :limit
        """
    )

    with SessionLocal() as db:
        rows = db.execute(sql, params).mappings().all()
        return {"items": [dict(r) for r in rows]}


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str):
    sql = text("SELECT * FROM public.documents WHERE id = :id")
    with SessionLocal() as db:
        row = db.execute(sql, {"id": doc_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        rowd = dict(row)
        _block_replaced_document(rowd)
        return rowd


@app.get("/api/documents/{doc_id}/presign")
def presign_document(
    doc_id: str,
    which: Literal["original", "styled_draft", "final"] = "styled_draft",
    expires_seconds: int = 3600,
):
    sql = text(
        """
        SELECT
          doc_type,
          status,
          invoice_number,
          quote_number,
          job_report_number,
          original_s3_key,
          styled_draft_s3_key,
          final_s3_key
        FROM public.documents
        WHERE id = :id
        """
    )

    with SessionLocal() as db:
        row = db.execute(sql, {"id": doc_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        rowd = dict(row)
        _block_replaced_document(rowd)

        if which == "original":
            key = rowd["original_s3_key"]
        elif which == "final":
            key = rowd["final_s3_key"]
        else:
            key = rowd["styled_draft_s3_key"]

        if not key:
            raise HTTPException(status_code=400, detail=f"No {which} file available yet")

        storage = get_storage()
        label = rowd["invoice_number"] or rowd["quote_number"] or rowd["job_report_number"] or doc_id
        filename = f"{rowd['doc_type']}_{label}.pdf"

        url = storage.presign_get_url(
            key=key,
            expires_seconds=expires_seconds,
            download_filename=filename,
            inline=True,
        )
        return {"url": url, "key": key, "which": which}


@app.get("/api/documents/{doc_id}/links")
def get_document_links(doc_id: str, expires_seconds: int = 3600):
    sql = text(
        """
        SELECT
          id,
          doc_type,
          status,
          invoice_number,
          quote_number,
          job_report_number,
          original_s3_key,
          styled_draft_s3_key,
          final_s3_key
        FROM public.documents
        WHERE id = :id
        """
    )

    with SessionLocal() as db:
        row = db.execute(sql, {"id": doc_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        rowd = dict(row)
        _block_replaced_document(rowd)

        storage = get_storage()
        label = rowd["invoice_number"] or rowd["quote_number"] or rowd["job_report_number"] or rowd["id"]
        filename = f"{rowd['doc_type']}_{label}.pdf"

        def url_for(key: str | None) -> str | None:
            if not key:
                return None
            return storage.presign_get_url(
                key=key,
                expires_seconds=expires_seconds,
                download_filename=filename,
                inline=True,
            )

        return {
            "id": rowd["id"],
            "doc_type": rowd["doc_type"],
            "filename": filename,
            "original": {"key": rowd["original_s3_key"], "url": url_for(rowd["original_s3_key"])},
            "styled_draft": {"key": rowd["styled_draft_s3_key"], "url": url_for(rowd["styled_draft_s3_key"])},
            "final": {"key": rowd["final_s3_key"], "url": url_for(rowd["final_s3_key"])},
        }


@app.post("/api/documents/{doc_id}/finalize")
def finalize_document(
    doc_id: str,
    body: dict = Body(default={"text": "This is final"}),
    force: bool = False,
):
    stamp_text = (body.get("text") or "This is final").strip() or "This is final"
    storage = get_storage()

    with SessionLocal() as db:
        row = db.execute(
            text(
                """
                SELECT id, doc_type, status, original_s3_key, styled_draft_s3_key, final_s3_key
                FROM public.documents
                WHERE id = :id
                """
            ),
            {"id": doc_id},
        ).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        rowd = dict(row)
        _block_replaced_document(rowd)

        if rowd["final_s3_key"] and not force:
            return {
                "ok": True,
                "note": "Final already exists (use force=true to regenerate).",
                "final_s3_key": rowd["final_s3_key"],
            }

        original_key = rowd["original_s3_key"]
        draft_key = rowd["styled_draft_s3_key"]
        if not original_key:
            raise HTTPException(status_code=400, detail="Document missing original_s3_key")

        source_key = draft_key or original_key
        final_key_path = final_key_for(original_key, doc_id)

        db.execute(
            text(
                """
                UPDATE public.documents
                SET status='FINALIZING', updated_at=now(), error=null
                WHERE id=:id
                """
            ),
            {"id": doc_id},
        )
        db.commit()

        try:
            src_bytes = storage.download_bytes(source_key)
            final_bytes = stamp_pdf(src_bytes, stamp_text)
            storage.upload_pdf_bytes(final_key_path, final_bytes)

            db.execute(
                text(
                    """
                    UPDATE public.documents
                    SET final_s3_key=:k,
                        status='FINALIZED',
                        updated_at=now(),
                        error=null
                    WHERE id=:id
                    """
                ),
                {"id": doc_id, "k": final_key_path},
            )
            db.commit()

            return {"ok": True, "final_s3_key": final_key_path, "source_used": source_key}

        except Exception as e:
            db.execute(
                text(
                    """
                    UPDATE public.documents
                    SET status='ERROR', updated_at=now(), error=:err
                    WHERE id=:id
                    """
                ),
                {"id": doc_id, "err": f"{type(e).__name__}: {e}"[:1000]},
            )
            db.commit()
            raise


@app.post("/api/documents/{doc_id}/restyle")
def restyle_document(doc_id: str):
    with SessionLocal() as db:
        row = db.execute(
            text("SELECT id, doc_type, status FROM public.documents WHERE id = :id"),
            {"id": doc_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        _block_replaced_document(dict(row))

        result = ensure_draft(db, doc_id, force=True)
        return {
            "ok": True,
            "doc_id": result["doc_id"],
            "styled_draft_s3_key": result["styled_draft_s3_key"],
            "reused_existing": result["reused_existing"],
        }


@app.get("/api/documents/{doc_id}/fields")
def get_document_fields(doc_id: str):
    with SessionLocal() as db:
        docrow = db.execute(
            text(
                """
                SELECT id, doc_type, status
                FROM public.documents
                WHERE id = :id
                """
            ),
            {"id": doc_id},
        ).mappings().first()

        if not docrow:
            raise HTTPException(status_code=404, detail="Not found")

        _block_replaced_document(dict(docrow))

        row = get_fields(db, doc_id)
        effective_doc_id = doc_id

        if not row:
            result = ensure_draft(db, doc_id, force=False)
            effective_doc_id = result["doc_id"]

            docrow2 = db.execute(
                text(
                    """
                    SELECT id, doc_type, status
                    FROM public.documents
                    WHERE id = :id
                    """
                ),
                {"id": effective_doc_id},
            ).mappings().first()
            if docrow2:
                _block_replaced_document(dict(docrow2))

            row = get_fields(db, effective_doc_id)

        if row:
            rdoc = db.execute(
                text(
                    """
                    SELECT doc_type, status
                    FROM public.documents
                    WHERE id = :id
                    """
                ),
                {"id": effective_doc_id},
            ).mappings().first()

            if rdoc:
                _block_replaced_document(dict(rdoc))

            return {
                "doc_id": effective_doc_id,
                "draft": row.get("draft_json"),
                "final": row.get("final_json"),
                "source": "document_fields",
            }

        r2 = db.execute(
            text(
                """
                SELECT doc_type, status, extracted_fields, user_overrides
                FROM public.documents
                WHERE id = :id
                """
            ),
            {"id": effective_doc_id},
        ).mappings().first()

        if not r2:
            raise HTTPException(status_code=404, detail="Not found")

        r2d = dict(r2)
        _block_replaced_document(r2d)

        extracted = r2d.get("extracted_fields")
        overrides = r2d.get("user_overrides")

        if extracted or overrides:
            return {
                "doc_id": effective_doc_id,
                "draft": extracted,
                "final": overrides,
                "source": "documents_json",
                "doc_type": r2d.get("doc_type"),
            }

        raise HTTPException(status_code=404, detail="No fields available")


@app.post("/api/documents/{doc_id}/save-final")
def save_final(doc_id: str, body: dict = Body(...)):
    fields = body.get("fields")
    if not isinstance(fields, dict):
        raise HTTPException(status_code=400, detail="Missing fields")

    fields = normalize_service_quote_fields(fields)
    storage = get_storage()

    with SessionLocal() as db:
        row = db.execute(
            text("SELECT id, doc_type, status, original_s3_key FROM public.documents WHERE id=:id"),
            {"id": doc_id},
        ).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        rowd = dict(row)
        _block_replaced_document(rowd)

        doc_type = rowd.get("doc_type") or ""
        dt = doc_type.upper()

        if ("SERVICE_QUOTE" not in dt) and ("PROJECT_QUOTE" not in dt) and ("QUOTE" not in dt):
            raise HTTPException(status_code=409, detail=f"Not a quote document (doc_type={doc_type})")

        target_doc_id = str(doc_id)
        original_key = rowd["original_s3_key"]
        if not original_key:
            raise HTTPException(status_code=400, detail="Missing original_s3_key")

        db.execute(
            text(
                """
                UPDATE public.documents
                SET status='FINALIZING', updated_at=now(), error=null
                WHERE id=:id
                """
            ),
            {"id": target_doc_id},
        )
        db.commit()

        try:
            set_final(db, target_doc_id, fields)
            db.commit()

            quote_num = (fields.get("quote_number") or "").strip() or None
            client_email = (fields.get("client_email") or "").strip() or None
            client_name = (fields.get("client_name") or "").strip() or None
            prop_addr = (fields.get("property_address") or "").strip() or None

            db.execute(
                text(
                    """
                    UPDATE public.documents
                    SET customer_email = COALESCE(:customer_email, customer_email),
                        customer_name = COALESCE(:customer_name, customer_name),
                        property_address = COALESCE(:property_address, property_address),
                        quote_number = COALESCE(:quote_number, quote_number),
                        updated_at = now()
                    WHERE id = :id
                    """
                ),
                {
                    "id": target_doc_id,
                    "customer_email": client_email,
                    "customer_name": client_name,
                    "property_address": prop_addr,
                    "quote_number": quote_num,
                },
            )
            db.commit()

            data = json_to_service_quote(fields)

            template_path = Path(
                os.getenv("SERVICE_QUOTE_TEMPLATE_PDF") or "templates/Mainline-Service-Quote.pdf"
            )

            final_bytes = render_service_quote(template_path, data)

            fk = final_key_for(original_key, target_doc_id, doc_type=doc_type)
            storage.upload_pdf_bytes(fk, final_bytes)

            db.execute(
                text(
                    """
                    UPDATE public.documents
                    SET final_s3_key = :k,
                        status = 'FINALIZED',
                        updated_at = now(),
                        error = null
                    WHERE id = :id
                    """
                ),
                {"id": target_doc_id, "k": fk},
            )

            if quote_num:
                _mark_older_quote_rows_replaced(db, quote_num, keep_id=target_doc_id)

            db.commit()

            return {
                "ok": True,
                "doc_id": target_doc_id,
                "final_s3_key": fk,
                "customer_email": client_email,
                "reused_existing": False,
            }

        except Exception as e:
            db.rollback()
            db.execute(
                text(
                    """
                    UPDATE public.documents
                    SET status='ERROR', updated_at=now(), error=:err
                    WHERE id=:id
                    """
                ),
                {"id": target_doc_id, "err": f"{type(e).__name__}: {e}"[:1000]},
            )
            db.commit()
            raise


class SendEmailIn(BaseModel):
    client_email: Optional[EmailStr] = None
    cc: Optional[List[EmailStr]] = None
    bcc: Optional[List[EmailStr]] = None
    deficiency_report_link: Optional[str] = None


def _is_reviewable_quote(doc_type: str) -> bool:
    dt = (doc_type or "").upper()
    return ("SERVICE_QUOTE" in dt) or ("PROJECT_QUOTE" in dt)


def _extract_quote_info(row: dict) -> tuple[str | None, str | None, str | None]:
    final_json = row.get("final_json") or {}

    quote_number = None
    property_name = None
    company_name = None

    if isinstance(final_json, dict):
        quote_number = (final_json.get("quote_number") or "").strip() or None
        property_name = (final_json.get("property_name") or "").strip() or None
        company_name = (final_json.get("company_name") or "").strip() or None

    quote_number = quote_number or (str(row.get("quote_number") or "").strip() or None)
    property_name = property_name or (str(row.get("property_address") or "").strip() or None)

    return quote_number, property_name, company_name


def _display_quote_label(quote_number: str | None, doc_id: str) -> str:
    return (quote_number or "").strip() or doc_id[:8]


def _as_dict_maybe(v):
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return {}
        try:
            import json
            parsed = json.loads(s)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _get_buildops_invoice_id(rowd: dict) -> str | None:
    overrides = _as_dict_maybe(rowd.get("user_overrides"))
    extracted = _as_dict_maybe(rowd.get("extracted_fields"))

    inv_id = (overrides.get("buildops_invoice_id") or extracted.get("buildops_invoice_id") or "").strip()
    return inv_id or None


@app.post("/api/documents/{doc_id}/send-email")
def send_email_any(doc_id: str, body: SendEmailIn):
    sql = text(
        """
        SELECT
          d.id,
          d.doc_type,
          d.status,
          d.customer_name,
          d.customer_email,
          d.property_address,
          d.invoice_number,
          d.extracted_fields,
          d.user_overrides,
          d.quote_number,
          d.job_report_number,
          d.original_s3_key,
          d.styled_draft_s3_key,
          d.final_s3_key,
          f.final_json
        FROM public.documents d
        LEFT JOIN public.document_fields f
          ON f.doc_id = d.id
        WHERE d.id = :id
        """
    )

    with SessionLocal() as db:
        row = db.execute(sql, {"id": doc_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        rowd = dict(row)
        _block_replaced_document(rowd)

        real_doc_id = str(doc_id)
        doc_type = rowd.get("doc_type") or ""

        if "INVOICE" in (doc_type or "").upper():
            raise HTTPException(
                status_code=409,
                detail="Please use the invoice send endpoint for invoices.",
            )

        to_email = str(body.client_email or rowd.get("customer_email") or "").strip()
        if not to_email:
            raise HTTPException(status_code=400, detail="No client email (customer_email is empty)")

        deficiency_report_link = (body.deficiency_report_link or "").strip() or None
        storage = get_storage()

        key = rowd["final_s3_key"] or rowd["styled_draft_s3_key"] or rowd["original_s3_key"]
        if not key:
            raise HTTPException(status_code=400, detail="No PDF available to send")

        label = rowd["invoice_number"] or rowd["quote_number"] or rowd["job_report_number"] or rowd["id"]
        filename = f"{rowd['doc_type']}_{label}.pdf"

        file_url = storage.presign_get_url(
            key=key,
            expires_seconds=7 * 24 * 3600,
            download_filename=filename,
            inline=True,
        )
        pdf_bytes = storage.download_bytes(key)

        customer_name = (rowd.get("customer_name") or "").strip()
        greeting = f"Good day {customer_name}," if customer_name else "Good day,"

        reviewable = _is_reviewable_quote(doc_type)

        quote_number, property_name, company_name = _extract_quote_info(rowd)
        display_quote_number = _display_quote_label(quote_number, real_doc_id)

        approve_url = None
        reject_url = None

        if reviewable:
            review_base = (os.getenv("PUBLIC_PORTAL_BASE_URL") or "").rstrip("/")
            if not review_base:
                raise RuntimeError("Missing PUBLIC_PORTAL_BASE_URL")

            approve_token = make_token(real_doc_id, "accept", extra_claims={"quote_number": display_quote_number})
            reject_token = make_token(real_doc_id, "reject", extra_claims={"quote_number": display_quote_number})

            approve_url = f"{review_base}/review?token={approve_token}"
            reject_url = f"{review_base}/review?token={reject_token}"

        payment_url = None
        if "INVOICE" in (doc_type or "").upper():
            buildops_invoice_id = _get_buildops_invoice_id(rowd)
            if buildops_invoice_id:
                try:
                    payment_url = get_invoice_payment_link(buildops_invoice_id)
                except Exception:
                    payment_url = None

        if reviewable:
            template_name = "quote.html"
            subject = (
                f"Quote #{display_quote_number} - {property_name}"
                if property_name
                else f"Quote #{display_quote_number}"
            )

            context = {
                "client_name": customer_name or None,
                "quote_number": display_quote_number,
                "property_name": property_name,
                "company_name": company_name,
                "quote_url": file_url,
                "approve_url": approve_url,
                "reject_url": reject_url,
                "deficiency_report_link": deficiency_report_link,
                "now": "",
            }

            html_body = render_html(template_name, context)

            text_body = (
                f"{greeting}\n\n"
                f"Here is your Quote #{display_quote_number}.\n"
                f"View Quote: {file_url}\n\n"
                + (f"Deficiency Report: {deficiency_report_link}\n\n" if deficiency_report_link else "")
                + f"Approve: {approve_url}\n"
                f"Reject: {reject_url}\n\n"
                "Need help? Reply to this email or call 416-305-0704.\n"
            )

        else:
            kind = email_kind_for(doc_type)
            template_name = template_for_kind(kind)
            subject = build_subject(kind, doc_type, str(label))

            context = {
                "greeting": greeting,
                "customer_name": customer_name,
                "doc_type": doc_type,
                "label": label,
                "file_url": file_url,
                "filename": filename,
                "payment_url": payment_url,
                "reviewable": False,
                "approve_url": None,
                "reject_url": None,
            }

            html_body = render_html(template_name, context)

            text_body = (
                f"{greeting}\n\n"
                f"Please find the document attached.\n"
                f"Link: {file_url}\n\n"
                + (f"Pay by Credit Card: {payment_url}\n\n" if payment_url else "")
                + "If you have any questions, reply to this email.\n"
            )

        cc_list = [str(x) for x in (body.cc or [])]
        bcc_list = [str(x) for x in (body.bcc or [])]

        send_email_brevo_smtp(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            cc_emails=cc_list,
            bcc_emails=bcc_list,
            attachments=[
                EmailAttachment(
                    filename=filename,
                    content_type="application/pdf",
                    data=pdf_bytes,
                )
            ],
        )

        sent_cc = ", ".join(cc_list) if cc_list else None
        sent_bcc = ", ".join(bcc_list) if bcc_list else None
        db.execute(
            text(
                """
                UPDATE public.documents
                SET sent_to = :sent_to,
                    sent_cc = :sent_cc,
                    sent_bcc = :sent_bcc,
                    sent_at = now(),
                    status = 'SENT',
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {"id": real_doc_id, "sent_to": to_email, "sent_cc": sent_cc, "sent_bcc": sent_bcc},
        )
        db.commit()

        sent_row = db.execute(
            text("SELECT sent_at FROM public.documents WHERE id=:id"),
            {"id": real_doc_id},
        ).mappings().first()

        return {
            "ok": True,
            "doc_id": real_doc_id,
            "to": to_email,
            "cc": cc_list,
            "bcc": bcc_list,
            "url": file_url,
            "sent_at": sent_row["sent_at"] if sent_row else None,
            "template": template_name,
            "reviewable": reviewable,
            "payment_url": payment_url if ("INVOICE" in (doc_type or "").upper()) else None,
            "quote_number": display_quote_number if reviewable else None,
        }


class AcceptIn(BaseModel):
    quote_po_number: Optional[str] = None
    quote_note: Optional[str] = None
    send_email: bool = False
    cc: Optional[List[EmailStr]] = None
    token: str


class RejectIn(BaseModel):
    reason: Optional[str] = None
    token: str


def _notify_support_approved(quote_number: str, po: str | None, note: str | None):
    subject = f"Quote #{quote_number} APPROVED"

    lines = [f"Quote #{quote_number} has been APPROVED.", ""]
    if po and po.strip():
        lines.append(f"PO Number: {po.strip()}")
    if note and note.strip():
        lines.append(f"Notes: {note.strip()}")

    text_body = "\n".join(lines).strip() + "\n"
    html_body = text_body.replace("\n", "<br>")

    send_email_brevo_smtp(
        to_email="sarah@mainlinefire.com",
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        cc_emails=[],
        attachments=[],
    )


def _notify_support_rejected(quote_number: str, reason: str | None):
    subject = f"Quote #{quote_number} REJECTED"

    lines = [f"Quote #{quote_number} has been REJECTED.", ""]
    if reason and reason.strip():
        lines.append(f"Reason: {reason.strip()}")

    text_body = "\n".join(lines).strip() + "\n"
    html_body = text_body.replace("\n", "<br>")

    send_email_brevo_smtp(
        to_email="sarah@mainlinefire.com",
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        cc_emails=[],
        attachments=[],
    )


@app.post("/api/documents/{doc_id}/accept")
def accept_document(doc_id: str, body: AcceptIn):
    claims = verify_token(body.token)
    if claims["doc_id"] != doc_id or claims["action"] != "accept":
        raise HTTPException(status_code=403, detail="Invalid token for this action")

    with SessionLocal() as db:
        row = db.execute(
            text(
                """
                SELECT
                  d.id,
                  d.status,
                  d.doc_type,
                  d.quote_number,
                  f.final_json
                FROM public.documents d
                LEFT JOIN public.document_fields f
                  ON f.doc_id = d.id
                WHERE d.id = :id
                """
            ),
            {"id": doc_id},
        ).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        rowd = dict(row)
        _block_replaced_document(rowd)

        if not _is_reviewable_quote(rowd.get("doc_type") or ""):
            raise HTTPException(status_code=409, detail=f"Not reviewable for doc_type={rowd.get('doc_type')}")

        quote_number, _, _ = _extract_quote_info(rowd)
        quote_label = _display_quote_label(quote_number, doc_id)

        status = (rowd.get("status") or "").upper()

        if status == "APPROVED":
            return {"ok": True, "id": doc_id, "status": "APPROVED", "message": "Already approved."}

        if status == "REJECTED":
            raise HTTPException(status_code=409, detail=f"Quote #{quote_label} was already rejected.")

        if status not in ("SENT", "FINALIZED"):
            raise HTTPException(status_code=409, detail=f"Cannot approve when status={rowd['status']}")

        db.execute(
            text(
                """
                UPDATE public.documents
                SET status='APPROVED',
                    quote_po_number = COALESCE(:po, quote_po_number),
                    quote_note = COALESCE(:note, quote_note),
                    quote_reject_reason = NULL,
                    quote_responded_at = now(),
                    updated_at = now(),
                    error = NULL
                WHERE id = :id
                """
            ),
            {"id": doc_id, "po": body.quote_po_number, "note": body.quote_note},
        )
        db.commit()

    _notify_support_approved(quote_label, body.quote_po_number, body.quote_note)

    if body.send_email:
        return send_email_any(doc_id, SendEmailIn(client_email=None, cc=body.cc))

    return {"ok": True, "id": doc_id, "status": "APPROVED"}


@app.post("/api/documents/{doc_id}/reject")
def reject_document(doc_id: str, body: RejectIn):
    claims = verify_token(body.token)
    if claims["doc_id"] != doc_id or claims["action"] != "reject":
        raise HTTPException(status_code=403, detail="Invalid token for this action")

    with SessionLocal() as db:
        row = db.execute(
            text(
                """
                SELECT
                  d.id,
                  d.status,
                  d.doc_type,
                  d.quote_number,
                  f.final_json
                FROM public.documents d
                LEFT JOIN public.document_fields f
                  ON f.doc_id = d.id
                WHERE d.id = :id
                """
            ),
            {"id": doc_id},
        ).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        rowd = dict(row)
        _block_replaced_document(rowd)

        if not _is_reviewable_quote(rowd.get("doc_type") or ""):
            raise HTTPException(status_code=409, detail=f"Not reviewable for doc_type={rowd.get('doc_type')}")

        quote_number, _, _ = _extract_quote_info(rowd)
        quote_label = _display_quote_label(quote_number, doc_id)

        status = (rowd.get("status") or "").upper()

        if status == "REJECTED":
            return {"ok": True, "id": doc_id, "status": "REJECTED", "message": "Already rejected."}

        if status == "APPROVED":
            raise HTTPException(status_code=409, detail=f"Quote #{quote_label} was already approved.")

        if status not in ("SENT", "FINALIZED"):
            raise HTTPException(status_code=409, detail=f"Cannot reject when status={rowd['status']}")

        db.execute(
            text(
                """
                UPDATE public.documents
                SET status='REJECTED',
                    quote_reject_reason = :reason,
                    quote_responded_at = now(),
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {"id": doc_id, "reason": (body.reason or "").strip() or None},
        )
        db.commit()

    _notify_support_rejected(quote_label, body.reason)

    return {"ok": True, "id": doc_id, "status": "REJECTED"}


@app.get("/api/documents/{doc_id}/quote-decision")
def get_quote_decision(doc_id: str, token: str):
    try:
        claims = verify_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired link.")

    if str(claims.get("doc_id", "")) != str(doc_id):
        raise HTTPException(status_code=401, detail="Invalid token for this document.")

    with SessionLocal() as db:
        row = db.execute(
            text(
                """
                SELECT
                  id,
                  doc_type,
                  status,
                  quote_po_number,
                  quote_note,
                  quote_reject_reason,
                  quote_responded_at
                FROM public.documents
                WHERE id = :id
                """
            ),
            {"id": doc_id},
        ).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Document not found.")

        rowd = dict(row)
        _block_replaced_document(rowd)

    status = (rowd.get("status") or "PENDING").upper()
    if status == "APPROVED":
        norm = "APPROVED"
    elif status == "REJECTED":
        norm = "REJECTED"
    else:
        norm = "PENDING"

    return {
        "doc_id": rowd["id"],
        "status": norm,
        "quote_po_number": rowd.get("quote_po_number"),
        "quote_note": rowd.get("quote_note"),
        "reject_reason": rowd.get("quote_reject_reason"),
        "decided_at": rowd.get("quote_responded_at"),
    }