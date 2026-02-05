# app/worker.py
from __future__ import annotations

import argparse
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import InboundEmail, Document
from app.gmail_client import GmailClient
from app.s3_client import S3Client


LABEL_TO_DOC_TYPE = {
    "buildops/invoice": "INVOICE",
    "buildops/quote_service": "SERVICE_QUOTE",
    "buildops/quote_project": "PROJECT_QUOTE",
    "buildops/report": "JOB_REPORT",
}


def iso_date_utc(dt: datetime | None) -> str:
    if not dt:
        dt = datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, help="Gmail label name, e.g. buildops/invoice")
    parser.add_argument("--max", type=int, default=10, help="Max messages to process")
    args = parser.parse_args()

    label = args.label
    doc_type = LABEL_TO_DOC_TYPE.get(label, "OTHER")

    gmail = GmailClient()
    s3 = S3Client()

    message_ids = gmail.list_message_ids_by_label(label_name=label, max_results=args.max)
    print(f"Found {len(message_ids)} messages for label '{label}'")

    db = SessionLocal()
    try:
        for mid in message_ids:
            meta = gmail.fetch_message_meta(mid)

            # 1) Idempotent insert: inbound_emails.gmail_message_id is UNIQUE
            inbound = InboundEmail(
                gmail_message_id=meta.message_id,
                from_email=meta.from_email,
                subject=meta.subject,
                received_at=meta.internal_date,
                status="NEW",
                raw_meta={
                    "thread_id": meta.thread_id,
                    "label": label,
                },
            )

            db.add(inbound)
            try:
                db.commit()
                db.refresh(inbound)
                created = True
            except IntegrityError:
                db.rollback()
                created = False

            if not created:
                print(f"SKIP (already ingested): {mid}")
                continue

            # 2) Download PDF attachments
            pdfs = gmail.download_pdf_attachments(mid)
            if not pdfs:
                # Mark inbound email as parsed but no attachments
                inbound.status = "PARSED"
                inbound.error = "No PDF attachments found"
                db.commit()
                print(f"WARN: No PDFs found for message {mid}")
                continue

            # 3) For each PDF, upload to S3 + create Document row
            for filename, pdf_bytes in pdfs:
                doc_id = uuid.uuid4()
                day = iso_date_utc(meta.internal_date)
                s3_key = f"original/{day}/{doc_id}.pdf"

                s3.upload_pdf_bytes(s3_key, pdf_bytes)

                doc = Document(
                    id=doc_id,
                    inbound_email_id=inbound.id,
                    doc_type=doc_type,
                    property_address=None,  # fill later (Phase 4)
                    customer_name=None,
                    customer_email=None,
                    invoice_number=None,
                    quote_number=None,
                    job_report_number=None,
                    original_s3_key=s3_key,
                    styled_draft_s3_key=None,
                    final_s3_key=None,
                    status="NEW",
                    extracted_fields={
                        "source_filename": filename,
                        "gmail_message_id": meta.message_id,
                        "label": label,
                    },
                )
                db.add(doc)
                db.commit()
                print(f"OK: saved {filename} -> s3://{s3.bucket}/{s3_key} (doc_id={doc_id})")

            inbound.status = "PARSED"
            db.commit()

    finally:
        db.close()


if __name__ == "__main__":
    main()
