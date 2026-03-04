// frontend/src/panels/serviceQuote/ServiceQuotePanel.tsx
import { useEffect, useState } from "react";
import PreviewCard from "../../components/PreviewCard";
import ServiceQuoteEditor from "../../components/ServiceQuoteEditor";
import type { DocRow, Links, ServiceQuoteFields } from "../../types";
import { sendEmail, saveFinal, getFields } from "../../api"; // ✅ add getFields
import { withComputedTotals } from "./totals";

export default function ServiceQuotePanel(props: {
  selected: DocRow;
  selectedId: string;
  links: Links | null;
  reloadKey: number;
  onRestyle: () => Promise<void>;
  loading: boolean;
}) {
  const [fields, setFields] = useState<ServiceQuoteFields | null>(null);
  const [ccInput, setCcInput] = useState("");
  const [sending, setSending] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const originalUrl = props.links?.original?.url || null;
  const draftUrl = props.links?.styled_draft?.url || null;
  const finalUrl = props.links?.final?.url || null;

  const toEmail = props.selected?.customer_email || fields?.client_email || "";

  // ✅ Load fields on doc select (same as InvoicePanel)
  useEffect(() => {
    let alive = true;

    (async () => {
      try {
        const data = await getFields(props.selectedId);
        const next = (data?.draft || data?.final || null) as ServiceQuoteFields | null;
        if (!alive) return;
        setFields(next ? withComputedTotals(next) : null);
      } catch {
        if (alive) setFields(null);
      }
    })();

    return () => {
      alive = false;
    };
  }, [props.selectedId]);

  function parseCc(input: string): string[] {
    return input
      .split(/[,;\n]+/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  async function onSaveFinal() {
    if (!props.selectedId || !fields) return;
    setMsg(null);
    setErr(null);

    try {
      await saveFinal(props.selectedId, withComputedTotals(fields));
      setMsg("Saved Final ✅");
    } catch (e: any) {
      setErr(e?.message || String(e));
    }
  }

  async function onSendEmail() {
    if (!props.selectedId) return;
    setSending(true);
    setMsg(null);
    setErr(null);

    try {
      const cc = parseCc(ccInput);
      await sendEmail(props.selectedId, { cc, client_email: toEmail });
      setMsg("Email sent ✅");
      setCcInput("");
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
          <PreviewCard title="Original" url={originalUrl} reloadKey={props.reloadKey} />
        </div>
        <div className="card">
          <PreviewCard title="Draft" url={draftUrl} reloadKey={props.reloadKey} />
        </div>
      </div>

      <div className="grid2" style={{ marginTop: 12 }}>
        <div className="card">
          <div className="cardHeader">
            <div className="cardTitle">Editable Fields</div>
            <div className="mutedSmall">Service Quote</div>
          </div>

          {fields ? (
            <ServiceQuoteEditor
              value={fields}
              onChange={(v) => setFields(withComputedTotals(v))}
              onSave={onSaveFinal}
              saving={props.loading}
              canSave={!props.loading && !!props.selectedId && !!fields}
            />
          ) : (
            <div className="mutedSmall" style={{ padding: 12 }}>
              No editable fields yet. Click <b>Restyle</b> to generate draft + fields.
            </div>
          )}
        </div>

        <div className="card">
          <PreviewCard title="Final" url={finalUrl} reloadKey={props.reloadKey} />

          {/* Send email */}
          <div style={{ padding: 12, borderTop: "1px solid #eee" }}>
            <div style={{ fontWeight: 900, marginBottom: 6 }}>Send Email</div>

            <div className="mutedSmall" style={{ marginBottom: 10 }}>
              To: <b>{toEmail || "(missing client_email)"}</b>
            </div>

            <label style={{ display: "block", marginBottom: 10 }}>
              <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>
                CC (comma or semicolon separated)
              </div>
              <input
                className="input"
                value={ccInput}
                onChange={(e) => setCcInput(e.target.value)}
                placeholder="cc1@email.com, cc2@email.com"
              />
            </label>

            <div className="row gap8">
              <button
                className="btn btnPrimary"
                onClick={onSendEmail}
                disabled={sending || props.loading || !props.selectedId || !toEmail}
              >
                {sending ? "Sending..." : "📧 Send"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}