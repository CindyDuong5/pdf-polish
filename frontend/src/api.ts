// frontend/src/api.ts
const API_BASE =
  import.meta.env.VITE_API_BASE_URL ||
  "https://pdf-polish-api-722522316664.northamerica-northeast1.run.app";

async function httpJson(url: string, init?: RequestInit) {
  const res = await fetch(url, init);
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {}
  if (!res.ok) {
    throw new Error(data?.detail || text || res.statusText);
  }
  return data;
}

export async function listDocuments(params: {
  q?: string;
  doc_type?: string;
  status?: string;
  limit?: number;
}) {
  const usp = new URLSearchParams();
  if (params.q) usp.set("q", params.q);
  if (params.doc_type) usp.set("doc_type", params.doc_type);
  if (params.status) usp.set("status", params.status);
  usp.set("limit", String(params.limit ?? 50));
  return httpJson(`${API_BASE}/api/documents?${usp.toString()}`);
}

export async function getLinks(docId: string) {
  return httpJson(`${API_BASE}/api/documents/${docId}/links`);
}

export async function restyleDoc(docId: string): Promise<{
  ok: boolean;
  doc_id: string;
  styled_draft_s3_key?: string | null;
  reused_existing?: boolean;
}> {
  return httpJson(`${API_BASE}/api/documents/${docId}/restyle`, { method: "POST" });
}

// fields + final
export async function getFields(docId: string): Promise<{
  doc_id: string;
  draft?: any;
  final?: any;
  source?: string;
  doc_type?: string;
}> {
  return httpJson(`${API_BASE}/api/documents/${docId}/fields`);
}

export async function saveFinal(docId: string, fields: any): Promise<{
  ok: boolean;
  doc_id: string;
  final_s3_key?: string | null;
  customer_email?: string | null;
  reused_existing?: boolean;
}> {
  return httpJson(`${API_BASE}/api/documents/${docId}/save-final`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fields }),
  });
}

// service quote email
export async function sendEmail(
  docId: string,
  payload: {
    cc?: string[];
    bcc?: string[];
    client_email?: string;
    deficiency_report_link?: string;
  }
): Promise<{
  ok: boolean;
  doc_id: string;
  to: string;
  cc: string[];
  bcc: string[];  
  url: string;
  sent_at?: string | null;
  template: string;
  reviewable: boolean;
  payment_url?: string | null;
  quote_number?: string | null;
}> {
  return httpJson(`${API_BASE}/api/documents/${docId}/send-email`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function sendInvoice(
  docId: string,
  payload?: { to?: string; cc?: string[]; bcc?: string[] }
) {
  return httpJson(`${API_BASE}/api/documents/${docId}/invoice/send`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
}

export async function lookupInvoiceByNumber(invoiceNumber: string) {
  const usp = new URLSearchParams({ number: String(invoiceNumber).trim() });
  return httpJson(`${API_BASE}/api/invoices/lookup?${usp.toString()}`);
}

export async function getInvoicePaymentLink(
  docId: string,
  payload?: { force_over_limit?: boolean }
) {
  return httpJson(`${API_BASE}/api/invoices/${docId}/payment-link`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
}

export async function acceptQuote(
  docId: string,
  payload: { token: string; quote_po_number?: string | null; quote_note?: string | null }
) {
  return httpJson(`${API_BASE}/api/documents/${docId}/accept`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function rejectQuote(docId: string, payload: { token: string; reason?: string | null }) {
  return httpJson(`${API_BASE}/api/documents/${docId}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getQuoteDecision(docId: string, token: string) {
  const qs = new URLSearchParams({ token }).toString();
  return httpJson(`${API_BASE}/api/documents/${docId}/quote-decision?${qs}`);
}

export async function buildInvoiceByNumber(invoiceNumber: string) {
  return httpJson(`${API_BASE}/api/invoices/build`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ invoice_number: invoiceNumber }),
  });
}

export async function saveFinalInvoice(docId: string, fields: any) {
  return httpJson(`${API_BASE}/api/documents/${docId}/invoice/save-final`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fields }),
  });
}

export function friendlyErrorMessage(e: any): string {
  const msg = e?.message || String(e) || "Something went wrong.";

  if (msg.includes("replaced by a newer version")) {
    return "This document has been replaced by a newer version. Please reopen the latest one.";
  }

  if (msg.includes("Please use the invoice send endpoint for invoices")) {
    return "This invoice must be sent from the invoice send flow.";
  }

  return msg;
}