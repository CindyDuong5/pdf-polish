// frontend/src/components/InvoiceEditor.tsx
import React, { useMemo } from "react";
import { recomputeInvoiceTotals } from "../panels/invoice/totals";

type LaborRow = {
  date?: string;
  name?: string;
  description?: string;
  taxable?: boolean;
  hours?: number;
  rate?: number;
  price?: number | string;
};

type PartRow = {
  date?: string;
  name?: string;
  code?: string;
  description?: string;
  taxable?: boolean;
  qty?: number;
  unit_price?: number;
  price?: number | string;
};

export type InvoiceFields = {
  invoice_number?: string;
  issued_date?: string;
  due_date?: string;

  billClient_name?: string;
  billClient_email?: string;
  billClient_phone?: string;
  billClient_address_lines?: string[];

  property_name?: string;
  property_address_lines?: string[];

  job_number?: string;
  po_number?: string;
  authorized_by?: string;
  nte?: string;

  invoice_summary?: string;

  labor_rows?: LaborRow[];
  parts_rows?: PartRow[];

  hide_labor?: boolean;
  hide_parts?: boolean;

  discount?: string;
  service_fee?: string;
  sales_tax_rate?: string;
  tax_amount?: string;
  taxable_subtotal?: string;
  subtotal?: string;
  subtotal_after_discount_fees?: string;
  total?: string;
  amount_paid?: string;
  balance?: string;

  buildops_invoice_id?: string;
  buildops_invoice_number?: string;
  customerProvidedWONumber?: string;

  customerPropertyId?: string;
  billingCustomerId?: string;

  property_id?: string;
  customer_id?: string;

  invoice_recipient_to?: string;
  invoice_recipient_cc?: string[];
  invoice_recipient_all_emails?: string[];

  property_rep_to?: string;
  property_rep_cc?: string[];
  property_rep_all_emails?: string[];

  customer_rep_to?: string;
  customer_rep_cc?: string[];
  customer_rep_all_emails?: string[];

  recipient_source?: string;
  recipient_message?: string;
  payment_url?: string;

  [key: string]: any;
};

function parseMoney(v: any): number {
  const s = String(v ?? "").replace(/[^0-9.\-]/g, "").trim();
  const n = Number(s);
  return Number.isFinite(n) ? n : 0;
}

function num(v: any): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function m(v: any): number {
  return typeof v === "number" && Number.isFinite(v) ? v : parseMoney(v);
}

function amountCell(value: number) {
  return `$${(Math.round(value * 100) / 100).toFixed(2)}`;
}

function toInputDate(v?: string): string {
  const s = String(v || "").trim();
  if (!s) return "";

  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;

  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString().slice(0, 10);
}

function fromInputDate(v: string): string {
  return v || "";
}

export default function InvoiceEditor(props: {
  value: InvoiceFields;
  onChange: (v: InvoiceFields) => void;
  onSave: () => void;
  saving: boolean;
  canSave: boolean;
}) {
  const v = useMemo(() => recomputeInvoiceTotals(props.value), [props.value]);
  const defaultLineDate = toInputDate(props.value.issued_date);

  React.useEffect(() => {
    const next = recomputeInvoiceTotals(props.value);
    if (
      next.subtotal !== props.value.subtotal ||
      next.tax_amount !== props.value.tax_amount ||
      next.total !== props.value.total ||
      next.balance !== props.value.balance ||
      next.subtotal_after_discount_fees !== props.value.subtotal_after_discount_fees ||
      next.taxable_subtotal !== props.value.taxable_subtotal
    ) {
      props.onChange(next);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    props.value.labor_rows,
    props.value.parts_rows,
    props.value.discount,
    props.value.service_fee,
    props.value.sales_tax_rate,
    props.value.amount_paid,
  ]);

  const set = (key: keyof InvoiceFields, value: any) =>
    props.onChange({ ...props.value, [key]: value });

  const setAddressLines = (key: "property_address_lines", text: string) => {
    const lines = text
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    props.onChange({ ...props.value, [key]: lines });
  };

  const setLabor = (idx: number, patch: Partial<LaborRow>) => {
    const rows = [...(props.value.labor_rows || [])];
    const nextRow = { ...rows[idx], ...patch };

    const hours = num(nextRow.hours);
    const rate = num(nextRow.rate);
    nextRow.price = Math.round(hours * rate * 100) / 100;

    rows[idx] = nextRow;
    props.onChange({ ...props.value, labor_rows: rows });
  };

  const setPart = (idx: number, patch: Partial<PartRow>) => {
    const rows = [...(props.value.parts_rows || [])];
    const nextRow = { ...rows[idx], ...patch };

    const qty = num(nextRow.qty);
    const unit = num(nextRow.unit_price);
    nextRow.price = Math.round(qty * unit * 100) / 100;

    rows[idx] = nextRow;
    props.onChange({ ...props.value, parts_rows: rows });
  };

  const addLabor = () => {
    const rows = [...(props.value.labor_rows || [])];
    rows.push({
      date: defaultLineDate,
      name: "Labor",
      description: "",
      taxable: false,
      hours: 1,
      rate: 0,
      price: 0,
    });
    props.onChange({ ...props.value, labor_rows: rows });
  };

  const addPart = () => {
    const rows = [...(props.value.parts_rows || [])];
    rows.push({
      date: defaultLineDate,
      name: "",
      code: "",
      description: "",
      taxable: true,
      qty: 1,
      unit_price: 0,
      price: 0,
    });
    props.onChange({ ...props.value, parts_rows: rows });
  };

  const removeLabor = (idx: number) => {
    const rows = [...(props.value.labor_rows || [])].filter((_, i) => i !== idx);
    props.onChange({ ...props.value, labor_rows: rows });
  };

  const removePart = (idx: number) => {
    const rows = [...(props.value.parts_rows || [])].filter((_, i) => i !== idx);
    props.onChange({ ...props.value, parts_rows: rows });
  };

  return (
    <div style={{ padding: 12 }}>
      <div style={{ fontWeight: 900, marginBottom: 8 }}>Invoice Info</div>

      <div className="row gap8" style={{ marginBottom: 10 }}>
        <input
          className="input"
          placeholder="Job Number"
          value={props.value.job_number || ""}
          onChange={(e) => set("job_number", e.target.value)}
        />
        <input
          className="input"
          placeholder="Authorized By"
          value={props.value.authorized_by || ""}
          onChange={(e) => set("authorized_by", e.target.value)}
        />
      </div>

      <div className="row gap8" style={{ marginBottom: 10 }}>
        <input
          className="input"
          placeholder="Customer WO"
          value={props.value.customerProvidedWONumber || ""}
          onChange={(e) => set("customerProvidedWONumber", e.target.value)}
        />
        <input
          className="input"
          placeholder="NTE"
          value={props.value.nte || ""}
          onChange={(e) => set("nte", e.target.value)}
        />
      </div>

      <div className="row gap8" style={{ marginBottom: 10 }}>
        <input
          className="input"
          placeholder="Property Name"
          value={props.value.property_name || ""}
          onChange={(e) => set("property_name", e.target.value)}
        />
        <input
          className="input"
          placeholder="PO Number"
          value={props.value.po_number || ""}
          onChange={(e) => set("po_number", e.target.value)}
        />
      </div>

      <label style={{ display: "block", marginBottom: 10 }}>
        <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>Property Address</div>
        <textarea
          className="input"
          style={{ minHeight: 70, resize: "vertical" }}
          placeholder={"123 Main St\nToronto, ON M5V 1A1\nCA"}
          value={(props.value.property_address_lines || []).join("\n")}
          onChange={(e) => setAddressLines("property_address_lines", e.target.value)}
        />
      </label>

      <div style={{ fontWeight: 900, marginBottom: 8 }}>Bill Client</div>

      <div className="row gap8" style={{ marginBottom: 10 }}>
        <input
          className="input"
          placeholder="Bill Client Name"
          value={props.value.billClient_name || ""}
          onChange={(e) => set("billClient_name", e.target.value)}
        />
        <input
          className="input"
          placeholder="Bill Client Email"
          value={props.value.billClient_email || ""}
          onChange={(e) => set("billClient_email", e.target.value)}
        />
      </div>

      <div className="row gap8" style={{ marginBottom: 10 }}>
        <input
          className="input"
          placeholder="Phone"
          value={props.value.billClient_phone || ""}
          onChange={(e) => set("billClient_phone", e.target.value)}
        />
      </div>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginTop: 8,
          marginBottom: 6,
        }}
      >
        <div style={{ fontWeight: 900 }}>Labor</div>
        <button
          type="button"
          className="btn"
          style={{
            background: props.value.hide_labor ? "#fff3e0" : "#ff9800",
            color: props.value.hide_labor ? "#c66900" : "#fff",
            border: "1px solid #ff9800",
            fontWeight: 700,
          }}
          onClick={() => set("hide_labor", !props.value.hide_labor)}
        >
          {props.value.hide_labor ? "Show" : "Hide"}
        </button>
      </div>

      {!props.value.hide_labor && (
        <>
          <div className="mutedSmall" style={{ marginBottom: 8 }}>
            Amount auto-calculates: hours × rate
          </div>

          <div className="invTableHeader">
            <div>Date</div>
            <div>Item Name</div>
            <div>Description</div>
            <div>Qty</div>
            <div>Unit Price</div>
            <div>Taxable</div>
            <div style={{ textAlign: "right" }}>Amount</div>
            <div />
          </div>

          {(props.value.labor_rows || []).map((r, i) => {
            const qty = num(r.hours);
            const unitPrice = num(r.rate);
            const amount = m(r.price);

            return (
              <div key={i} className="invTableRow">
                <input
                  className="input"
                  type="date"
                  value={toInputDate(r.date)}
                  onChange={(e) => setLabor(i, { date: fromInputDate(e.target.value) })}
                />
                <input
                  className="input"
                  placeholder="Item name"
                  value={r.name || ""}
                  onChange={(e) => setLabor(i, { name: e.target.value })}
                />
                <input
                  className="input"
                  placeholder="Item description"
                  value={r.description || ""}
                  onChange={(e) => setLabor(i, { description: e.target.value })}
                />
                <input
                  className="input"
                  type="number"
                  placeholder="Qty"
                  value={String(qty)}
                  onChange={(e) => setLabor(i, { hours: parseFloat(e.target.value || "0") })}
                />
                <input
                  className="input"
                  type="number"
                  placeholder="Unit Price"
                  value={String(unitPrice)}
                  onChange={(e) => setLabor(i, { rate: parseFloat(e.target.value || "0") })}
                />
                <label className="invChk">
                  <input
                    type="checkbox"
                    checked={!!r.taxable}
                    onChange={(e) => setLabor(i, { taxable: e.target.checked })}
                  />
                  <span>Tax</span>
                </label>
                <div className="invAmount">{amountCell(amount)}</div>
                <button type="button" className="btn btnGhost" onClick={() => removeLabor(i)}>
                  Remove
                </button>
              </div>
            );
          })}

          <div style={{ marginTop: 8 }}>
            <button type="button" className="btn btnSecondary" onClick={addLabor}>
              + Add labor line
            </button>
          </div>
        </>
      )}

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginTop: 14,
          marginBottom: 6,
        }}
      >
        <div style={{ fontWeight: 900 }}>Parts & Materials</div>
        <button
          type="button"
          className="btn"
          style={{
            background: props.value.hide_parts ? "#fff3e0" : "#ff9800",
            color: props.value.hide_parts ? "#c66900" : "#fff",
            border: "1px solid #ff9800",
            fontWeight: 700,
          }}
          onClick={() => set("hide_parts", !props.value.hide_parts)}
        >
          {props.value.hide_parts ? "Show" : "Hide"}
        </button>
      </div>

      {!props.value.hide_parts && (
        <>
          <div className="mutedSmall" style={{ marginBottom: 8 }}>
            Amount auto-calculates: qty × unit price
          </div>

          <div className="invTableHeader">
            <div>Date</div>
            <div>Item Name</div>
            <div>Item Code</div>
            <div>Description</div>
            <div>Qty</div>
            <div>Unit Price</div>
            <div>Taxable</div>
            <div style={{ textAlign: "right" }}>Amount</div>
            <div />
          </div>

          {(props.value.parts_rows || []).map((r, i) => {
            const qty = num(r.qty);
            const unitPrice = num(r.unit_price);
            const amount = m(r.price);

            return (
              <div key={i} className="invTableRow">
                <input
                  className="input"
                  type="date"
                  value={toInputDate(r.date)}
                  onChange={(e) => setPart(i, { date: fromInputDate(e.target.value) })}
                />
                <input
                  className="input"
                  placeholder="Item name"
                  value={r.name || ""}
                  onChange={(e) => setPart(i, { name: e.target.value })}
                />
                <input
                  className="input"
                  placeholder="Item code"
                  value={r.code || ""}
                  onChange={(e) => setPart(i, { code: e.target.value })}
                />
                <input
                  className="input"
                  placeholder="Item description"
                  value={r.description || ""}
                  onChange={(e) => setPart(i, { description: e.target.value })}
                />
                <input
                  className="input"
                  type="number"
                  placeholder="Qty"
                  value={String(qty)}
                  onChange={(e) => setPart(i, { qty: parseFloat(e.target.value || "0") })}
                />
                <input
                  className="input"
                  type="number"
                  placeholder="Unit Price"
                  value={String(unitPrice)}
                  onChange={(e) => setPart(i, { unit_price: parseFloat(e.target.value || "0") })}
                />
                <label className="invChk">
                  <input
                    type="checkbox"
                    checked={!!r.taxable}
                    onChange={(e) => setPart(i, { taxable: e.target.checked })}
                  />
                  <span>Tax</span>
                </label>
                <div className="invAmount">{amountCell(amount)}</div>
                <button type="button" className="btn btnGhost" onClick={() => removePart(i)}>
                  Remove
                </button>
              </div>
            );
          })}

          <div style={{ marginTop: 8 }}>
            <button type="button" className="btn btnSecondary" onClick={addPart}>
              + Add part line
            </button>
          </div>
        </>
      )}

      <div style={{ marginTop: 14, borderTop: "1px solid #eee", paddingTop: 10 }}>
        <div className="row gap8" style={{ marginBottom: 8 }}>
          <label style={{ flex: 1 }}>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>Discount</div>
            <input
              className="input"
              placeholder="$0.00"
              value={props.value.discount || "$0.00"}
              onChange={(e) => set("discount", e.target.value)}
            />
          </label>

          <label style={{ flex: 1 }}>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>Service Fee</div>
            <input
              className="input"
              placeholder="$0.00"
              value={props.value.service_fee || "$0.00"}
              onChange={(e) => set("service_fee", e.target.value)}
            />
          </label>

          <label style={{ flex: 1 }}>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>Tax Rate</div>
            <input
              className="input"
              placeholder="13%"
              value={props.value.sales_tax_rate || "13%"}
              onChange={(e) => set("sales_tax_rate", e.target.value)}
            />
          </label>
        </div>

        <div className="row gap8" style={{ marginBottom: 10 }}>
          <div
            className="input"
            style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
          >
            <span className="mutedSmall">Subtotal</span>
            <b>{v.subtotal}</b>
          </div>

          <div
            className="input"
            style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
          >
            <span className="mutedSmall">Subtotal After Discount/Fees</span>
            <b>{v.subtotal_after_discount_fees}</b>
          </div>

          <div
            className="input"
            style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
          >
            <span className="mutedSmall">Tax</span>
            <b>{v.tax_amount}</b>
          </div>

          <div
            className="input"
            style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
          >
            <span className="mutedSmall">Total</span>
            <b>{v.total}</b>
          </div>
        </div>

        <div className="row gap8">
          <button className="btn btnPrimary" onClick={props.onSave} disabled={!props.canSave || props.saving}>
            {props.saving ? "Saving..." : "Save Invoice"}
          </button>
          <div className="mutedSmall" style={{ display: "flex", alignItems: "center" }}>
            Final will update after Save ✅
          </div>
        </div>
      </div>
    </div>
  );
}