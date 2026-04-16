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

export type ServiceQuoteItem = {
  name?: string;
  price?: string | number;
  description?: string;
};

export type ServiceQuoteFields = {
  quote_number?: string;
  quote_date?: string;
  expiry_date?: string;

  client_name?: string;
  client_email?: string;
  client_phone?: string;

  company_name?: string;
  company_address?: string;

  property_name?: string;
  property_address?: string;

  quote_description?: string;

  specific_exclusions?: string[];

  notes?: string;

  subtotal?: string | number;
  tax_rate?: string | number;
  tax?: string | number;
  tax_amount?: string | number;
  total?: string | number;

  items?: ServiceQuoteItem[];

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