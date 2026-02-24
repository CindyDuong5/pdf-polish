# app/api_main.py
from __future__ import annotations

import os
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.storage.s3_storage import get_storage

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
    """
    Uses your existing schema:
      - doc_type (invoice/quote/job/etc.)
      - invoice_number / quote_number / job_report_number
      - customer_name / property_address optional
    """
    where = []
    params = {"limit": limit}

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
    """
    Returns a presigned S3 URL for opening in browser.
    Kept mainly for debugging; frontend should prefer /links.
    """
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
    """
    Returns presigned URLs (only for keys that exist in DB).
    Frontend should use this endpoint.
    """
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

        # Nice filename for browser tab / download
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