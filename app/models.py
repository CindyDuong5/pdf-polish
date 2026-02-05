# app/models.py
import uuid
from datetime import datetime

from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
    Index,
    BigInteger,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class InboundEmail(Base):
    __tablename__ = "inbound_emails"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Gmail message id (idempotency key)
    gmail_message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    from_email: Mapped[str | None] = mapped_column(String(320))
    subject: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # NEW | PARSED | ERROR
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NEW")
    error: Mapped[str | None] = mapped_column(Text)

    raw_meta: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    documents = relationship("Document", back_populates="inbound_email")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    inbound_email_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inbound_emails.id")
    )

    # INVOICE | SERVICE_QUOTE | PROJECT_QUOTE | JOB_REPORT | OTHER
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False, default="OTHER")

    # Address / property name (single field is enough)
    property_address: Mapped[str | None] = mapped_column(Text)

    customer_name: Mapped[str | None] = mapped_column(Text)
    customer_email: Mapped[str | None] = mapped_column(String(320))

    invoice_number: Mapped[str | None] = mapped_column(String(64))
    quote_number: Mapped[str | None] = mapped_column(String(64))
    job_report_number: Mapped[str | None] = mapped_column(String(64))

    # S3 keys (not full URLs)
    original_s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    styled_draft_s3_key: Mapped[str | None] = mapped_column(Text)
    final_s3_key: Mapped[str | None] = mapped_column(Text)

    # NEW | READY_FOR_REVIEW | NEEDS_EDIT | FINALIZED | SENT | ERROR
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NEW")
    error: Mapped[str | None] = mapped_column(Text)

    extracted_fields: Mapped[dict | None] = mapped_column(JSONB)
    user_overrides: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    inbound_email = relationship("InboundEmail", back_populates="documents")
    send_jobs = relationship("SendJob", back_populates="document")
    quote_decision = relationship("QuoteDecision", back_populates="document", uselist=False)

    __table_args__ = (
        Index("idx_documents_doc_type", "doc_type"),
        Index("idx_documents_status", "status"),
        Index("idx_documents_customer_email", "customer_email"),
        Index("idx_documents_invoice_number", "invoice_number"),
        Index("idx_documents_quote_number", "quote_number"),
        Index("idx_documents_job_report_number", "job_report_number"),
    )


class SendJob(Base):
    __tablename__ = "send_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)

    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    from_email: Mapped[str] = mapped_column(String(320), nullable=False, default="support@mainlinefire.com")

    ses_message_id: Mapped[str | None] = mapped_column(String(255), index=True)

    # QUEUED | SENT | DELIVERED | BOUNCED | COMPLAINT | FAILED
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")
    error: Mapped[str | None] = mapped_column(Text)

    provider_payload: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    document = relationship("Document", back_populates="send_jobs")

    __table_args__ = (
        Index("idx_send_jobs_status", "status"),
        Index("idx_send_jobs_ses_message_id", "ses_message_id"),
    )


class QuoteDecision(Base):
    __tablename__ = "quote_decisions"

    # 1:1 with Document
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"), primary_key=True)

    # ACCEPTED | REJECTED
    decision: Mapped[str] = mapped_column(String(16), nullable=False)

    po_number: Mapped[str | None] = mapped_column(String(128))
    note: Mapped[str | None] = mapped_column(Text)

    reject_reason: Mapped[dict | None] = mapped_column(JSONB)


    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    decided_by_email: Mapped[str | None] = mapped_column(String(320))

    document = relationship("Document", back_populates="quote_decision")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # e.g. "document.updated", "document.sent", "quote.accepted"
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_email: Mapped[str | None] = mapped_column(String(320))

    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"))
    send_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("send_jobs.id"))

    meta: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("idx_audit_action", "action"),
        Index("idx_audit_document_id", "document_id"),
    )


# =========================
# NEW (Step 1) — Gmail Push State + Queue
# =========================

class GmailState(Base):
    """
    Stores the rolling Gmail history cursor so push processing is incremental.
    Keep only one row (id='main') for the mailbox.
    """
    __tablename__ = "gmail_state"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="main")
    last_history_id: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class GmailJob(Base):
    """
    Queue of Gmail messages to ingest.
    Cloud Run enqueues gmail_message_id, AWS worker processes them.
    """
    __tablename__ = "gmail_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # idempotency key from Gmail
    gmail_message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # optional label/doc_type hint (nice-to-have)
    label: Mapped[str | None] = mapped_column(String(128))

    # QUEUED | PROCESSING | DONE | ERROR
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")
    error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        Index("idx_gmail_jobs_status", "status"),
    )
