// frontend/src/panels/serviceQuote/totals.ts
import type { ServiceQuoteFields } from "../../types";

const DEFAULT_TAX_RATE = 0.13;

function parseMoney(v: string | number | undefined | null): number {
  const t = String(v ?? "").replace(/[^0-9.\-]/g, "").trim();
  const n = Number(t);
  return Number.isFinite(n) ? n : 0;
}

function money2(n: number): string {
  return (Math.round(n * 100) / 100).toFixed(2);
}

export function withComputedTotals(f: ServiceQuoteFields): ServiceQuoteFields {
  const items = Array.isArray(f.items) ? f.items : [];

  const itemsSubtotal = items.reduce((sum: number, it: any) => {
    return sum + parseMoney(it?.price);
  }, 0);

  const subtotal = Math.round(itemsSubtotal * 100) / 100;
  const tax = Math.round(subtotal * DEFAULT_TAX_RATE * 100) / 100;
  const total = Math.round((subtotal + tax) * 100) / 100;

  return {
    ...f,
    subtotal: money2(subtotal),
    tax: money2(tax),
    total: money2(total),
  };
}