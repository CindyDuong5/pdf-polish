from __future__ import annotations

from sqlalchemy import text, bindparam
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import JSONB


def get_fields(db: Session, doc_id: str) -> dict | None:
    row = db.execute(
        text("select draft_json, final_json from public.document_fields where doc_id=:id"),
        {"id": doc_id},
    ).mappings().first()
    return dict(row) if row else None


def upsert_draft(db: Session, doc_id: str, draft_json: dict) -> None:
    stmt = text(
        """
        insert into public.document_fields (doc_id, draft_json, updated_at)
        values (:id, :j, now())
        on conflict (doc_id)
        do update set draft_json=:j, updated_at=now()
        """
    ).bindparams(bindparam("j", type_=JSONB))

    db.execute(stmt, {"id": doc_id, "j": draft_json})


def set_final(db: Session, doc_id: str, final_json: dict) -> None:
    stmt = text(
        """
        insert into public.document_fields (doc_id, final_json, updated_at)
        values (:id, :j, now())
        on conflict (doc_id)
        do update set final_json=:j, updated_at=now()
        """
    ).bindparams(bindparam("j", type_=JSONB))

    db.execute(stmt, {"id": doc_id, "j": final_json})