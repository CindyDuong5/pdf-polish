// frontend/src/panels/proposal/ProposalPanel.tsx
import { useEffect, useMemo, useState } from "react";
import {
  buildProposal,
  getFields,
  getLinks,
  getProposalProperties,
  searchProposalCustomers,
  saveFinalProposal,
  sendEmail,
  friendlyErrorMessage,
} from "../../api";
import ProposalStaticForm from "../../components/ProposalStaticForm";
import PreviewCard from "../../components/PreviewCard";
import AdditionalDocumentsPanel from "../../components/AdditionalDocumentsPanel";
import type {
  ProposalCustomer,
  ProposalProperty,
  ProposalStaticFields,
} from "../../types";

type Links = {
  id?: string;
  doc_type?: string;
  filename?: string;
  original?: { key: string | null; url: string | null };
  styled_draft?: { key: string | null; url: string | null };
  final?: { key: string | null; url: string | null };
};

type Props = {
  fields: ProposalStaticFields;
  onChange: (patch: Partial<ProposalStaticFields>) => void;
};

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

function pickProposalFields(input: any): Partial<ProposalStaticFields> {
  if (!input || typeof input !== "object") return {};

  return {
    proposal_number: String(input.proposal_number ?? ""),
    proposal_date: String(input.proposal_date ?? ""),
    proposal_type: String(input.proposal_type ?? ""),

    customer_id: String(input.customer_id ?? ""),
    customer_name: String(input.customer_name ?? ""),
    customer_address: String(input.customer_address ?? ""),

    property_id: String(input.property_id ?? ""),
    property_name: String(input.property_name ?? ""),
    property_address: String(input.property_address ?? ""),

    contact_name: String(input.contact_name ?? ""),
    contact_email: String(input.contact_email ?? ""),
    contact_phone: String(input.contact_phone ?? ""),

    prepared_by: String(input.prepared_by ?? ""),
    scope_summary: String(input.scope_summary ?? ""),
    exclusions: String(input.exclusions ?? ""),

    subtotal: String(input.subtotal ?? ""),
    tax_rate: String(input.tax_rate ?? ""),
    tax: String(input.tax ?? ""),
    total: String(input.total ?? ""),

    items: Array.isArray(input.items)
      ? input.items.map((row: any) => ({
          item: String(row?.item ?? ""),
          description: String(row?.description ?? ""),
          price: String(row?.price ?? ""),
        }))
      : [],
  };
}

function normalizeProposalPayload(fields: ProposalStaticFields): ProposalStaticFields {
  const itemSubtotal = (fields.items || []).reduce((sum, row) => {
    const price = parseMoney(row.price);
    return sum + (price ?? 0);
  }, 0);

  const hasAnyNumericItemPrice = (fields.items || []).some(
    (row) => parseMoney(row.price) !== null
  );

  const manualSubtotal = parseMoney(fields.subtotal);
  const effectiveSubtotal =
    hasAnyNumericItemPrice
      ? itemSubtotal
      : (manualSubtotal ?? 0);

  const taxRate = parseMoney(fields.tax_rate) ?? 13;
  const tax = effectiveSubtotal * (taxRate / 100);
  const total = effectiveSubtotal + tax;

  return {
    ...fields,
    subtotal: money2(effectiveSubtotal),
    tax_rate: String(taxRate),
    tax: money2(tax),
    total: money2(total),
    items: (fields.items || []).map((row) => ({
      item: String(row.item ?? ""),
      description: String(row.description ?? ""),
      price: String(row.price ?? ""),
    })),
  };
}

export default function ProposalPanel({ fields, onChange }: Props) {
  const [customerQuery, setCustomerQuery] = useState(fields.customer_name || "");
  const [customerResults, setCustomerResults] = useState<ProposalCustomer[]>([]);
  const [customerLoading, setCustomerLoading] = useState(false);
  const [customerErr, setCustomerErr] = useState<string | null>(null);

  const [properties, setProperties] = useState<ProposalProperty[]>([]);
  const [propertiesLoading, setPropertiesLoading] = useState(false);
  const [propertiesErr, setPropertiesErr] = useState<string | null>(null);

  const [docId, setDocId] = useState("");
  const [links, setLinks] = useState<Links | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [building, setBuilding] = useState(false);
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);

  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [sendMsg, setSendMsg] = useState<string | null>(null);
  const [sendErr, setSendErr] = useState<string | null>(null);

  const [ccInput, setCcInput] = useState("");
  const [bccInput, setBccInput] = useState("");
  const [subjectInput, setSubjectInput] = useState("");
  const [subjectDirty, setSubjectDirty] = useState(false);

  const draftUrl = links?.styled_draft?.url || null;
  const rawFinalUrl = links?.final?.url || null;
  const finalUrl = rawFinalUrl
    ? `${rawFinalUrl}${rawFinalUrl.includes("?") ? "&" : "?"}r=${reloadKey}`
    : null;

  const toEmail = useMemo(
    () => (fields.contact_email || "").trim(),
    [fields.contact_email]
  );

  function buildDefaultSubject(nextFields: ProposalStaticFields) {
    const proposalNumber = String(nextFields.proposal_number || "").trim();
    const propertyName = String(
      nextFields.property_name || nextFields.property_address || ""
    ).trim();

    if (proposalNumber && propertyName) {
      return `Proposal #${proposalNumber} - ${propertyName}`;
    }
    if (proposalNumber) {
      return `Proposal #${proposalNumber} - Please Review`;
    }
    return "Proposal - Please Review";
  }

  useEffect(() => {
    const q = customerQuery.trim();

    if (q.length < 2) {
      setCustomerResults([]);
      setCustomerErr(null);
      return;
    }

    const timer = window.setTimeout(async () => {
      try {
        setCustomerLoading(true);
        setCustomerErr(null);
        const res = await searchProposalCustomers(q, 20);
        setCustomerResults(res.items || []);
      } catch (e: any) {
        setCustomerResults([]);
        setCustomerErr(e?.message || "Customer search failed");
      } finally {
        setCustomerLoading(false);
      }
    }, 300);

    return () => window.clearTimeout(timer);
  }, [customerQuery]);

  useEffect(() => {
    if (subjectDirty) return;
    setSubjectInput(buildDefaultSubject(fields));
  }, [
    fields.proposal_number,
    fields.property_name,
    fields.property_address,
    subjectDirty,
  ]);

  function handleCustomerQueryChange(nextValue: string) {
    setCustomerQuery(nextValue);

    const selectedName = (fields.customer_name || "").trim();
    const nextTrimmed = nextValue.trim();

    if (fields.customer_id && nextTrimmed !== selectedName) {
      onChange({
        customer_id: "",
        customer_name: nextValue,
        customer_address: "",
        property_id: "",
        property_name: "",
        property_address: "",
      });

      setProperties([]);
      setPropertiesErr(null);
    }
  }

  async function handleSelectCustomer(customer: ProposalCustomer) {
    const customerName = customer.customer_name || "";
    const contactPhone = customer.phone_primary || customer.phone_alternate || "";

    setCustomerQuery(customerName);
    setCustomerResults([]);

    onChange({
      customer_id: customer.customer_id,
      customer_name: customerName,
      customer_address: customer.full_address || customer.address || "",
      property_id: "",
      property_name: "",
      property_address: "",
      contact_name: "",
      contact_email: customer.email || "",
      contact_phone: contactPhone,
    });

    try {
      setPropertiesLoading(true);
      setPropertiesErr(null);
      const res = await getProposalProperties(customer.customer_id);
      setProperties(res.items || []);
    } catch (e: any) {
      setProperties([]);
      setPropertiesErr(e?.message || "Property lookup failed");
    } finally {
      setPropertiesLoading(false);
    }
  }

  function handleSelectProperty(propertyId: string) {
    const property = properties.find((p) => p.property_id === propertyId);

    if (!property) {
      onChange({
        property_id: "",
        property_name: "",
        property_address: "",
      });
      return;
    }

    onChange({
      property_id: property.property_id,
      property_name: property.property_name || "",
      property_address:
        property.property_full_address || property.property_address || "",
    });
  }

  function parseEmails(input: string): string[] {
    return input
      .split(/[,;\n]+/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  async function refreshLinks(nextDocId: string) {
    const res = await getLinks(nextDocId);
    setLinks(res);
    setReloadKey((n) => n + 1);
  }

  async function onBuildProposal() {
    setMsg(null);
    setErr(null);
    setSendMsg(null);
    setSendErr(null);

    try {
      setBuilding(true);

      const payloadFields = normalizeProposalPayload(fields);
      const res = await buildProposal(payloadFields);
      const nextDocId = String(res?.doc_id || "").trim();

      if (!nextDocId) {
        throw new Error("Backend did not return doc_id");
      }

      setDocId(nextDocId);

      if (res?.fields) {
        onChange(pickProposalFields(res.fields));
      } else {
        onChange(payloadFields);
      }

      await refreshLinks(nextDocId);

      setMsg("Proposal draft built ✅");
    } catch (e: any) {
      setErr(friendlyErrorMessage(e));
    } finally {
      setBuilding(false);
    }
  }

  async function onSaveFinal() {
    if (!docId) {
      setErr("Please build the proposal first.");
      return;
    }

    setMsg(null);
    setErr(null);

    try {
      setSaving(true);

      const payloadFields = normalizeProposalPayload(fields);
      const res = await saveFinalProposal(docId, payloadFields);

      if (res?.customer_email && !fields.contact_email) {
        onChange({ contact_email: res.customer_email });
      }

      await refreshLinks(docId);

      try {
        const f = await getFields(docId);
        const next = f?.final || f?.draft || null;
        if (next) {
          onChange(pickProposalFields(next));
        } else {
          onChange(payloadFields);
        }
      } catch {
        onChange(payloadFields);
      }

      setMsg("Saved Final ✅");
    } catch (e: any) {
      setErr(friendlyErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  async function onSendEmail() {
    if (!docId) {
      setSendErr("Please build and save final first.");
      return;
    }

    if (!toEmail) {
      setSendErr("Missing contact email");
      return;
    }

    setSending(true);
    setSendMsg(null);
    setSendErr(null);

    try {
      await sendEmail(docId, {
        client_email: toEmail,
        cc: parseEmails(ccInput),
        bcc: parseEmails(bccInput),
        subject: subjectInput.trim() || undefined,
      });

      setSendMsg("Email sent ✅");
      setCcInput("");
      setBccInput("");
    } catch (e: any) {
      setSendErr(friendlyErrorMessage(e));
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      {msg ? <div className="alert ok">{msg}</div> : null}
      {err ? <div className="alert err">{err}</div> : null}

      <div className="panelCard">
        <div className="sectionTitle">Proposal Builder</div>

        <div
          style={{
            marginBottom: 18,
            padding: 16,
            border: "1px solid rgba(0,0,0,0.08)",
            borderRadius: 14,
            background: "#fff",
          }}
        >
          <label className="label">Customer Search</label>
          <input
            className="input"
            placeholder="Type customer name..."
            value={customerQuery}
            onChange={(e) => handleCustomerQueryChange(e.target.value)}
          />

          {customerLoading ? <div className="mutedSmall">Searching...</div> : null}
          {customerErr ? <div className="alert err">{customerErr}</div> : null}

          {customerResults.length > 0 ? (
            <div className="proposalSearchResults">
              {customerResults.map((c) => (
                <button
                  key={c.customer_id}
                  type="button"
                  className="proposalResultBtn"
                  onClick={() => handleSelectCustomer(c)}
                >
                  <div style={{ fontWeight: 700 }}>{c.customer_name}</div>
                  <div className="mutedSmall">{c.full_address || c.address || ""}</div>
                  <div className="mutedSmall">{c.email || ""}</div>
                </button>
              ))}
            </div>
          ) : null}
        </div>

        <div
          style={{
            marginBottom: 18,
            padding: 16,
            border: "1px solid rgba(0,0,0,0.08)",
            borderRadius: 14,
            background: "#fff",
          }}
        >
          <label className="label">Property</label>
          <select
            className="input"
            value={fields.property_id}
            onChange={(e) => handleSelectProperty(e.target.value)}
            disabled={!fields.customer_id || propertiesLoading}
          >
            <option value="">
              {!fields.customer_id
                ? "Select customer first..."
                : propertiesLoading
                ? "Loading properties..."
                : "Select property..."}
            </option>

            {properties.map((p) => (
              <option key={p.property_id} value={p.property_id}>
                {p.property_name || "Unnamed Property"} -{" "}
                {p.property_full_address || p.property_address || ""}
              </option>
            ))}
          </select>

          {propertiesLoading ? (
            <div className="mutedSmall">Loading properties...</div>
          ) : null}
          {propertiesErr ? <div className="alert err">{propertiesErr}</div> : null}
        </div>

        <ProposalStaticForm fields={fields} onChange={onChange} />

        <div className="row gap8" style={{ marginTop: 16 }}>
          <button
            className="btn btnPrimary"
            type="button"
            onClick={onBuildProposal}
            disabled={building || saving || sending}
          >
            {building ? "Building..." : "Build Proposal"}
          </button>

          <button
            className="btn btnGhost"
            type="button"
            onClick={onSaveFinal}
            disabled={!docId || building || saving || sending}
          >
            {saving ? "Saving..." : "Save Final"}
          </button>
        </div>

        <div className="mutedSmall" style={{ marginTop: 8 }}>
          {docId ? `Document ID: ${docId}` : "Build Proposal first to create the document row."}
        </div>
      </div>

      <div className="grid2" style={{ marginTop: 12 }}>
        <div className="card">
          <PreviewCard title="Draft" url={draftUrl} reloadKey={reloadKey} />
        </div>

        <div className="card">
          <PreviewCard title="Final" url={finalUrl} reloadKey={reloadKey} />

          <div style={{ padding: 12, borderTop: "1px solid #eee" }}>
            <div style={{ fontWeight: 900, marginBottom: 6 }}>Send Email</div>

            <div className="mutedSmall" style={{ marginBottom: 10 }}>
              To: <b>{toEmail || "(missing contact_email)"}</b>
            </div>

            <label style={{ display: "block", marginBottom: 10 }}>
              <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>
                Subject
              </div>
              <input
                className="input"
                value={subjectInput}
                onChange={(e) => {
                  setSubjectInput(e.target.value);
                  setSubjectDirty(true);
                }}
                placeholder="Email subject"
              />
            </label>

            <label style={{ display: "block", marginBottom: 10 }}>
              <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>
                CC
              </div>
              <input
                className="input"
                value={ccInput}
                onChange={(e) => setCcInput(e.target.value)}
                placeholder="cc1@email.com, cc2@email.com"
              />
            </label>

            <label style={{ display: "block", marginBottom: 10 }}>
              <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>
                BCC
              </div>
              <input
                className="input"
                value={bccInput}
                onChange={(e) => setBccInput(e.target.value)}
                placeholder="bcc1@email.com, bcc2@email.com"
              />
            </label>

            <AdditionalDocumentsPanel
              docId={docId}
              disabled={!docId || building || saving || sending}
              title="Additional Documents"
              helpText="These files will be attached to the proposal email."
            />

            <div className="row gap8" style={{ marginTop: 12 }}>
              <button
                className="btn btnPrimary"
                onClick={onSendEmail}
                disabled={!docId || !toEmail || building || saving || sending}
              >
                {sending ? "Sending..." : "📧 Send"}
              </button>
            </div>

            {sendMsg ? <div className="inlineSuccess">{sendMsg}</div> : null}
            {sendErr ? <div className="inlineError">{sendErr}</div> : null}
          </div>
        </div>
      </div>
    </>
  );
}