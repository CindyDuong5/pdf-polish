# app/services/styling_service.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.storage.s3_storage import get_storage
from app.services.keys import styled_draft_key
from app.styling.service_quote.styler import ServiceQuoteStyler
from app.services.document_fields import upsert_draft
from app.services.service_quote_editor import service_quote_to_json


def _get_service_quote_template_path() -> Path:
    p = os.getenv("SERVICE_QUOTE_TEMPLATE_PDF")
    if p:
        return Path(p)
    return Path("templates/Mainline-Service-Quote.pdf")


def _pick_styler(doc_type: str) -> Tuple[Any, str]:
    dt = (doc_type or "").upper().strip()
    if dt in {"SERVICE_QUOTE", "QUOTE", "SERVICE", "PROJECT_QUOTE"}:
        tpl = _get_service_quote_template_path()
        return ServiceQuoteStyler(template_pdf=tpl), "service_quote"
    raise ValueError(f"No styler configured yet for doc_type={doc_type!r}")


def _mark_older_quote_rows_replaced(
    db: Session,
    quote_number: str | None,
    *,
    keep_id: str,
) -> int:
    quote_number = (quote_number or "").strip()
    if not quote_number:
        return 0

    result = db.execute(
        text(
            """
            UPDATE public.documents
            SET status = 'REPLACED',
                updated_at = now(),
                error = :err
            WHERE quote_number = :quote_number
              AND upper(doc_type) LIKE '%QUOTE%'
              AND id <> :keep_id
              AND COALESCE(status, '') <> 'REPLACED'
            """
        ),
        {
            "quote_number": quote_number,
            "keep_id": keep_id,
            "err": f"Replaced by newer quote row {keep_id}",
        },
    )
    return int(result.rowcount or 0)


def ensure_draft(db: Session, doc_id: str, *, force: bool = False) -> dict:
    row = db.execute(
        text(
            """
            SELECT id, doc_type, original_s3_key, styled_draft_s3_key, quote_number
            FROM public.documents
            WHERE id = :id
            """
        ),
        {"id": doc_id},
    ).mappings().first()

    if not row:
        raise ValueError("Document not found")

    if row["styled_draft_s3_key"] and not force:
        return {
            "doc_id": str(row["id"]),
            "styled_draft_s3_key": row["styled_draft_s3_key"],
            "reused_existing": False,
        }

    doc_type = row["doc_type"] or "OTHER"
    original_key = row["original_s3_key"]
    if not original_key:
        raise ValueError("Missing original_s3_key")

    storage = get_storage()

    db.execute(
        text(
            """
            UPDATE public.documents
            SET status='STYLING', updated_at=now(), error=null
            WHERE id=:id
            """
        ),
        {"id": doc_id},
    )
    db.commit()

    try:
        original_bytes = storage.download_bytes(original_key)

        styler, _styler_kind = _pick_styler(doc_type)
        draft_bytes, extracted_doc = styler.style(original_bytes)
        draft_json = service_quote_to_json(extracted_doc)

        parsed_quote_number = (draft_json.get("quote_number") or "").strip() or None
        target_doc_id = str(doc_id)

        draft_key = styled_draft_key(original_key, target_doc_id)

        storage.upload_pdf_bytes(draft_key, draft_bytes)
        upsert_draft(db, target_doc_id, draft_json)

        db.execute(
            text(
                """
                UPDATE public.documents
                SET styled_draft_s3_key = :k,
                    status = 'READY_FOR_REVIEW',
                    quote_number = COALESCE(:quote_number, quote_number),
                    customer_name = COALESCE(:customer_name, customer_name),
                    customer_email = COALESCE(:customer_email, customer_email),
                    property_address = COALESCE(:property_address, property_address),
                    updated_at = now(),
                    error = null
                WHERE id = :id
                """
            ),
            {
                "id": target_doc_id,
                "k": draft_key,
                "quote_number": parsed_quote_number,
                "customer_name": (draft_json.get("client_name") or "").strip() or None,
                "customer_email": (draft_json.get("client_email") or "").strip() or None,
                "property_address": (draft_json.get("property_address") or "").strip() or None,
            },
        )

        if parsed_quote_number:
            _mark_older_quote_rows_replaced(db, parsed_quote_number, keep_id=target_doc_id)

        db.commit()

        return {
            "doc_id": target_doc_id,
            "styled_draft_s3_key": draft_key,
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
            {"id": doc_id, "err": f"{type(e).__name__}: {e}"[:1000]},
        )
        db.commit()
        raise