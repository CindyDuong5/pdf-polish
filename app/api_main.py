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
          created_at,
          updated_at,
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

            return {"ok": True, "final_s3_key": fk}

        except Exception as e:
            db.rollback()
            db.execute(
                text("UPDATE public.documents SET status='ERROR', updated_at=now(), error=:err WHERE id=:id"),
                {"id": doc_id, "err": f"{type(e).__name__}: {e}"[:1000]},
            )
            db.commit()
            raise
    