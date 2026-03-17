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

  const draftUrl = props.links?.styled_draft?.url || null;
  const finalUrl = props.links?.final?.url || null;

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

  useEffect(() => {
    let alive = true;

    (async () => {
      try {
        setErr(null);

        const data = await getFields(props.selectedId);
        const next = (data?.draft || data?.final || null) as InvoiceFields | null;
        if (!alive) return;

        setFields(next);

        const defaultTo =
          (next?.billClient_email || "").trim() ||
          (props.selected?.customer_email || "").trim() ||
          "";

        setToInput(defaultTo);
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

    const nextTo =
      (fields?.billClient_email || "").trim() ||
      (props.selected?.customer_email || "").trim() ||
      "";

    setToInput(nextTo);
  }, [fields?.billClient_email, props.selected?.customer_email, toDirty]);

  useEffect(() => {
    if (subjectDirty) return;
    setSubjectInput(buildDefaultInvoiceSubject(fields));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fields?.invoice_number, props.selected?.invoice_number, subjectDirty]);

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
      await saveFinalInvoice(props.selectedId, fields);
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
        `This invoice total is over $5,000 (${(fields as any)?.total || `$${total.toFixed(2)}`}).\n\nDo you still want to generate a payment link?`
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
      setErr("Missing To email");
      return;
    }

    setSending(true);
    setMsg(null);
    setErr(null);

    try {
      const cc = parseCc(ccInput);
      const bcc = parseCc(bccInput);

      await sendInvoice(props.selectedId, {
        to,
        cc,
        bcc,
        subject: subjectInput.trim() || undefined,
      });

      setMsg("Invoice email sent ✅");
      setCcInput("");
      setBccInput("");
    } catch (e: any) {
      setErr(friendlyErrorMessage(e));
    } finally {
      setSending(false);
    }
  }

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
              <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>Payment Link</div>

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
                <div className="input" style={{ display: "flex", alignItems: "center", gap: 8 }}>
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
          </div>
        </div>
      </div>
    </>
  );
}