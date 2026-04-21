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
  } catch {
    // ignore non-json response
  }

  if (!res.ok) {
    throw new Error(data?.detail || text || res.statusText);
  }

  return data;
}

/* ---------------- Shared / generic document types ---------------- */

export type ListDocumentsParams = {
  q?: string;
  doc_type?: string;
  status?: string;
  limit?: number;
};

export type RestyleDocResponse = {
  ok: boolean;
  doc_id: string;
  styled_draft_s3_key?: string | null;
  reused_existing?: boolean;
};

export type GetFieldsResponse = {
  doc_id: string;
  draft?: any;
  final?: any;
  source?: string;
  doc_type?: string;
};

export type SaveFinalResponse = {
  ok: boolean;
  doc_id: string;
  final_s3_key?: string | null;
  customer_email?: string | null;
  reused_existing?: boolean;
};

export type SendEmailPayload = {
  cc?: string[];
  bcc?: string[];
  client_email?: string;
  deficiency_report_link?: string;
  subject?: string;
};

export type SendEmailResponse = {
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
  subject?: string;
};

export type AcceptQuotePayload = {
  token: string;
  quote_po_number?: string | null;
  quote_note?: string | null;
};

export type RejectQuotePayload = {
  token: string;
  reason?: string | null;
};

/* ---------------- Invoice types ---------------- */

export type InvoiceRecipientSource =
  | "property"
  | "customer"
  | "bill_client"
  | "manual"
  | "snowflake_error"
  | string;

export type InvoiceRecipientItem = {
  email?: string;
  full_name?: string;
  role?: string;
  source?: string;
  selected?: boolean;
  [key: string]: any;
};

export type BuildInvoiceResponse = {
  ok: boolean;
  doc_id: string;
  invoice_number?: string | null;
  styled_draft_s3_key?: string | null;
  url?: string | null;
  payment_url?: string | null;
  property_id?: string | null;
  customer_id?: string | null;
  invoice_recipient_to?: string | null;
  invoice_recipient_cc?: string[];
  property_rep_to?: string | null;
  property_rep_cc?: string[];
  recipient_source?: InvoiceRecipientSource | null;
  recipient_message?: string | null;
};

export type SaveFinalInvoiceResponse = {
  ok: boolean;
  final_s3_key?: string | null;
  status?: string | null;
  payment_url?: string | null;
  property_id?: string | null;
  customer_id?: string | null;
  invoice_recipient_to?: string | null;
  invoice_recipient_cc?: string[];
  property_rep_to?: string | null;
  property_rep_cc?: string[];
  recipient_source?: InvoiceRecipientSource | null;
  recipient_message?: string | null;
};

export type SendInvoicePayload = {
  to?: string;
  cc?: string[];
  bcc?: string[];
  subject?: string;
};

export type SendInvoiceResponse = {
  ok: boolean;
  doc_id: string;
  to: string;
  cc: string[];
  bcc: string[];
  subject?: string | null;
  sent_at?: string | null;
  status?: string | null;
  payment_url?: string | null;

  property_id?: string | null;
  customer_id?: string | null;

  invoice_recipient_to?: string | null;
  invoice_recipient_cc?: string[];
  invoice_recipient_all_emails?: string[];

  property_rep_to?: string | null;
  property_rep_cc?: string[];
  property_rep_all_emails?: string[];

  recipient_source?: InvoiceRecipientSource | null;
  recipient_message?: string | null;
  recipient_items?: InvoiceRecipientItem[];

  additional_document_names?: string[];
};

export type GetInvoicePaymentLinkPayload = {
  force_over_limit?: boolean;
};

export type GetInvoicePaymentLinkResponse = {
  ok?: boolean;
  payment_url?: string | null;
  [key: string]: any;
};

/* ---------------- Additional documents types ---------------- */

export type AdditionalDocumentItem = {
  id: string;
  document_id: string;
  display_name: string;
  source_type: "upload" | "url";
  storage_key: string;
  original_filename?: string | null;
  content_type?: string | null;
  file_size?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ListAdditionalDocumentsResponse = {
  items: AdditionalDocumentItem[];
};

export type UploadAdditionalDocumentResponse = {
  ok: boolean;
  item: AdditionalDocumentItem;
};

export type AddAdditionalDocumentByUrlPayload = {
  file_url: string;
  display_name: string;
};

export type DeleteAdditionalDocumentResponse = {
  ok: boolean;
};

export type ListDocumentHistoryParams = {
  limit?: number;
  q?: string;
};

/* ---------------- Proposal types ---------------- */

export type ProposalCustomer = {
  customer_id: string;
  customer_name: string | null;
  customer_code: string | null;
  customer_type: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  full_address: string | null;
  email: string | null;
  phone_primary: string | null;
  phone_alternate: string | null;
};

export type ProposalProperty = {
  customer_id: string;
  customer_name: string | null;
  property_id: string;
  property_name: string | null;
  property_address: string | null;
  property_city: string | null;
  property_state: string | null;
  property_postal_code: string | null;
  property_country: string | null;
  property_full_address: string | null;
};

export type ProposalCustomerSearchResponse = {
  ok: boolean;
  query: string;
  count: number;
  items: ProposalCustomer[];
};

export type ProposalPropertyListResponse = {
  ok: boolean;
  customer_id: string;
  count: number;
  items: ProposalProperty[];
};

export type ProposalItem = {
  item: string;
  description: string;
  price: string;
};

export type ProposalStaticFields = {
  proposal_number: string;
  proposal_date: string;
  proposal_type: string;

  customer_id: string;
  customer_name: string;
  customer_address: string;

  property_id: string;
  property_name: string;
  property_address: string;

  contact_name: string;
  contact_email: string;
  contact_phone: string;

  prepared_by: string;
  scope_summary: string;
  exclusions: string;

  subtotal: string;
  tax_rate: string;
  tax: string;
  total: string;

  items: ProposalItem[];
};

export type BuildProposalResponse = {
  ok: boolean;
  doc_id: string;
  doc_type: string;
  proposal_number?: string | null;
  quote_number?: string | null;
  styled_draft_s3_key?: string | null;
  url?: string | null;
  fields?: any;
};

export type SaveFinalProposalResponse = {
  ok: boolean;
  doc_id: string;
  doc_type?: string | null;
  proposal_number?: string | null;
  quote_number?: string | null;
  final_s3_key?: string | null;
  customer_email?: string | null;
};

/* ---------------- Generic document APIs ---------------- */

export async function listDocuments(params: ListDocumentsParams) {
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

export async function restyleDoc(docId: string): Promise<RestyleDocResponse> {
  return httpJson(`${API_BASE}/api/documents/${docId}/restyle`, {
    method: "POST",
  });
}

export async function getFields(docId: string): Promise<GetFieldsResponse> {
  return httpJson(`${API_BASE}/api/documents/${docId}/fields`);
}

export async function saveFinal(
  docId: string,
  fields: any
): Promise<SaveFinalResponse> {
  return httpJson(`${API_BASE}/api/documents/${docId}/save-final`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fields }),
  });
}

/* ---------------- Quote / proposal email ---------------- */

export async function sendEmail(
  docId: string,
  payload: SendEmailPayload
): Promise<SendEmailResponse> {
  return httpJson(`${API_BASE}/api/documents/${docId}/send-email`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function acceptQuote(docId: string, payload: AcceptQuotePayload) {
  return httpJson(`${API_BASE}/api/documents/${docId}/accept`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function rejectQuote(docId: string, payload: RejectQuotePayload) {
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

/* ---------------- Invoice APIs ---------------- */

export async function sendInvoice(
  docId: string,
  payload?: SendInvoicePayload
): Promise<SendInvoiceResponse> {
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
  payload?: GetInvoicePaymentLinkPayload
): Promise<GetInvoicePaymentLinkResponse> {
  return httpJson(`${API_BASE}/api/invoices/${docId}/payment-link`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
}

export async function buildInvoiceByNumber(
  invoiceNumber: string
): Promise<BuildInvoiceResponse> {
  return httpJson(`${API_BASE}/api/invoices/build`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ invoice_number: invoiceNumber }),
  });
}

export async function saveFinalInvoice(
  docId: string,
  fields: any
): Promise<SaveFinalInvoiceResponse> {
  return httpJson(`${API_BASE}/api/documents/${docId}/invoice/save-final`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fields }),
  });
}

/* ---------------- Proposal APIs ---------------- */

export async function searchProposalCustomers(
  q: string,
  limit = 20
): Promise<ProposalCustomerSearchResponse> {
  const params = new URLSearchParams({
    q,
    limit: String(limit),
  });

  return httpJson(
    `${API_BASE}/api/proposals/customers/search?${params.toString()}`
  );
}

export async function getProposalProperties(
  customerId: string
): Promise<ProposalPropertyListResponse> {
  return httpJson(`${API_BASE}/api/proposals/customers/${customerId}/properties`);
}

export async function buildProposal(
  fields: ProposalStaticFields
): Promise<BuildProposalResponse> {
  return httpJson(`${API_BASE}/api/proposals/build`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fields }),
  });
}

export async function saveFinalProposal(
  docId: string,
  fields: ProposalStaticFields
): Promise<SaveFinalProposalResponse> {
  return httpJson(`${API_BASE}/api/documents/${docId}/proposal/save-final`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fields }),
  });
}

/* ---------------- Friendly errors ---------------- */

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

/* ---------------- Additional documents ---------------- */

export async function listAdditionalDocuments(
  docId: string
): Promise<ListAdditionalDocumentsResponse> {
  return httpJson(`${API_BASE}/api/documents/${docId}/additional-documents`);
}

export async function uploadAdditionalDocument(
  docId: string,
  file: File,
  displayName: string
): Promise<UploadAdditionalDocumentResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("display_name", displayName);

  const res = await fetch(
    `${API_BASE}/api/documents/${docId}/additional-documents/upload`,
    {
      method: "POST",
      body: form,
    }
  );

  const text = await res.text();

  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    // ignore non-json response
  }

  if (!res.ok) {
    throw new Error(data?.detail || text || res.statusText);
  }

  return data;
}

export async function addAdditionalDocumentByUrl(
  docId: string,
  payload: AddAdditionalDocumentByUrlPayload
): Promise<UploadAdditionalDocumentResponse> {
  return httpJson(
    `${API_BASE}/api/documents/${docId}/additional-documents/by-url`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export async function deleteAdditionalDocument(
  docId: string,
  additionalDocId: string
): Promise<DeleteAdditionalDocumentResponse> {
  return httpJson(
    `${API_BASE}/api/documents/${docId}/additional-documents/${additionalDocId}`,
    {
      method: "DELETE",
    }
  );
}

/* ---------------- History ---------------- */

export async function listDocumentHistory(params?: ListDocumentHistoryParams) {
  const usp = new URLSearchParams();
  usp.set("limit", String(params?.limit ?? 300));

  if (params?.q?.trim()) {
    usp.set("q", params.q.trim());
  }

  return httpJson(`${API_BASE}/api/documents/history?${usp.toString()}`);
}