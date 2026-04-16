// frontend/src/pages/ProposalPage.tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import ProposalPanel from "../panels/proposal/ProposalPanel";
import type { ProposalStaticFields, ProposalItem } from "../types";
import "../styles.css";

function todayIsoDate(): string {
  const d = new Date();
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

const DEFAULT_SCOPE_SUMMARY = `Complete the Following Fire & Life Safety Inspections and Testing in Accordance with OFC, OBC, CAN/ULC-S536, NFPA 25, NFPA 10, CSA B64.`;

const DEFAULT_EXCLUSIONS = `• Job to be completed during regular hours 08:00-16:30 Monday to Friday
• Pricing is subject to parts availability and all items being done concurrently`;

function parseMoney(value: string | number | null | undefined): number | null {
  if (value == null) return null;

  const raw = String(value).trim();
  if (!raw) return null;

  const cleaned = raw.replace(/[^0-9.\-]/g, "");
  if (!cleaned) return null;

  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}

function money2(n: number): string {
  return round2(n).toFixed(2);
}

function calculateDerivedFields(next: ProposalStaticFields): ProposalStaticFields {
  const numericItemPrices = (next.items || [])
    .map((row: ProposalItem) => parseMoney(row.price))
    .filter((v): v is number => v !== null);

  const itemSubtotal = numericItemPrices.reduce((sum, n) => sum + n, 0);
  const hasAnyNumericItemPrice = numericItemPrices.length > 0;

  const manualSubtotal = parseMoney(next.subtotal);
  const effectiveSubtotal = hasAnyNumericItemPrice
    ? itemSubtotal
    : (manualSubtotal ?? 0);

  const taxRate = parseMoney(next.tax_rate) ?? 13;
  const tax = effectiveSubtotal * (taxRate / 100);
  const total = effectiveSubtotal + tax;

  return {
    ...next,
    subtotal: money2(effectiveSubtotal),
    tax_rate: String(taxRate),
    tax: money2(tax),
    total: money2(total),
  };
}

function buildInitialFields(): ProposalStaticFields {
  return calculateDerivedFields({
    proposal_number: "",
    proposal_date: todayIsoDate(),
    proposal_type: "",

    customer_id: "",
    customer_name: "",
    customer_address: "",

    property_id: "",
    property_name: "",
    property_address: "",

    contact_name: "",
    contact_email: "",
    contact_phone: "",

    prepared_by: "",
    scope_summary: DEFAULT_SCOPE_SUMMARY,
    exclusions: DEFAULT_EXCLUSIONS,

    subtotal: "",
    tax_rate: "13",
    tax: "",
    total: "",

    items: [
      {
        item: "",
        description: "",
        price: "",
      },
    ],
  });
}

export default function ProposalPage() {
  const navigate = useNavigate();
  const [fields, setFields] = useState<ProposalStaticFields>(buildInitialFields);

  function patchFields(patch: Partial<ProposalStaticFields>) {
    setFields((prev) => calculateDerivedFields({ ...prev, ...patch }));
  }

  return (
    <div className="appShell">
      <aside className="sidebar">
        <div className="sidebarHeader">
          <div className="brandDot" />
          <div>
            <div className="brandTitle">PDF Polish</div>
            <div className="brandSub">Proposal Builder</div>
          </div>
        </div>

        <div className="searchBox">
          <div style={{ fontWeight: 900, marginBottom: 8 }}>Proposal</div>

          <div className="row gap8" style={{ marginBottom: 8 }}>
            <button className="btn" onClick={() => navigate("/")}>
              Back to Home
            </button>
          </div>

          <div className="mutedSmall">
            Search customer, choose property, complete proposal details, then generate PDF.
          </div>
        </div>
      </aside>

      <main className="main">
        <div className="topBar">
          <div>
            <div className="pageTitle">Create Proposal</div>
            <div className="pageSub">Build proposal info before PDF generation</div>
          </div>
        </div>

        <ProposalPanel fields={fields} onChange={patchFields} />

        <div className="panelCard" style={{ marginTop: 16 }}>
          <div className="sectionTitle">Current Payload Preview</div>
          <pre
            style={{
              margin: 0,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              fontSize: 13,
            }}
          >
            {JSON.stringify(fields, null, 2)}
          </pre>
        </div>
      </main>
    </div>
  );
}