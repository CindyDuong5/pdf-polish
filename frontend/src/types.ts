// frontend/src/types.ts
export type DocRow = {
  id: string;
  doc_type: string | null;
  status: string | null;
  customer_name: string | null;
  property_address: string | null;
  invoice_number: string | null;
  quote_number: string | null;
  job_report_number: string | null;
  created_at: string | null;
  original_s3_key: string | null;
  styled_draft_s3_key: string | null;
  final_s3_key: string | null;
  error: string | null;
};

export type Links = {
  id: string;
  doc_type: string;
  filename: string;
  original: { key: string | null; url: string | null };
  styled_draft: { key: string | null; url: string | null };
  final: { key: string | null; url: string | null };
};

// Service Quote editable shape (what backend returns)
export type SQItem = { name: string; price: string; description: string };

export type ServiceQuoteFields = {
  client_name: string;
  client_phone: string;
  client_email: string;

  company_name: string;
  company_address: string;

  property_name: string;
  property_address: string;

  quote_number: string;
  quote_date: string;
  quote_description: string;

  items: SQItem[];

  subtotal: string;
  tax: string;
  total: string;
};