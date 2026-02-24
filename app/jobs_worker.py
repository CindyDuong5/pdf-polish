# app/jobs_worker.py
from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import InboundEmail, Document
from app.gmail_client import GmailClient
from app.s3_client import S3Client


def iso_date_utc(dt: datetime | None) -> str:
    if not dt:
        dt = datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def make_styled_draft_key(original_key: str, doc_id: uuid.UUID) -> str:
    """
    Keep date partition consistent with original:
      original/YYYY-MM-DD/<doc_id>.pdf
      styled_draft/YYYY-MM-DD/<doc_id>.pdf
    """
    parts = original_key.split("/", 2)
    day = parts[1] if len(parts) >= 2 else iso_date_utc(None)
    return f"styled_draft/{day}/{doc_id}.pdf"


@dataclass
class ClaimedJob:
    id: int
    gmail_message_id: str


CLAIM_SQL = """
with job as (
  select id
  from gmail_jobs
  where status='QUEUED'
  order by created_at asc
  limit 1
  for update skip locked
)
update gmail_jobs
set status='PROCESSING', updated_at=now(), error=null
where id in (select id from job)
returning id, gmail_message_id;
"""

MARK_DONE_SQL = """
update gmail_jobs
set status='DONE', updated_at=now(), error=null
where id=:job_id;
"""

MARK_ERROR_SQL = """
update gmail_jobs
set status='ERROR', updated_at=now(), error=:err
where id=:job_id;
"""


def claim_one(db) -> Optional[ClaimedJob]:
    row = db.execute(text(CLAIM_SQL)).mappings().first()
    if not row:
        return None
    return ClaimedJob(id=row["id"], gmail_message_id=row["gmail_message_id"])


def mark_done(db, job_id: int) -> None:
    db.execute(text(MARK_DONE_SQL), {"job_id": job_id})
    db.commit()


def mark_error(db, job_id: int, err: str) -> None:
    db.execute(text(MARK_ERROR_SQL), {"job_id": job_id, "err": err[:1000]})
    db.commit()


def document_exists_for_inbound(db, inbound_id, filename: str) -> bool:
    """
    Prevent duplicate Document rows if the same gmail job replays.
    Uses extracted_fields->>'source_filename' as a simple idempotency key.
    """
    sql = text(
        """
        SELECT 1
        FROM public.documents
        WHERE inbound_email_id = :inbound_id
          AND extracted_fields->>'source_filename' = :filename
        LIMIT 1
        """
    )
    row = db.execute(sql, {"inbound_id": inbound_id, "filename": filename}).first()
    return row is not None


def main(max_jobs: int = 10) -> int:
    gmail = GmailClient()
    s3 = S3Client()

    processed = 0
    db = SessionLocal()

    try:
        for _ in range(max_jobs):
            job = claim_one(db)
            if not job:
                print("No queued jobs.")
                break

            print(f"Claimed job {job.id} gmail_message_id={job.gmail_message_id}")

            try:
                # 1) Fetch message meta + attachments by gmail_message_id
                meta = gmail.fetch_message_meta(job.gmail_message_id)
                pdfs = gmail.download_pdf_attachments(job.gmail_message_id)
                print(f"Found {len(pdfs)} PDF attachments")
                
                # 2) Idempotent inbound insert (UNIQUE gmail_message_id)
                inbound = InboundEmail(
                    gmail_message_id=meta.message_id,
                    from_email=meta.from_email,
                    subject=meta.subject,
                    received_at=meta.internal_date,
                    status="NEW",
                    raw_meta={"thread_id": meta.thread_id},
                )
                db.add(inbound)

                try:
                    db.commit()
                    db.refresh(inbound)
                    created = True
                except IntegrityError:
                    db.rollback()
                    created = False
                    inbound = (
                        db.query(InboundEmail)
                        .filter(InboundEmail.gmail_message_id == meta.message_id)
                        .first()
                    )
                    if not inbound:
                        raise RuntimeError(
                            f"Duplicate gmail_message_id but inbound row not found: {meta.message_id}"
                        )

                if created:
                    print(f"Inbound created: id={inbound.id} gmail_message_id={meta.message_id}")
                else:
                    print(f"Inbound reused:  id={inbound.id} gmail_message_id={meta.message_id}")

                # 3) Handle no PDFs
                if not pdfs:
                    inbound.status = "PARSED"
                    inbound.error = "No PDF attachments found"
                    db.commit()
                    mark_done(db, job.id)
                    print(f"Job {job.id}: DONE (no PDFs)")
                    processed += 1
                    continue

                # 4) Upload PDFs + create Document rows (idempotent per inbound+filename)
                for filename, pdf_bytes in pdfs:
                    if document_exists_for_inbound(db, inbound.id, filename):
                        print(f"SKIP doc (already exists for inbound {inbound.id}): {filename}")
                        continue

                    doc_id = uuid.uuid4()
                    day = iso_date_utc(meta.internal_date)

                    original_key = f"original/{day}/{doc_id}.pdf"
                    s3.upload_pdf_bytes(original_key, pdf_bytes)

                    styled_key = make_styled_draft_key(original_key, doc_id)
                    s3.copy_pdf(original_key, styled_key)

                    doc = Document(
                        id=doc_id,
                        inbound_email_id=inbound.id,
                        doc_type="OTHER",
                        property_address=None,
                        customer_name=None,
                        customer_email=None,
                        invoice_number=None,
                        quote_number=None,
                        job_report_number=None,
                        original_s3_key=original_key,
                        styled_draft_s3_key=styled_key,
                        final_s3_key=None,
                        status="READY_FOR_REVIEW",
                        extracted_fields={
                            "source_filename": filename,
                            "gmail_message_id": meta.message_id,
                        },
                    )
                    db.add(doc)
                    db.commit()

                    print(f"Uploaded {filename} -> s3://{s3.bucket}/{original_key}")
                    print(f"Draft ready -> s3://{s3.bucket}/{styled_key}")

                inbound.status = "PARSED"
                db.commit()

                mark_done(db, job.id)
                print(f"Job {job.id}: DONE")
                processed += 1

            except Exception as e:
                db.rollback()
                err = f"{type(e).__name__}: {e}"
                print(f"Job {job.id}: ERROR {err}", file=sys.stderr)
                mark_error(db, job.id, err)

        return processed

    finally:
        db.close()


def guess_kind(subject: str | None, filename: str | None) -> str:
    s = (subject or "").lower()
    f = (filename or "").lower()

    if "invoice" in s or "invoice" in f:
        return "invoice"
    if "quote" in s or "quote" in f:
        return "quote"
    if "report" in s or "job report" in s or "report" in f:
        return "job"
    return "invoice"  # default


if __name__ == "__main__":
    # Allow override from env (Cloud Run Job)
    max_jobs = int(os.getenv("MAX_JOBS", "10"))
    main(max_jobs=max_jobs)