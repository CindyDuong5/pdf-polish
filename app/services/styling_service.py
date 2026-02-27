# app/service/styling_service.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.storage.s3_storage import get_storage
from app.services.keys import styled_draft_key
from app.services.pdf_stamp import stamp_pdf


def ensure_draft(db: Session, doc_id: str, *, force: bool = False) -> str:
    row = db.execute(
        text("""
            SELECT id, original_s3_key, styled_draft_s3_key
            FROM public.documents
            WHERE id = :id
        """),
        {"id": doc_id},
    ).mappings().first()

    if not row:
        raise ValueError("Document not found")

    if row["styled_draft_s3_key"] and not force:
        return row["styled_draft_s3_key"]

    original_key = row["original_s3_key"]
    if not original_key:
        raise ValueError("Missing original_s3_key")

    draft_key = styled_draft_key(original_key, doc_id)
    storage = get_storage()

    db.execute(
        text("""
            UPDATE public.documents
            SET status='STYLING', updated_at=now(), error=null
            WHERE id=:id
        """),
        {"id": doc_id},
    )
    db.commit()

    original_bytes = storage.download_bytes(original_key)
    draft_bytes = stamp_pdf(original_bytes, "RESTYLED DRAFT")
    storage.upload_pdf_bytes(draft_key, draft_bytes)

    db.execute(
        text("""
            UPDATE public.documents
            SET styled_draft_s3_key=:k,
                status='READY_FOR_REVIEW',
                updated_at=now(),
                error=null
            WHERE id=:id
        """),
        {"id": doc_id, "k": draft_key},
    )
    db.commit()

    return draft_key