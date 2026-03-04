// frontend/src/panels/invoice/InvoicePanel.tsx
import React, { useEffect, useMemo, useState } from "react";
import PreviewCard from "../../components/PreviewCard";
import InvoiceEditor, { type InvoiceFields } from "../../components/InvoiceEditor";
import type { DocRow, Links } from "../../types";
import { getFields, saveFinalInvoice, sendInvoice, getLinks } from "../../api";
import { recomputeInvoiceTotals } from "./totals";

export default function InvoicePanel(props: {
  selected: DocRow;
  selectedId: string;
  links: Links | null;
  reloadKey: number;
  onRestyle: () => Promise<void>;
  loading: boolean;

  // ✅ parent callback so we can refresh Final after Save
  onLinksUpdated: (links: Links) => void;
}) {
  const [fields, setFields] = useState<InvoiceFields | null>(null);
  const [ccInput, setCcInput] = useState("");
  const [toInput, setToInput] = useState("");
  const [sending, setSending] = useState(false);
  const [savingFinal, setSavingFinal] = useState(false);

  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const draftUrl = props.links?.styled_draft?.url || null;
  const finalUrl = props.links?.final?.url || null;

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const data = await getFields(props.selectedId);
        const next = (data?.draft || data?.final || null) as InvoiceFields | null;
        if (!alive) return;

        const computed = next ? recomputeInvoiceTotals(next) : null;
        setFields(computed);

        // default TO email
        const defaultTo =
          (props.selected?.customer_email || "").trim() ||
          (computed?.billClient_email || "").trim() ||
          "";
        setToInput(defaultTo);
      } catch {
        if (alive) setFields(null);
      }
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.selectedId]);

  const paymentUrl = useMemo(() => {
    return (fields as any)?.payment_url || "";
  }, [fields]);

  function parseCc(input: string): string[] {
    return input
      .split(/[,;\n]+/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  async function waitForFinalPdf(docId: string, tries = 15, delayMs = 800) {
    for (let i = 0; i < tries; i++) {
      const links = await getLinks(docId);
      if (links?.final?.url) return links; // ✅ correct shape
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
      await saveFinalInvoice(props.selectedId, recomputeInvoiceTotals(fields));
      setMsg("Saved Final ✅");

      // ✅ refresh links so Final preview shows
      const updatedLinks = await waitForFinalPdf(props.selectedId);
      if (updatedLinks) props.onLinksUpdated(updatedLinks);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setSavingFinal(false);
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
      await sendInvoice(props.selectedId, { to, cc });
      setMsg("Invoice email sent ✅");
    } catch (e: any) {
      setErr(e?.message || String(e));
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
              No editable fields yet. Click <b>Restyle</b> to generate draft + fields.
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
                onChange={(e) => setToInput(e.target.value)}
                placeholder="client@email.com"
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

            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>Payment Link</div>
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
                <div className="mutedSmall">No payment link available (yet).</div>
              )}
            </div>

            <button
              className="btn btnPrimary"
              onClick={onSendInvoice}
              disabled={sending || savingFinal || props.loading || !props.selectedId || !toInput.trim()}
            >
              {sending ? "Sending..." : "📧 Send Invoice"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}