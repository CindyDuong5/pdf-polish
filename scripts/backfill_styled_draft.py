# scripts/backfill_styled_draft.py
from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import text

from app.db import SessionLocal
from app.s3_client import S3Client


def iso_date_utc(dt: datetime | None = None) -> str:
    if not dt:
        dt = datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def derive_day_from_original(original_key: str) -> str:
    # original/YYYY-MM-DD/<doc_id>.pdf
    parts = (original_key or "").split("/", 2)
    if len(parts) >= 2 and parts[1]:
        return parts[1]
    return iso_date_utc()


def main(limit: int = 200):
    s3 = S3Client()
    db = SessionLocal()

    try:
        rows = db.execute(
            text(
                """
                SELECT id, original_s3_key
                FROM public.documents
                WHERE styled_draft_s3_key IS NULL
                  AND original_s3_key IS NOT NULL
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()

        if not rows:
            print("No documents missing styled drafts. ✅")
            return

        print(f"Found {len(rows)} documents missing styled drafts")

        updated = 0
        for r in rows:
            doc_id = r["id"]
            original_key = r["original_s3_key"]
            day = derive_day_from_original(original_key)
            styled_key = f"styled_draft/{day}/{doc_id}.pdf"

            # Copy in S3
            s3.copy_pdf(original_key, styled_key)

            # Update DB
            db.execute(
                text(
                    """
                    UPDATE public.documents
                    SET styled_draft_s3_key = :styled_key,
                        status = CASE
                          WHEN status IN ('NEW', 'PARSED') THEN 'READY_FOR_REVIEW'
                          ELSE status
                        END,
                        updated_at = now()
                    WHERE id = :id
                    """
                ),
                {"id": doc_id, "styled_key": styled_key},
            )
            updated += 1
            print(f"OK {doc_id}: {original_key} -> {styled_key}")

        db.commit()
        print(f"Backfill complete. Updated {updated} docs. ✅")

    finally:
        db.close()


if __name__ == "__main__":
    limit = int(os.getenv("LIMIT", "200"))
    main(limit=limit)