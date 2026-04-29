// frontend/src/panels/proposal/ProposalPanel.tsx

import { useEffect, useMemo, useState } from "react";
import {
  buildProposal,
  getFields,
  getLinks,
  saveFinalProposal,
  sendEmail,
  friendlyErrorMessage,
} from "../../api";
import ProposalStaticForm from "../../components/ProposalStaticForm";
import PreviewCard from "../../components/PreviewCard";
import AdditionalDocumentsPanel from "../../components/AdditionalDocumentsPanel";
import type { ProposalContact, ProposalStaticFields } from "../../types";

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
  proposalContacts?: ProposalContact[];
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
  const effectiveSubtotal = hasAnyNumericItemPrice
    ? itemSubtotal
    : manualSubtotal ?? 0;

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

function parseEmails(input: string): string[] {
  return input
    .split(/[,;\n]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function uniqueEmails(values: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];

  for (const value of values) {
    const email = String(value || "").trim();
    const key = email.toLowerCase();

    if (!email || seen.has(key)) continue;

    seen.add(key);
    out.push(email);
  }

  return out;
}

function contactEmail(contact: any): string {
  return String(
    contact?.email_address ||
      contact?.email ||
      contact?.contact_email ||
      contact?.CONTACT_EMAIL ||
      contact?.EMAIL ||
      ""
  ).trim();
}

export default function ProposalPanel({
  fields,
  onChange,
  proposalContacts = [],
}: Props) {
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
  const [ccDirty, setCcDirty] = useState(false);

  const draftUrl = links?.styled_draft?.url || null;
  const rawFinalUrl = links?.final?.url || null;
  const finalUrl = rawFinalUrl
    ? `${rawFinalUrl}${rawFinalUrl.includes("?") ? "&" : "?"}r=${reloadKey}`
    : null;

  const toEmail = useMemo(
    () => (fields.contact_email || "").trim(),
    [fields.contact_email]
  );

  const ccEmailsFromContacts = useMemo(() => {
    const selectedEmail = toEmail.toLowerCase();

    return uniqueEmails(
      proposalContacts
        .map((contact) => contactEmail(contact))
        .filter((email) => email.toLowerCase() !== selectedEmail)
    );
  }, [proposalContacts, toEmail]);

  useEffect(() => {
    if (ccDirty) return;
    setCcInput(ccEmailsFromContacts.join(", "));
  }, [ccEmailsFromContacts, ccDirty]);

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
    if (subjectDirty) return;
    setSubjectInput(buildDefaultSubject(fields));
  }, [
    fields.proposal_number,
    fields.property_name,
    fields.property_address,
    subjectDirty,
  ]);

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
      const cc = parseEmails(ccInput).filter(
        (email) => email.toLowerCase() !== toEmail.toLowerCase()
      );

      await sendEmail(docId, {
        client_email: toEmail,
        cc,
        bcc: parseEmails(bccInput),
        subject: subjectInput.trim() || undefined,
      });

      setSendMsg("Email sent ✅");
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
          {docId
            ? `Document ID: ${docId}`
            : "Build Proposal first to create the document row."}
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
                onChange={(e) => {
                  setCcInput(e.target.value);
                  setCcDirty(true);
                }}
                placeholder="cc1@email.com, cc2@email.com"
              />
              {ccEmailsFromContacts.length > 0 ? (
                <div className="mutedSmall" style={{ marginTop: 4 }}>
                  Other proposal contacts are auto-filled here.
                </div>
              ) : null}
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