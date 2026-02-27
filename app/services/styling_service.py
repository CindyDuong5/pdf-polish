# app/services/styling_service.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Tuple

from sqlalchemy import text, bindparam
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import JSONB  # ✅ add this

from app.storage.s3_storage import get_storage
from app.services.keys import styled_draft_key

from app.styling.service_quote.styler import ServiceQuoteStyler


def _get_service_quote_template_path() -> Path:
    p = os.getenv("SERVICE_QUOTE_TEMPLATE_PDF")
    if p:
        return Path(p)
    return Path("templates/Mainline-Service-Quote.pdf")


def _pick_styler(doc_type: str) -> Tuple[Any, str]:
    dt = (doc_type or "").upper().strip()
    if dt in {"SERVICE_QUOTE", "QUOTE", "SERVICE"}:
        tpl = _get_service_quote_template_path()
        return ServiceQuoteStyler(template_pdf=tpl), "service_quote"
    raise ValueError(f"No styler configured yet for doc_type={doc_type!r}")


def ensure_draft(db: Session, doc_id: str, *, force: bool = False) -> str:
    row = db.execute(
        text("""
            SELECT id, doc_type, original_s3_key, styled_draft_s3_key
            FROM public.documents
            WHERE id = :id
        """),
        {"id": doc_id},
    ).mappings().first()

    if not row:
        raise ValueError("Document not found")

    if row["styled_draft_s3_key"] and not force:
        return row["styled_draft_s3_key"]

    doc_type = row["doc_type"] or "OTHER"
    original_key = row["original_s3_key"]
    if not original_key:
        raise ValueError("Missing original_s3_key")

    draft_key = styled_draft_key(original_key, str(doc_id))
    storage = get_storage()

    # mark STYLING
    db.execute(
        text("""
            UPDATE public.documents
            SET status='STYLING', updated_at=now(), error=null
            WHERE id=:id
        """),
        {"id": doc_id},
    )
    db.commit()

    try:
        original_bytes = storage.download_bytes(original_key)

        styler, styler_kind = _pick_styler(doc_type)
        draft_bytes, extracted = styler.style(original_bytes)

        storage.upload_pdf_bytes(draft_key, draft_bytes)

        extracted_payload = {
            "styler_kind": styler_kind,
            "parsed": extracted.__dict__ if hasattr(extracted, "__dict__") else {},
        }

        # ✅ Bind extracted as JSONB so you can pass a dict directly
        stmt = text("""
            UPDATE public.documents
            SET styled_draft_s3_key=:k,
                status='READY_FOR_REVIEW',
                updated_at=now(),
                error=null,
                extracted_fields = COALESCE(extracted_fields, '{}'::jsonb) || :extracted
            WHERE id=:id
        """).bindparams(bindparam("extracted", type_=JSONB))

        db.execute(
            stmt,
            {"id": doc_id, "k": draft_key, "extracted": extracted_payload},
        )
        db.commit()

        return draft_key

    except Exception as e:
        db.rollback()  # ✅ IMPORTANT

        db.execute(
            text("""
                UPDATE public.documents
                SET status='ERROR', updated_at=now(), error=:err
                WHERE id=:id
            """),
            {"id": doc_id, "err": f"{type(e).__name__}: {e}"[:1000]},
        )
        db.commit()
        raise