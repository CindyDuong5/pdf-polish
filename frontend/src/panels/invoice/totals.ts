// frontend/src/panels/invoice/totals.ts
import type { InvoiceFields } from "../../components/InvoiceEditor";

function parseMoney(v: any): number {
  const s = String(v ?? "").replace(/[^0-9.\-]/g, "").trim();
  const n = Number(s);
  return Number.isFinite(n) ? n : 0;
}

function money2(n: number): string {
  return `$${(Math.round(n * 100) / 100).toFixed(2)}`;
}

function parsePercent(v: any): number {
  const s = String(v ?? "").replace(/[^0-9.\-]/g, "").trim();
  const n = Number(s);
  return Number.isFinite(n) ? n / 100 : 0;
}

// money-safe getter (handles numbers AND "$123.45" strings)
function m(v: any): number {
  return typeof v === "number" && Number.isFinite(v) ? v : parseMoney(v);
}

export function recomputeInvoiceTotals(f: InvoiceFields): InvoiceFields {
  const laborSubtotal = (f.labor_rows || []).reduce((sum, r) => sum + m(r.price), 0);
  const partsSubtotal = (f.parts_rows || []).reduce((sum, r) => sum + m(r.price), 0);

  const taxableLabor = (f.labor_rows || []).reduce((sum, r) => sum + (r.taxable ? m(r.price) : 0), 0);
  const taxableParts = (f.parts_rows || []).reduce((sum, r) => sum + (r.taxable ? m(r.price) : 0), 0);
  const taxableSubtotal = taxableLabor + taxableParts;

  const subtotal = laborSubtotal + partsSubtotal;

  // ✅ Subtotal After Discount/Fees = subtotal + service fee - discount
  // (discount is expected to be entered as a positive number like "50" or "$50")
  const discount = m(f.discount);
  const serviceFee = m(f.service_fee);
  const after = subtotal + serviceFee - discount;

  const taxRate = parsePercent(f.sales_tax_rate) || 0.13;
  const tax = taxableSubtotal * taxRate;

  const total = after + tax;
  const paid = m(f.amount_paid);
  const balance = total - paid;

  return {
    ...f,
    taxable_subtotal: money2(taxableSubtotal),
    subtotal: money2(subtotal),
    subtotal_after_discount_fees: money2(after),
    tax_amount: money2(tax),
    total: money2(total),
    balance: money2(balance),
  };
}