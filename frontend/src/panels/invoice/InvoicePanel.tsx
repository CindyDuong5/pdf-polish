// frontend/src/panels/invoice/InvoicePanel.tsx
import { useEffect, useMemo, useState } from "react";
import PreviewCard from "../../components/PreviewCard";
import InvoiceEditor, { type InvoiceFields } from "../../components/InvoiceEditor";
import type { DocRow, Links } from "../../types";
import {
  getFields,
  saveFinalInvoice,
  sendInvoice,
  getLinks,
  getInvoicePaymentLink,
  friendlyErrorMessage,
} from "../../api";
import { recomputeInvoiceTotals } from "./totals";
import AdditionalDocumentsPanel from "../../components/AdditionalDocumentsPanel";

export default function InvoicePanel(props: {
  selected: DocRow;
  selectedId: string;
  links: Links | null;
  reloadKey: number;
  loading: boolean;
  onLinksUpdated: (links: Links) => void;
}) {
  const [fields, setFields] = useState<InvoiceFields | null>(null);
  const [ccInput, setCcInput] = useState("");
  const [bccInput, setBccInput] = useState("");
  const [toInput, setToInput] = useState("");
  const [subjectInput, setSubjectInput] = useState("");
  const [sending, setSending] = useState(false);
  const [savingFinal, setSavingFinal] = useState(false);
  const [gettingPaymentLink, setGettingPaymentLink] = useState(false);
  const [toDirty, setToDirty] = useState(false);
  const [subjectDirty, setSubjectDirty] = useState(false);

  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [sendMsg, setSendMsg] = useState<string | null>(null);
  const [sendErr, setSendErr] = useState<string | null>(null);

  const draftUrl = props.links?.styled_draft?.url || null;

  const finalBaseUrl = props.links?.final?.url || null;
  const finalUrl = finalBaseUrl
    ? `${finalBaseUrl}${finalBaseUrl.includes("?") ? "&" : "?"}v=${props.reloadKey}`
    : null;

  function buildDefaultInvoiceSubject(next: InvoiceFields | null) {
    const invoiceNumber = String(
      next?.invoice_number ||
        (next as any)?.invoice_no ||
        props.selected?.invoice_number ||
        ""
    ).trim();

    return invoiceNumber
      ? `Invoice #${invoiceNumber} from Mainline Fire Protection`
      : "Invoice from Mainline Fire Protection";
  }

  function getDefaultTo(next: InvoiceFields | null) {
    return (
      next?.invoice_recipient_to ||
      next?.property_rep_to ||
      ""
    ).trim();
  }

  function uniqueEmails(items: any[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];

  for (const item of items || []) {
    const email = String(item || "").trim().toLowerCase();
    if (!email || seen.has(email)) continue;
    seen.add(email);
    out.push(email);
  }

  return out;
}

function getDefaultCc(next: InvoiceFields | null) {
  const to = String(
    next?.invoice_recipient_to ||
      next?.property_rep_to ||
      ""
  )
    .trim()
    .toLowerCase();

  const cc = uniqueEmails([
    ...(next?.invoice_recipient_cc || []),
    ...(next?.property_rep_cc || []),
    ...(next?.customer_rep_cc || []),
    ...(next?.invoice_recipient_all_emails || []),
    ...(next?.property_rep_all_emails || []),
    ...(next?.customer_rep_all_emails || []),
  ]);

  return cc.filter((email) => email !== to).join(", ");
}

  useEffect(() => {
    let alive = true;

    (async () => {
      try {
        setErr(null);
        setMsg(null);
        setSendMsg(null);
        setSendErr(null);

        const data = await getFields(props.selectedId);
        const next = (data?.draft || data?.final || null) as InvoiceFields | null;
        if (!alive) return;

        setFields(next);
        setToInput(getDefaultTo(next));
        setCcInput(getDefaultCc(next));
        setBccInput("");
        setToDirty(false);

        setSubjectInput(buildDefaultInvoiceSubject(next));
        setSubjectDirty(false);
      } catch (e: any) {
        if (!alive) return;
        setFields(null);
        setErr(friendlyErrorMessage(e));
      }
    })();

    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.selectedId]);

  useEffect(() => {
    if (toDirty) return;
    setToInput(getDefaultTo(fields));
  }, [fields?.invoice_recipient_to, toDirty]);

  useEffect(() => {
    if (subjectDirty) return;
    setSubjectInput(buildDefaultInvoiceSubject(fields));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fields?.invoice_number, props.selected?.invoice_number, subjectDirty]);

  useEffect(() => {
    setCcInput(getDefaultCc(fields));
  }, [
    fields?.invoice_recipient_cc,
    fields?.property_rep_cc,
    fields?.customer_rep_cc,
    fields?.invoice_recipient_all_emails,
    fields?.property_rep_all_emails,
    fields?.customer_rep_all_emails,
    fields?.invoice_recipient_to,
    fields?.property_rep_to,
    props.selectedId,
  ]);

  const paymentUrl = useMemo(() => {
    return (fields as any)?.payment_url || "";
  }, [fields]);

  function parseCc(input: string): string[] {
    return input
      .split(/[,;\n]+/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function parseMoney(v: any): number {
    const s = String(v ?? "").replace(/[^0-9.\-]/g, "").trim();
    const n = Number(s);
    return Number.isFinite(n) ? n : 0;
  }

  async function waitForFinalPdf(docId: string, tries = 15, delayMs = 800) {
    for (let i = 0; i < tries; i++) {
      const links = await getLinks(docId);
      if (links?.final?.url) return links;
      await new Promise((r) => setTimeout(r, delayMs));
    }
    return await getLinks(docId);
  }

  async function onSaveFinal() {
    if (!props.selectedId || !fields) return;
    setMsg(null);
    setErr(null);
    setSavingFinal(true);

    try {
      const res = await saveFinalInvoice(props.selectedId, fields);

      setFields((prev) =>
        prev
          ? ({
              ...prev,
              invoice_recipient_to:
                res?.invoice_recipient_to ?? prev.invoice_recipient_to,
              invoice_recipient_cc:
                res?.invoice_recipient_cc ?? prev.invoice_recipient_cc,
              property_rep_to: res?.property_rep_to ?? prev.property_rep_to,
              property_rep_cc: res?.property_rep_cc ?? prev.property_rep_cc,
              recipient_source: res?.recipient_source ?? prev.recipient_source,
              recipient_message: res?.recipient_message ?? prev.recipient_message,
              payment_url: res?.payment_url ?? prev.payment_url,
              property_id: res?.property_id ?? prev.property_id,
              customer_id: res?.customer_id ?? prev.customer_id,
            } as InvoiceFields)
          : prev
      );

      setMsg("Saved Final ✅");

      const updatedLinks = await waitForFinalPdf(props.selectedId);
      if (updatedLinks) props.onLinksUpdated(updatedLinks);
    } catch (e: any) {
      setErr(friendlyErrorMessage(e));
    } finally {
      setSavingFinal(false);
    }
  }

  async function onGetPaymentLink() {
    if (!props.selectedId || !fields) return;

    setMsg(null);
    setErr(null);

    const total = parseMoney((fields as any)?.total);
    let force = false;

    if (total > 5000) {
      const ok = window.confirm(
        `This invoice total is over $5,000 (${(fields as any)?.total || `$${total.toFixed(
          2
        )}`}).\n\nDo you still want to generate a payment link?`
      );
      if (!ok) return;
      force = true;
    }

    setGettingPaymentLink(true);
    try {
      const res = await getInvoicePaymentLink(props.selectedId, {
        force_over_limit: force,
      });

      setFields((prev) =>
        prev
          ? ({
              ...prev,
              payment_url: res?.payment_url || "",
            } as InvoiceFields)
          : prev
      );

      setMsg("Payment link loaded ✅");
    } catch (e: any) {
      setErr(friendlyErrorMessage(e));
    } finally {
      setGettingPaymentLink(false);
    }
  }

  async function onSendInvoice() {
    if (!props.selectedId) return;

    const to = (toInput || "").trim();
    if (!to) {
      setSendErr("Missing To email");
      setSendMsg(null);
      return;
    }

    setSending(true);
    setSendMsg(null);
    setSendErr(null);

    try {
      const cc = parseCc(ccInput);
      const bcc = parseCc(bccInput);

      const res = await sendInvoice(props.selectedId, {
        to,
        cc,
        bcc,
        subject: subjectInput.trim() || undefined,
      });

      setFields((prev) =>
        prev
          ? ({
              ...prev,
              invoice_recipient_to:
                res?.invoice_recipient_to ?? prev.invoice_recipient_to,
              invoice_recipient_cc:
                res?.invoice_recipient_cc ?? prev.invoice_recipient_cc,
              property_rep_to: res?.property_rep_to ?? prev.property_rep_to,
              property_rep_cc: res?.property_rep_cc ?? prev.property_rep_cc,
              recipient_source: res?.recipient_source ?? prev.recipient_source,
              recipient_message: res?.recipient_message ?? prev.recipient_message,
            } as InvoiceFields)
          : prev
      );

      setToInput(res?.to || to);
      setCcInput((res?.cc || []).join(", "));
      setBccInput((res?.bcc || []).join(", "));

      setSendMsg("Invoice email sent ✅");
    } catch (e: any) {
      setSendErr(friendlyErrorMessage(e));
    } finally {
      setSending(false);
    }
  }

  function getRecipientSourceUi(source?: string | null) {
    switch ((source || "").trim()) {
      case "property":
        return {
          border: "1px solid #b7eb8f",
          background: "#f6ffed",
          titleColor: "#237804",
          badgeBg: "#389e0d",
          label: "PROPERTY (SNOWFLAKE)",
        };
      case "customer":
        return {
          border: "1px solid #ffe58f",
          background: "#fffbe6",
          titleColor: "#8a6d1d",
          badgeBg: "#d48806",
          label: "CUSTOMER (SNOWFLAKE)",
        };
      case "bill_client":
        return {
          border: "1px solid #91d5ff",
          background: "#e6f7ff",
          titleColor: "#0958d9",
          badgeBg: "#1677ff",
          label: "BILL CLIENT EMAIL",
        };
      case "snowflake_error":
        return {
          border: "1px solid #ffccc7",
          background: "#fff2f0",
          titleColor: "#cf1322",
          badgeBg: "#cf1322",
          label: "SNOWFLAKE ERROR",
        };
      case "manual":
      default:
        return {
          border: "1px solid #f5c2c7",
          background: "#fff1f0",
          titleColor: "#a61d24",
          badgeBg: "#cf1322",
          label: "MANUAL",
        };
    }
  }

  const recipientUi = getRecipientSourceUi(fields?.recipient_source);

  return (
    <>
      {msg ? <div className="alert ok">{msg}</div> : null}
      {err ? <div className="alert err">{err}</div> : null}

      <div className="grid2">
        <div className="card">
          <PreviewCard title="Draft" url={draftUrl} reloadKey={props.reloadKey} />
        </div>
        <div className="card">
          <PreviewCard title="Final" url={finalUrl} reloadKey={props.reloadKey} />
        </div>
      </div>

      <div className="grid2" style={{ marginTop: 12 }}>
        <div className="card">
          <div className="cardHeader">
            <div className="cardTitle">Editable Fields</div>
            <div className="mutedSmall">Invoice</div>
          </div>

          {fields ? (
            <InvoiceEditor
              value={fields}
              onChange={(v) => setFields(recomputeInvoiceTotals(v))}
              onSave={onSaveFinal}
              saving={savingFinal}
              canSave={!savingFinal && !!props.selectedId && !!fields}
            />
          ) : (
            <div className="mutedSmall" style={{ padding: 12 }}>
              No editable fields available for this invoice.
            </div>
          )}
        </div>

        <div className="card">
          <div className="cardHeader">
            <div className="cardTitle">Send Invoice</div>
            <div className="mutedSmall">Email + payment link</div>
          </div>

          <div style={{ padding: 12 }}>
            {fields?.recipient_source ? (
              <div
                style={{
                  marginBottom: 14,
                  padding: "14px 16px",
                  borderRadius: 10,
                  border: recipientUi.border,
                  background: recipientUi.background,
                }}
              >
                <div
                  style={{
                    fontSize: 12,
                    fontWeight: 700,
                    letterSpacing: "0.04em",
                    textTransform: "uppercase",
                    marginBottom: 8,
                    color: recipientUi.titleColor,
                  }}
                >
                  Recipient Source
                </div>

                <div
                  style={{
                    display: "inline-block",
                    padding: "4px 10px",
                    borderRadius: 999,
                    fontSize: 12,
                    fontWeight: 700,
                    marginBottom: 8,
                    background: recipientUi.badgeBg,
                    color: "#fff",
                  }}
                >
                  {recipientUi.label}
                </div>

                {fields.recipient_message ? (
                  <div
                    style={{
                      fontSize: 14,
                      lineHeight: 1.45,
                      fontWeight: 500,
                      color: "#222",
                      whiteSpace: "pre-line",
                    }}
                  >
                    {fields.recipient_message}
                  </div>
                ) : null}

                {fields.recipient_source === "bill_client" &&
                (fields as any)?.billClient_email ? (
                  <div
                    style={{
                      marginTop: 8,
                      fontSize: 13,
                      color: "#0958d9",
                      fontWeight: 600,
                      wordBreak: "break-word",
                    }}
                  >
                    Billing client email: {(fields as any).billClient_email}
                  </div>
                ) : null}
              </div>
            ) : null}

            <label style={{ display: "block", marginBottom: 10 }}>
              <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>To</div>
              <input
                className="input"
                value={toInput}
                onChange={(e) => {
                  setToInput(e.target.value);
                  setToDirty(true);
                }}
                placeholder="client@email.com"
              />
            </label>

            <label style={{ display: "block", marginBottom: 10 }}>
              <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>Subject</div>
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
                CC (comma/semicolon separated)
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
                BCC (comma/semicolon separated)
              </div>
              <input
                className="input"
                value={bccInput}
                onChange={(e) => setBccInput(e.target.value)}
                placeholder="bcc1@email.com, bcc2@email.com"
              />
            </label>

            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>
                Payment Link
              </div>

              <div className="row gap8" style={{ marginBottom: 8 }}>
                <button
                  className="btn btnGhost"
                  onClick={onGetPaymentLink}
                  disabled={
                    gettingPaymentLink ||
                    savingFinal ||
                    props.loading ||
                    !props.selectedId ||
                    !fields
                  }
                >
                  {gettingPaymentLink ? "Getting..." : "Get Payment Link"}
                </button>
              </div>

              {paymentUrl ? (
                <div
                  className="input"
                  style={{ display: "flex", alignItems: "center", gap: 8 }}
                >
                  <div style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {paymentUrl}
                  </div>
                  <a className="btn btnGhost" href={paymentUrl} target="_blank" rel="noreferrer">
                    Open
                  </a>
                </div>
              ) : (
                <div className="mutedSmall">No payment link available yet.</div>
              )}
            </div>

            <AdditionalDocumentsPanel
              docId={props.selectedId}
              disabled={sending || savingFinal || props.loading || !props.selectedId}
              title="Additional Documents"
              helpText="These files will be attached to the invoice email."
            />

            <div className="row gap8" style={{ marginTop: 12 }}>
              <button
                className="btn btnPrimary"
                onClick={onSendInvoice}
                disabled={
                  sending ||
                  savingFinal ||
                  props.loading ||
                  !props.selectedId ||
                  !toInput.trim()
                }
              >
                {sending ? "Sending..." : "📧 Send Invoice"}
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