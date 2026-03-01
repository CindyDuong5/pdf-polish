# app/api_main.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.storage.s3_storage import get_storage
from app.services.document_fields import get_fields, set_final
from app.services.keys import final_key
from app.services.styling_service import ensure_draft
from app.services.pdf_stamp import stamp_pdf

# ✅ Service Quote editing + rendering
from app.services.service_quote_editor import json_to_service_quote, normalize_service_quote_fields
from app.styling.service_quote.renderer import render_service_quote

from pydantic import BaseModel, EmailStr
from typing import List, Optional
from app.email.smtp_sender import send_email_brevo_smtp, EmailAttachment
from app.email.template_router import email_kind_for, template_for_kind, render_html, build_subject

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
            # ensure draft exists (this will also store draft_json)
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
# ✅ NEW: Save Final from edited fields (Service Quote)
# ------------------------------------------------------------
@app.post("/api/documents/{doc_id}/save-final")
def save_final(doc_id: str, body: dict = Body(...)):
    """
    body = { "fields": { ...ServiceQuoteData json... } }
    - Normalizes totals (subtotal/tax/total) if blank
    - Stores final_json
    - Renders FINAL PDF and uploads to S3
    - Updates documents.final_s3_key + status
    - ✅ Also copies client_email/client_name/property_address into documents table
    """
    fields = body.get("fields")
    if not isinstance(fields, dict):
        raise HTTPException(status_code=400, detail="Missing fields")

    # ✅ compute subtotal/tax/total if user left blank
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

        # mark FINALIZING
        db.execute(
            text("UPDATE public.documents SET status='FINALIZING', updated_at=now(), error=null WHERE id=:id"),
            {"id": doc_id},
        )
        db.commit()

        try:
            # ✅ store final JSON
            set_final(db, doc_id, fields)
            db.commit()

            # ✅ ALSO store important fields on documents table (fixes "To" missing)
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

            # ✅ json -> ServiceQuoteData
            data = json_to_service_quote(fields)

            # ✅ render final pdf
            template_path = Path(os.getenv("SERVICE_QUOTE_TEMPLATE_PDF") or "templates/Mainline-Service-Quote.pdf")
            final_bytes = render_service_quote(template_path, data)

            # ✅ upload + update
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

class SendQuoteEmailIn(BaseModel):
    client_email: EmailStr
    cc: Optional[List[EmailStr]] = None
    
class SendEmailIn(BaseModel):
    # optional override; if omitted, backend uses documents.customer_email
    client_email: Optional[EmailStr] = None
    cc: Optional[List[EmailStr]] = None


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

        # choose best available file
        key = row["final_s3_key"] or row["styled_draft_s3_key"] or row["original_s3_key"]
        if not key:
            raise HTTPException(status_code=400, detail="No PDF available to send")

        label = row["invoice_number"] or row["quote_number"] or row["job_report_number"] or row["id"]
        filename = f"{row['doc_type']}_{label}.pdf"

        file_url = storage.presign_get_url(
            key=key,
            expires_seconds=7 * 24 * 3600,  # 7 days
            download_filename=filename,
            inline=True,
        )

        pdf_bytes = storage.download_bytes(key)

        # ----------------------------
        # ✅ Template routing by doc_type
        # ----------------------------
        customer_name = (row.get("customer_name") or "").strip()
        greeting = f"Good day {customer_name}," if customer_name else "Good day,"

        kind = email_kind_for(row.get("doc_type"))
        template_name = template_for_kind(kind)

        subject = build_subject(kind, row.get("doc_type"), str(label))

        context = {
            "greeting": greeting,
            "customer_name": customer_name,
            "doc_type": row.get("doc_type"),
            "label": label,
            "file_url": file_url,
            "filename": filename,
        }

        html_body = render_html(template_name, context)

        # simple plaintext fallback
        text_body = (
            f"{greeting}\n\n"
            f"Please find the document attached.\n"
            f"Link: {file_url}\n\n"
            f"If you have any questions, reply to this email.\n"
        )

        cc_list = [str(x) for x in (body.cc or [])]

        # 5) Send via Brevo SMTP
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

        # 6) Store sent metadata + mark SENT
        sent_cc = ", ".join(cc_list) if cc_list else None

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
        }
    
# --- Review actions: Accept / Reject (human approval) -----------------

class AcceptIn(BaseModel):
    # optional fields you already have in documents table
    quote_po_number: Optional[str] = None
    quote_note: Optional[str] = None
    # If true, auto-send email after accept (optional)
    send_email: bool = False
    cc: Optional[List[EmailStr]] = None


class RejectIn(BaseModel):
    reason: Optional[str] = None


@app.post("/api/documents/{doc_id}/accept")
def accept_document(doc_id: str, body: AcceptIn):
    with SessionLocal() as db:
        row = db.execute(
            text("SELECT id, status FROM public.documents WHERE id=:id"),
            {"id": doc_id},
        ).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        if row["status"] != "READY_FOR_REVIEW":
            raise HTTPException(status_code=409, detail=f"Cannot accept when status={row['status']}")

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

    if body.send_email:
        return send_email_any(doc_id, SendEmailIn(client_email=None, cc=body.cc))

    return {"ok": True, "id": doc_id, "status": "APPROVED"}

@app.post("/api/documents/{doc_id}/reject")
def reject_document(doc_id: str, body: RejectIn):
    with SessionLocal() as db:
        row = db.execute(
            text("SELECT id, status FROM public.documents WHERE id=:id"),
            {"id": doc_id},
        ).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        if row["status"] != "READY_FOR_REVIEW":
            raise HTTPException(status_code=409, detail=f"Cannot reject when status={row['status']}")

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

    return {"ok": True, "id": doc_id, "status": "REJECTED"}
  