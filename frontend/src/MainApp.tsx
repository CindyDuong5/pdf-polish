// frontend/src/MainApp.tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { getFields, getLinks, listDocuments, restyleDoc, saveFinal, sendEmail } from "./api";
import type { DocRow, Links, ServiceQuoteFields } from "./types";
import PreviewCard from "./components/PreviewCard";
import ServiceQuoteEditor from "./components/ServiceQuoteEditor";
import "./styles.css";

// Ontario HST default
const DEFAULT_TAX_RATE = 0.13;

function parseMoney(v: string | undefined | null): number {
  const t = String(v ?? "").replace(/[^0-9.\-]/g, "").trim();
  const n = Number(t);
  return Number.isFinite(n) ? n : 0;
}

function money2(n: number): string {
  return (Math.round(n * 100) / 100).toFixed(2);
}

/**
 * ALWAYS recompute subtotal/tax/total from item prices.
 * (Totals are display-only in the editor; backend also enforces.)
 */
function withComputedTotals(f: ServiceQuoteFields): ServiceQuoteFields {
  const itemsSubtotal = (f.items || []).reduce((sum, it) => sum + parseMoney(it.price), 0);
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

export default function MainApp() {
  const [items, setItems] = useState<DocRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [links, setLinks] = useState<Links | null>(null);

  // Keep only status filter for now
  const [status, setStatus] = useState("");

  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [fields, setFields] = useState<ServiceQuoteFields | null>(null);

  const [reloadKey, setReloadKey] = useState<number>(() => Date.now());
  const pollRef = useRef<number | null>(null);

  const [ccInput, setCcInput] = useState("");
  const [sending, setSending] = useState(false);

  function parseCc(input: string): string[] {
    return input
      .split(/[,;\n]+/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  const selected = useMemo(
    () => items.find((x) => x.id === selectedId) || null,
    [items, selectedId]
  );

  const isServiceQuote = (selected?.doc_type || "").toUpperCase().includes("SERVICE_QUOTE");

  async function refreshList() {
    setErr(null);
    const data = await listDocuments({
      status: status || undefined,
      limit: 50,
    });
    setItems(data.items || []);
  }

  async function refreshLinks(id: string) {
    const data = await getLinks(id);
    setLinks((prev) => {
      const changed =
        prev?.original?.url !== data?.original?.url ||
        prev?.styled_draft?.url !== data?.styled_draft?.url ||
        prev?.final?.url !== data?.final?.url;
      if (changed) setReloadKey(Date.now());
      return data;
    });
  }

  async function refreshFields(id: string) {
    const data = await getFields(id);
    const next = (data?.draft || data?.final || null) as ServiceQuoteFields | null;
    if (next) setFields(withComputedTotals(next));
    else setFields(null);
  }

  async function onSendEmail() {
    if (!selectedId || !selected) return;

    setSending(true);
    setMsg(null);
    setErr(null);

    try {
      const cc = parseCc(ccInput);

      // send to selected.customer_email (backend default), with cc list
      await sendEmail(selectedId, { cc, client_email: toEmail });

      await refreshList();
      await refreshLinks(selectedId);

      setMsg("Email sent ✅");
      setCcInput("");
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setSending(false);
    }
  }

  // Initial load
  useEffect(() => {
    refreshList().catch((e) => setErr(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // When selecting doc: links + fields
  useEffect(() => {
    if (!selectedId) {
      setLinks(null);
      setFields(null);
      return;
    }
    refreshLinks(selectedId).catch((e) => setErr(String(e)));
    refreshFields(selectedId).catch(() => setFields(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  // Poll list while processing (no blinking)
  useEffect(() => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (!selectedId || !selected) return;

    const draftMissing = !selected.styled_draft_s3_key;
    const st = (selected.status || "").toUpperCase();
    const stillProcessing = st === "NEW" || st === "STYLING" || st === "FINALIZING";

    if (draftMissing || stillProcessing) {
      pollRef.current = window.setInterval(() => {
        refreshList().catch(() => {});
      }, 2500);
    }

    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
      pollRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, selected?.status, selected?.styled_draft_s3_key]);

  // When draft appears, refresh links+fields once
  useEffect(() => {
    if (!selectedId || !selected) return;
    if (selected.styled_draft_s3_key) {
      refreshLinks(selectedId).catch(() => {});
      refreshFields(selectedId).catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.styled_draft_s3_key]);

  async function onRestyle() {
    if (!selectedId) return;
    setLoading(true);
    setMsg(null);
    setErr(null);

    try {
      await restyleDoc(selectedId);

      await refreshList();
      await refreshLinks(selectedId);
      await refreshFields(selectedId);

      setMsg("Restyle complete ✅ Draft + fields ready.");
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function onSaveFinal() {
    if (!selectedId) return;
    const f = fields ? withComputedTotals(fields) : null;
    if (!f) return;

    setLoading(true);
    setMsg(null);
    setErr(null);

    try {
      await saveFinal(selectedId, f);

      await refreshList();
      await refreshLinks(selectedId);
      await refreshFields(selectedId);

      setMsg("Saved Final ✅");
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  const originalUrl = links?.original?.url || null;
  const draftUrl = links?.styled_draft?.url || null;
  const finalUrl = links?.final?.url || null;
  const toEmail = selected?.customer_email || fields?.client_email || "";

  const topLabel =
    selected?.invoice_number ||
    selected?.quote_number ||
    selected?.job_report_number ||
    (selected?.id ? selected.id.slice(0, 8) : "");

  return (
    <div className="appShell">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebarHeader">
          <div className="brandDot" />
          <div>
            <div className="brandTitle">PDF Polish</div>
            <div className="brandSub">Service Quote editor (v1)</div>
          </div>
        </div>

        <div className="searchBox">
          <div className="row gap8">
            <input
              className="input"
              placeholder="Status (optional)"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            />
            <button className="btn btnGhost" onClick={() => refreshList().catch((e) => setErr(String(e)))}>
              Refresh
            </button>
          </div>
          <div className="mutedSmall">{items.length} documents</div>
        </div>

        <div className="docList">
          {items.map((d) => {
            const label = d.invoice_number || d.quote_number || d.job_report_number || d.id.slice(0, 8);
            const isActive = d.id === selectedId;
            const st = (d.status || "-").toUpperCase();

            return (
              <button
                key={d.id}
                className={`docCard ${isActive ? "active" : ""}`}
                onClick={() => setSelectedId(d.id)}
              >
                <div className="docTitle">
                  <span className="pill">{d.doc_type || "UNKNOWN"}</span>
                  <span className="docLabel">{label}</span>
                </div>
                <div className="docMeta">
                  <span className={`statusDot ${st}`} />
                  <span>Status: {st}</span>
                </div>
                <div className="docMeta muted">{d.customer_name || d.property_address || ""}</div>
                {d.error ? <div className="docError">{d.error}</div> : null}
              </button>
            );
          })}
        </div>
      </aside>

      {/* Main */}
      <main className="main">
        {!selected ? (
          <div className="emptyState">Select a document to preview.</div>
        ) : (
          <>
            <div className="topBar">
              <div>
                <div className="pageTitle">
                  {selected.doc_type || "UNKNOWN"} <span className="muted">—</span> {topLabel}
                </div>
                <div className="pageSub">
                  Status: <b>{selected.status || "-"}</b>
                  {!selected.styled_draft_s3_key ? <span className="warnBadge">Draft generating…</span> : null}
                </div>
              </div>

              <div className="row gap8">
                <button className="btn btnPrimary" disabled={loading || !selectedId} onClick={onRestyle}>
                  {loading ? "Working..." : "Restyle"}
                </button>
                {/* Save is inside editor */}
              </div>
            </div>

            {msg ? <div className="alert ok">{msg}</div> : null}
            {err ? <div className="alert err">{err}</div> : null}

            {/* Row 1: Original + Draft */}
            <div className="grid2">
              <div className="card">
                <PreviewCard title="Original" url={originalUrl} reloadKey={reloadKey} />
              </div>
              <div className="card">
                <PreviewCard title="Draft" url={draftUrl} reloadKey={reloadKey} />
              </div>
            </div>

            {/* Row 2: Editor + Final */}
            <div className="grid2" style={{ marginTop: 12 }}>
              <div className="card">
                <div className="cardHeader">
                  <div className="cardTitle">Editable Fields</div>
                  <div className="mutedSmall">Service Quote</div>
                </div>

                {isServiceQuote ? (
                  fields ? (
                    <ServiceQuoteEditor
                      value={fields}
                      onChange={(v) => setFields(withComputedTotals(v))}
                      onSave={onSaveFinal}
                      saving={loading}
                      canSave={!loading && !!selectedId && !!fields}
                    />
                  ) : (
                    <div className="mutedSmall" style={{ padding: 12 }}>
                      No editable fields yet. Click <b>Restyle</b> to generate draft + fields.
                    </div>
                  )
                ) : (
                  <div className="mutedSmall" style={{ padding: 12 }}>
                    Editor not enabled for this document type yet (Service Quote only).
                  </div>
                )}
              </div>

              <div className="card">
                <PreviewCard title="Final" url={finalUrl} reloadKey={reloadKey} />

                {/* ✅ Send Email Section */}
                <div style={{ padding: 12, borderTop: "1px solid #eee" }}>
                  <div style={{ fontWeight: 900, marginBottom: 6 }}>Send Email</div>

                  <div className="mutedSmall" style={{ marginBottom: 10 }}>
                    To: <b>{toEmail || "(missing client_email)"}</b>
                    {selected.sent_at ? (
                      <span style={{ marginLeft: 8 }}>
                        — Sent ✅ <b>{new Date(selected.sent_at).toLocaleString()}</b>
                      </span>
                    ) : null}
                  </div>

                  <label style={{ display: "block", marginBottom: 10 }}>
                    <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>CC (comma or semicolon separated)</div>
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
                      disabled={
                        sending ||
                        loading ||
                        !selectedId ||
                        !toEmail ||
                        (!selected.final_s3_key && !selected.styled_draft_s3_key && !selected.original_s3_key)
                      }
                    >
                      {sending ? "Sending..." : "📧 Send"}
                    </button>

                    {selected.sent_to ? (
                      <div className="mutedSmall">
                        Sent to: <b>{selected.sent_to}</b>
                        {selected.sent_cc ? <span> | CC: {selected.sent_cc}</span> : null}
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            </div>

            <div className="mutedSmall" style={{ marginTop: 10 }}>
              Tip: if a PDF doesn’t load inside the embedded viewer, click “Open in new tab”.
            </div>
          </>
        )}
      </main>
    </div>
  );
}