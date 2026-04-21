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