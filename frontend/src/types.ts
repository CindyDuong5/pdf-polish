// frontend/src/types.ts
export type DocRow = {
  id: string;
  doc_type: string | null;
  status: string | null;

  customer_name: string | null;
  customer_email: string | null;
  property_address: string | null;

  invoice_number: string | null;
  quote_number: string | null;
  job_report_number: string | null;

  original_s3_key: string | null;
  styled_draft_s3_key: string | null;
  final_s3_key: string | null;

  sent_to: string | null;
  sent_cc: string | null;
  sent_bcc?: string | null;
  sent_at: string | null;

  created_at: string | null;
  updated_at: string | null;

  quote_po_number?: string | null;
  quote_note?: string | null;
  quote_reject_reason?: string | null;
  quote_responded_at?: string | null;

  error?: string | null;
};

export type Links = {
  id: string;
  doc_type: string;
  filename: string;
  original: { key: string | null; url: string | null };
  styled_draft: { key: string | null; url: string | null };
  final: { key: string | null; url: string | null };
};

export type ServiceQuoteLine = {
  qty?: string | number;
  description?: string;
  unit_price?: string | number;
  amount?: string | number;
};

export type ServiceQuoteFields = {
  quote_number?: string;
  quote_date?: string;
  expiry_date?: string;

  client_name?: string;
  client_email?: string;
  client_phone?: string;

  property_name?: string;
  property_address?: string;
  company_name?: string;

  scope_of_work?: string;
  exclusions?: string;
  notes?: string;

  subtotal?: string | number;
  tax_rate?: string | number;
  tax_amount?: string | number;
  total?: string | number;

  line_items?: ServiceQuoteLine[];

  [key: string]: any;
};

export type DocumentHistoryRow = {
  id: string;
  doc_type: string | null;
  status: string | null;
  invoice_number: string | null;
  quote_number: string | null;
  job_report_number: string | null;
  final_s3_key?: string | null;
  final_url?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};