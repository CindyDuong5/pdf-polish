// frontend/src/uiLabels.ts

import type { DocRow, DocumentHistoryRow } from "./types";

type AnyDoc = Partial<DocRow & DocumentHistoryRow>;

export function getDisplayDocType(row: AnyDoc): string {
  const dt = String(row.doc_type || "").toUpperCase();

  if (dt.includes("SERVICE_QUOTE")) return "Service Quote";
  if (dt.includes("PROJECT_QUOTE")) return "Proposal";
  if (dt.includes("QUOTE")) return "Quote";
  if (dt.includes("INVOICE")) return "Invoice";

  return row.doc_type || "Unknown";
}

export function getDocTypeClass(row: AnyDoc): string {
  const label = getDisplayDocType(row);

  switch (label) {
    case "Invoice":
      return "docTypeInvoice";
    case "Service Quote":
      return "docTypeServiceQuote";
    case "Proposal":
      return "docTypeProposal";
    case "Quote":
      return "docTypeQuote";
    default:
      return "docTypeUnknown";
  }
}

export function getDisplayStatus(row: AnyDoc): string {
  const raw = String(row.status || "").toUpperCase().trim();

  if (
    raw === "NEW" ||
    raw === "READY_FOR_REVIEW" ||
    raw === "READY FOR REVIEW"
  ) {
    return "NEW";
  }

  if (raw === "SENT") return "SENT";
  if (raw === "DECLINED" || raw === "REJECTED") return "DECLINED";
  if (raw === "APPROVED") return "APPROVED";
  if (raw === "DRAFT") return "DRAFT";
  if (raw === "PAID") return "PAID";
  if (raw === "FINALIZED") return "FINALIZED";

  return raw || "-";
}

export function getStatusClass(status: string): string {
  const normalized = String(status || "").toUpperCase().trim();

  switch (normalized) {
    case "NEW":
      return "statusNew";
    case "SENT":
      return "statusSent";
    case "DECLINED":
      return "statusDeclined";
    case "APPROVED":
      return "statusApproved";
    case "DRAFT":
      return "statusDraft";
    case "PAID":
      return "statusPaid";
    case "FINALIZED":
      return "statusFinalized";
    default:
      return "statusDraft";
  }
}

export function getDisplayEmailStatus(row: AnyDoc): string {
  const label = String((row as any).email_status_label || "").trim();
  if (label) return label;

  const raw = String((row as any).email_status || "").toUpperCase().trim();

  if (!raw) {
    return row.sent_at ? "Sent - waiting for update" : "Not sent";
  }

  if (raw === "SENT") return "Sent";
  if (raw === "DELIVERED") return "Delivered";
  if (raw === "OPENED") return "Opened";
  if (raw === "CLICKED") return "Clicked";

  if (raw === "AUTO_OPENED") return "Auto-opened";
  if (raw === "SOFT_BOUNCED") return "Temporary delivery issue";
  if (raw === "HARD_BOUNCED") return "Failed - bad email address";
  if (raw === "FAILED") return "Failed";
  if (raw === "SPAM_COMPLAINT") return "Marked as spam";
  if (raw === "UNSUBSCRIBED") return "Unsubscribed";

  return raw;
}

export function getEmailStatusClass(row: AnyDoc): string {
  const raw = String((row as any).email_status || "").toUpperCase().trim();

  if (!raw) return row.sent_at ? "emailStatusPending" : "emailStatusNone";

  switch (raw) {
    case "DELIVERED":
    case "OPENED":
    case "CLICKED":
      return "emailStatusGood";

    case "SENT":
    case "AUTO_OPENED":
      return "emailStatusPending";

    case "SOFT_BOUNCED":
      return "emailStatusWarning";

    case "HARD_BOUNCED":
    case "FAILED":
    case "SPAM_COMPLAINT":
    case "UNSUBSCRIBED":
      return "emailStatusBad";

    default:
      return "emailStatusPending";
  }
}