// frontend/src/panels/invoice/totals.ts
import type { InvoiceFields } from "../../components/InvoiceEditor";

function parseMoney(v: any): number {
  const s = String(v ?? "").replace(/[^0-9.\-]/g, "").trim();
  const n = Number(s);
  return Number.isFinite(n) ? n : 0;
}

function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}

function money2(n: number): string {
  return `$${round2(n).toFixed(2)}`;
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
  const laborSubtotal = round2(
    (f.labor_rows || []).reduce((sum, r) => sum + m(r.price), 0)
  );

  const partsSubtotal = round2(
    (f.parts_rows || []).reduce((sum, r) => sum + m(r.price), 0)
  );

  const taxableLabor = round2(
    (f.labor_rows || []).reduce(
      (sum, r) => sum + (r.taxable ? m(r.price) : 0),
      0
    )
  );

  const taxableParts = round2(
    (f.parts_rows || []).reduce(
      (sum, r) => sum + (r.taxable ? m(r.price) : 0),
      0
    )
  );

  const subtotal = round2(laborSubtotal + partsSubtotal);

  const discount = round2(m(f.discount));      // expected positive
  const serviceFee = round2(m(f.service_fee)); // can be positive or negative
  const after = round2(subtotal + serviceFee - discount);

  const taxRate = parsePercent(f.sales_tax_rate) || 0.13;

  let taxableSubtotal = round2(taxableLabor + taxableParts + serviceFee - discount);
  if (taxableSubtotal < 0) taxableSubtotal = 0;

  const tax = round2(taxableSubtotal * taxRate);
  const total = round2(after + tax);

  const paid = round2(m(f.amount_paid));

  let balance = round2(total - paid);
  if (Math.abs(balance) < 0.005) balance = 0;

  return {
    ...f,
    taxable_subtotal: money2(taxableSubtotal),
    subtotal: money2(subtotal),
    subtotal_after_discount_fees: money2(after),
    tax_amount: money2(tax),
    total: money2(total),
    amount_paid: money2(paid),
    balance: money2(balance),
  };
}