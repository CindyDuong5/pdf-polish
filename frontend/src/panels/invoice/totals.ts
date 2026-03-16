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

function m(v: any): number {
  return typeof v === "number" && Number.isFinite(v) ? v : parseMoney(v);
}

/**
 * Manual UI recompute rule:
 * tax is based on taxable labor + taxable parts + service fee - discount
 */
export function recomputeInvoiceTotals(f: InvoiceFields): InvoiceFields {
  const laborSubtotal = (f.labor_rows || []).reduce((sum, r) => sum + m(r.price), 0);
  const partsSubtotal = (f.parts_rows || []).reduce((sum, r) => sum + m(r.price), 0);

  const taxableLabor = (f.labor_rows || []).reduce(
    (sum, r) => sum + (r.taxable ? m(r.price) : 0),
    0
  );
  const taxableParts = (f.parts_rows || []).reduce(
    (sum, r) => sum + (r.taxable ? m(r.price) : 0),
    0
  );

  const subtotal = laborSubtotal + partsSubtotal;

  const discount = m(f.discount);      // expected positive, e.g. 50
  const serviceFee = m(f.service_fee); // can be positive or negative
  const after = subtotal + serviceFee - discount;

  const taxRate = parsePercent(f.sales_tax_rate) || 0.13;

  // ✅ include fee + discount in taxable base
  let taxableSubtotal = taxableLabor + taxableParts + serviceFee - discount;

  // optional safety: don't allow negative taxable base
  if (taxableSubtotal < 0) taxableSubtotal = 0;

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