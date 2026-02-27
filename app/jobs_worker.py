# app/jobs_worker.py
from __future__ import annotations

import io
import re
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
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


def styled_draft_key_from_original(original_key: str, doc_id: uuid.UUID) -> str:
    parts = original_key.split("/")
    day = parts[1] if len(parts) >= 3 else iso_date_utc(None)
    return f"styled_draft/{day}/{doc_id}.pdf"


def stamp_pdf_bytes(pdf_bytes: bytes, text_to_stamp: str) -> bytes:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()

    for page in reader.pages:
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)

        overlay_buf = io.BytesIO()
        c = canvas.Canvas(overlay_buf, pagesize=(w, h))

        c.saveState()
        c.setFont("Helvetica-Bold", 42)
        c.translate(w / 2, h / 2)
        c.rotate(25)
        c.drawCentredString(0, 0, text_to_stamp)
        c.restoreState()

        c.setFont("Helvetica-Bold", 14)
        c.drawRightString(w - 24, h - 24, text_to_stamp)

        c.save()
        overlay_buf.seek(0)

        overlay_reader = PdfReader(overlay_buf)
        overlay_page = overlay_reader.pages[0]
        page.merge_page(overlay_page)

        writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


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


def guess_kind(subject: str | None, filename: str | None) -> str:
    """
    Determine Document.doc_type from subject + filename.
    Matches your schema:
      INVOICE | SERVICE_QUOTE | PROJECT_QUOTE | JOB_REPORT | OTHER

    Priority:
      INVOICE > JOB_REPORT > SERVICE_QUOTE/PROJECT_QUOTE > OTHER
    """
    s = (subject or "").lower()
    f = (filename or "").lower()
    hay = f"{f} {s}"
    hay = re.sub(r"[\-_]+", " ", hay)

    # 1) Invoice
    if "invoice" in hay:
        return "INVOICE"

    # 2) Job report (more strict than "report" alone)
    if "job report" in hay or ("job" in hay and "report" in hay):
        return "JOB_REPORT"

    # 3) Quotes
    if "project quote" in hay:
        return "PROJECT_QUOTE"

    if "service quote" in hay or "quote service" in hay:
        return "SERVICE_QUOTE"

    # 4) Generic "quote" fallback
    if "quote" in hay:
        return "SERVICE_QUOTE"  # choose your default

    return "OTHER"

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
                meta = gmail.fetch_message_meta(job.gmail_message_id)
                pdfs = gmail.download_pdf_attachments(job.gmail_message_id)
                print(f"Found {len(pdfs)} PDF attachments")

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

                print(
                    f"Inbound {'created' if created else 'reused'}: id={inbound.id} gmail_message_id={meta.message_id}"
                )

                if not pdfs:
                    inbound.status = "PARSED"
                    inbound.error = "No PDF attachments found"
                    db.commit()
                    mark_done(db, job.id)
                    print(f"Job {job.id}: DONE (no PDFs)")
                    processed += 1
                    continue

                for filename, pdf_bytes in pdfs:
                    if document_exists_for_inbound(db, inbound.id, filename):
                        print(f"SKIP doc (already exists for inbound {inbound.id}): {filename}")
                        continue

                    doc_id = uuid.uuid4()
                    day = iso_date_utc(meta.internal_date)

                    original_key = f"original/{day}/{doc_id}.pdf"
                    s3.upload_pdf_bytes(original_key, pdf_bytes)

                    # Create a simple stamped draft right away (so frontend can preview)
                    draft_key = styled_draft_key_from_original(original_key, doc_id)
                    draft_bytes = stamp_pdf_bytes(pdf_bytes, "RESTYLED DRAFT")
                    s3.upload_pdf_bytes(draft_key, draft_bytes)

                    doc_type_guess = guess_kind(meta.subject, filename)
                    print("DOC TYPE GUESS:", doc_type_guess, "| subject=", meta.subject, "| filename=", filename)

                    doc = Document(
                        id=doc_id,
                        inbound_email_id=inbound.id,
                        doc_type=doc_type_guess,
                        property_address=None,
                        customer_name=None,
                        customer_email=None,
                        invoice_number=None,
                        quote_number=None,
                        job_report_number=None,
                        original_s3_key=original_key,
                        styled_draft_s3_key=draft_key,
                        final_s3_key=None,
                        status="READY_FOR_REVIEW",
                        extracted_fields={
                            "source_filename": filename,
                            "gmail_message_id": meta.message_id,
                            "doc_type_guess": doc_type_guess,
                        },
                    )
                    db.add(doc)
                    db.commit()

                    print(f"Uploaded {filename} -> s3://{s3.bucket}/{original_key}")
                    print(f"Draft created -> s3://{s3.bucket}/{draft_key}")
                    print("Doc status=READY_FOR_REVIEW")

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


if __name__ == "__main__":
    max_jobs = int(os.getenv("MAX_JOBS", "10"))
    main(max_jobs=max_jobs)