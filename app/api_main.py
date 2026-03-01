# app/api_main.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, List, Optional

from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.email.smtp_sender import EmailAttachment, send_email_brevo_smtp
from app.email.template_router import build_subject, email_kind_for, render_html, template_for_kind
from app.security.quote_response_token import make_token, verify_token  # ✅ use your existing JWT
from app.services.document_fields import get_fields, set_final
from app.services.keys import final_key
from app.services.pdf_stamp import stamp_pdf
from app.services.styling_service import ensure_draft
from app.services.service_quote_editor import json_to_service_quote, normalize_service_quote_fields
from app.storage.s3_storage import get_storage
from app.styling.service_quote.renderer import render_service_quote

print("LOADED api_main.py FROM:", __file__)
load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

app = FastAPI(title="PDF Polish API")

# CORS for local frontend dev (React/Vite/etc.)
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
        return dict(row)


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

        if which == "original":
            key = row["original_s3_key"]
        elif which == "final":
            key = row["final_s3_key"]
        else:
            key = row["styled_draft_s3_key"]

        if not key:
            raise HTTPException(status_code=400, detail=f"No {which} file available yet")

        storage = get_storage()
        label = row["invoice_number"] or row["quote_number"] or row["job_report_number"] or row["id"]
        filename = f"{row['doc_type']}_{label}.pdf"

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

        storage = get_storage()
        label = row["invoice_number"] or row["quote_number"] or row["job_report_number"] or row["id"]
        filename = f"{row['doc_type']}_{label}.pdf"

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
            "id": row["id"],
            "doc_type": row["doc_type"],
            "filename": filename,
            "original": {"key": row["original_s3_key"], "url": url_for(row["original_s3_key"])},
            "styled_draft": {"key": row["styled_draft_s3_key"], "url": url_for(row["styled_draft_s3_key"])},
            "final": {"key": row["final_s3_key"], "url": url_for(row["final_s3_key"])},
        }


# ------------------------------------------------------------
# Existing: Stamp-based finalize (optional debug tool)
# ------------------------------------------------------------
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
                SELECT id, original_s3_key, styled_draft_s3_key, final_s3_key
                FROM public.documents
                WHERE id = :id
                """
            ),
            {"id": doc_id},
        ).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        if row["final_s3_key"] and not force:
            return {
                "ok": True,
                "note": "Final already exists (use force=true to regenerate).",
                "final_s3_key": row["final_s3_key"],
            }

        original_key = row["original_s3_key"]
        draft_key = row["styled_draft_s3_key"]
        if not original_key:
            raise HTTPException(status_code=400, detail="Document missing original_s3_key")

        source_key = draft_key or original_key
        final_key_path = final_key(original_key, doc_id)

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


# ------------------------------------------------------------
# Draft creation (restyle)
# ------------------------------------------------------------
@app.post("/api/documents/{doc_id}/restyle")
def restyle_document(doc_id: str):
    with SessionLocal() as db:
        key = ensure_draft(db, doc_id, force=True)
        return {"ok": True, "styled_draft_s3_key": key}


# ------------------------------------------------------------
# Fields: editable JSON (draft/final)
# ------------------------------------------------------------
@app.get("/api/documents/{doc_id}/fields")
def get_document_fields(doc_id: str):
    with SessionLocal() as db:
        row = get_fields(db, doc_id)
        if not row:
            ensure_draft(db, doc_id, force=False)
            row = get_fields(db, doc_id)

        if not row:
            raise HTTPException(status_code=404, detail="No fields available")

        return {
            "doc_id": doc_id,
            "draft": row.get("draft_json"),
            "final": row.get("final_json"),
        }


# ------------------------------------------------------------
# ✅ Save Final from edited fields (Service Quote)
# ------------------------------------------------------------
@app.post("/api/documents/{doc_id}/save-final")
def save_final(doc_id: str, body: dict = Body(...)):
    fields = body.get("fields")
    if not isinstance(fields, dict):
        raise HTTPException(status_code=400, detail="Missing fields")

    fields = normalize_service_quote_fields(fields)
    storage = get_storage()

    with SessionLocal() as db:
        row = db.execute(
            text("SELECT id, original_s3_key FROM public.documents WHERE id=:id"),
            {"id": doc_id},
        ).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        original_key = row["original_s3_key"]
        if not original_key:
            raise HTTPException(status_code=400, detail="Missing original_s3_key")

        db.execute(
            text("UPDATE public.documents SET status='FINALIZING', updated_at=now(), error=null WHERE id=:id"),
            {"id": doc_id},
        )
        db.commit()

        try:
            set_final(db, doc_id, fields)
            db.commit()

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
                        updated_at = now()
                    WHERE id = :id
                    """
                ),
                {
                    "id": doc_id,
                    "customer_email": client_email,
                    "customer_name": client_name,
                    "property_address": prop_addr,
                },
            )
            db.commit()

            data = json_to_service_quote(fields)
            template_path = Path(os.getenv("SERVICE_QUOTE_TEMPLATE_PDF") or "templates/Mainline-Service-Quote.pdf")
            final_bytes = render_service_quote(template_path, data)

            fk = final_key(original_key, doc_id)
            storage.upload_pdf_bytes(fk, final_bytes)

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
                {"id": doc_id, "k": fk},
            )
            db.commit()

            return {"ok": True, "final_s3_key": fk, "customer_email": client_email}

        except Exception as e:
            db.rollback()
            db.execute(
                text("UPDATE public.documents SET status='ERROR', updated_at=now(), error=:err WHERE id=:id"),
                {"id": doc_id, "err": f"{type(e).__name__}: {e}"[:1000]},
            )
            db.commit()
            raise


class SendEmailIn(BaseModel):
    client_email: Optional[EmailStr] = None
    cc: Optional[List[EmailStr]] = None


def _is_reviewable_quote(doc_type: str) -> bool:
    """
    Only Service Quote + Project Quote get Approve/Reject buttons.
    Adjust these checks to match your exact doc_type values.
    """
    dt = (doc_type or "").upper()
    return ("SERVICE_QUOTE" in dt) or ("PROJECT_QUOTE" in dt)


@app.post("/api/documents/{doc_id}/send-email")
def send_email_any(doc_id: str, body: SendEmailIn):
    sql = text(
        """
        SELECT
          id,
          doc_type,
          customer_name,
          customer_email,
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

        to_email = str(body.client_email or row.get("customer_email") or "").strip()
        if not to_email:
            raise HTTPException(status_code=400, detail="No client email (customer_email is empty)")

        storage = get_storage()

        key = row["final_s3_key"] or row["styled_draft_s3_key"] or row["original_s3_key"]
        if not key:
            raise HTTPException(status_code=400, detail="No PDF available to send")

        label = row["invoice_number"] or row["quote_number"] or row["job_report_number"] or row["id"]
        filename = f"{row['doc_type']}_{label}.pdf"

        file_url = storage.presign_get_url(
            key=key,
            expires_seconds=7 * 24 * 3600,
            download_filename=filename,
            inline=True,
        )

        pdf_bytes = storage.download_bytes(key)

        customer_name = (row.get("customer_name") or "").strip()
        greeting = f"Good day {customer_name}," if customer_name else "Good day,"

        kind = email_kind_for(row.get("doc_type"))
        template_name = template_for_kind(kind)
        subject = build_subject(kind, row.get("doc_type"), str(label))

        # ✅ Approve/Reject only for Service Quote + Project Quote
        reviewable = _is_reviewable_quote(row.get("doc_type") or "")
        approve_url = None
        reject_url = None

        if reviewable:
            review_base = (os.getenv("PUBLIC_PORTAL_BASE_URL") or "").rstrip("/")
            if not review_base:
                raise RuntimeError("Missing PUBLIC_PORTAL_BASE_URL (frontend base URL)")
            print("PUBLIC_PORTAL_BASE_URL =", os.getenv("PUBLIC_PORTAL_BASE_URL"))
            
            approve_token = make_token(doc_id, "accept")
            reject_token = make_token(doc_id, "reject")
            approve_url = f"{review_base}/review?token={approve_token}"
            reject_url = f"{review_base}/review?token={reject_token}"

            # ✅ Make sure it is reviewable even after we mark it SENT
            # (accept/reject endpoints will allow READY_FOR_REVIEW or SENT)
            db.execute(
                text(
                    """
                    UPDATE public.documents
                    SET status = CASE
                        WHEN status IN ('APPROVED','REJECTED') THEN status
                        ELSE 'READY_FOR_REVIEW'
                    END,
                    updated_at = now()
                    WHERE id = :id
                    """
                ),
                {"id": doc_id},
            )
            db.commit()

        context = {
            "greeting": greeting,
            "customer_name": customer_name,
            "doc_type": row.get("doc_type"),
            "label": label,
            "file_url": file_url,
            "filename": filename,
            "reviewable": reviewable,
            "approve_url": approve_url,
            "reject_url": reject_url,
        }

        html_body = render_html(template_name, context)

        text_body = (
            f"{greeting}\n\n"
            f"Please find the document attached.\n"
            f"Link: {file_url}\n\n"
        )
        if reviewable and approve_url and reject_url:
            text_body += f"Approve: {approve_url}\nReject: {reject_url}\n\n"
        text_body += "If you have any questions, reply to this email.\n"

        cc_list = [str(x) for x in (body.cc or [])]

        send_email_brevo_smtp(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            cc_emails=cc_list,
            attachments=[
                EmailAttachment(
                    filename=filename,
                    content_type="application/pdf",
                    data=pdf_bytes,
                )
            ],
        )

        sent_cc = ", ".join(cc_list) if cc_list else None

        # ✅ keep status SENT after sending
        db.execute(
            text(
                """
                UPDATE public.documents
                SET sent_to = :sent_to,
                    sent_cc = :sent_cc,
                    sent_at = now(),
                    status = 'SENT',
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {"id": doc_id, "sent_to": to_email, "sent_cc": sent_cc},
        )
        db.commit()

        sent_row = db.execute(
            text("SELECT sent_at FROM public.documents WHERE id=:id"),
            {"id": doc_id},
        ).mappings().first()

        return {
            "ok": True,
            "to": to_email,
            "cc": cc_list,
            "url": file_url,
            "sent_at": sent_row["sent_at"] if sent_row else None,
            "kind": kind,
            "template": template_name,
            "reviewable": reviewable,
        }


# --- Review actions: Accept / Reject (client approval) -----------------

class AcceptIn(BaseModel):
    quote_po_number: Optional[str] = None
    quote_note: Optional[str] = None
    send_email: bool = False
    cc: Optional[List[EmailStr]] = None
    token: str  # ✅ required


class RejectIn(BaseModel):
    reason: Optional[str] = None
    token: str  # ✅ required


def _notify_support_approved(doc_id: str, quote_label: str, po: str | None, note: str | None):
    subject = f"Quote {quote_label} APPROVED"
    text_body = (
        f"Quote {quote_label} has been APPROVED.\n\n"
        f"PO Number: {(po or '').strip()}\n"
        f"Notes: {(note or '').strip()}\n"
        f"Document ID: {doc_id}\n"
    )
    html_body = text_body.replace("\n", "<br>")

    send_email_brevo_smtp(
        to_email="support@mainlinefire.com",
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        cc_emails=[],
        attachments=[],
    )


def _notify_support_rejected(doc_id: str, quote_label: str, reason: str | None):
    subject = f"Quote {quote_label} REJECTED"
    text_body = (
        f"Quote {quote_label} has been REJECTED.\n\n"
        f"Reason: {(reason or '').strip()}\n"
        f"Document ID: {doc_id}\n"
    )
    html_body = text_body.replace("\n", "<br>")

    send_email_brevo_smtp(
        to_email="support@mainlinefire.com",
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        cc_emails=[],
        attachments=[],
    )


@app.post("/api/documents/{doc_id}/accept")
def accept_document(doc_id: str, body: AcceptIn):
    # ✅ verify JWT (expired/invalid will raise)
    claims = verify_token(body.token)
    if claims["doc_id"] != doc_id or claims["action"] != "accept":
        raise HTTPException(status_code=403, detail="Invalid token for this action")

    with SessionLocal() as db:
        row = db.execute(
            text("SELECT id, status, doc_type, quote_number FROM public.documents WHERE id=:id"),
            {"id": doc_id},
        ).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        # ✅ allow accept if READY_FOR_REVIEW OR SENT (because send-email sets SENT)
        if row["status"] not in ("READY_FOR_REVIEW", "SENT"):
            raise HTTPException(status_code=409, detail=f"Cannot accept when status={row['status']}")

        # ✅ extra safety: only allow for reviewable quotes
        if not _is_reviewable_quote(row.get("doc_type") or ""):
            raise HTTPException(status_code=409, detail=f"Not reviewable for doc_type={row.get('doc_type')}")

        db.execute(
            text(
                """
                UPDATE public.documents
                SET status='APPROVED',
                    quote_po_number = COALESCE(:po, quote_po_number),
                    quote_note = COALESCE(:note, quote_note),
                    quote_reject_reason = NULL,
                    quote_responded_at = now(),
                    updated_at=now(),
                    error=NULL
                WHERE id=:id
                """
            ),
            {"id": doc_id, "po": body.quote_po_number, "note": body.quote_note},
        )
        db.commit()

        quote_label = row.get("quote_number") or doc_id[:8]

    # ✅ notify support
    _notify_support_approved(doc_id, quote_label, body.quote_po_number, body.quote_note)

    # optional: auto-send (keep if you want; usually false for client review)
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
            text("SELECT id, status, doc_type, quote_number FROM public.documents WHERE id=:id"),
            {"id": doc_id},
        ).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        if row["status"] not in ("READY_FOR_REVIEW", "SENT"):
            raise HTTPException(status_code=409, detail=f"Cannot reject when status={row['status']}")

        if not _is_reviewable_quote(row.get("doc_type") or ""):
            raise HTTPException(status_code=409, detail=f"Not reviewable for doc_type={row.get('doc_type')}")

        db.execute(
            text(
                """
                UPDATE public.documents
                SET status='REJECTED',
                    quote_reject_reason = :reason,
                    quote_responded_at = now(),
                    updated_at=now()
                WHERE id=:id
                """
            ),
            {"id": doc_id, "reason": (body.reason or "").strip() or None},
        )
        db.commit()

        quote_label = row.get("quote_number") or doc_id[:8]

    _notify_support_rejected(doc_id, quote_label, body.reason)

    return {"ok": True, "id": doc_id, "status": "REJECTED"}