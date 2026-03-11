// frontend/src/pages/MainApp.tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { getLinks, listDocuments, restyleDoc, buildInvoiceByNumber } from "../api";
import type { DocRow, Links } from "../types";
import DocumentPanel from "../panels/DocumentPanel";
import "../styles.css";

function isQuoteDoc(row: DocRow) {
  return (row.doc_type || "").toUpperCase().includes("QUOTE");
}

function docTime(row: DocRow) {
  return new Date(row.updated_at || row.created_at || 0).getTime();
}

function dedupeDocuments(rows: DocRow[]): DocRow[] {
  const map = new Map<string, DocRow>();

  for (const row of rows) {
    const status = (row.status || "").toUpperCase();
    const quoteNumber = String(row.quote_number || "").trim();

    if (status === "REPLACED") continue;

    if (isQuoteDoc(row) && quoteNumber) {
      const key = `quote:${quoteNumber}`;
      const existing = map.get(key);

      if (!existing || docTime(row) > docTime(existing)) {
        map.set(key, row);
      }
      continue;
    }

    map.set(`doc:${row.id}`, row);
  }

  return Array.from(map.values()).sort((a, b) => docTime(b) - docTime(a));
}

export default function MainApp() {
  const [items, setItems] = useState<DocRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [links, setLinks] = useState<Links | null>(null);

  const [invoiceInput, setInvoiceInput] = useState("");
  const [generating, setGenerating] = useState(false);

  const [status, setStatus] = useState("");

  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [reloadKey, setReloadKey] = useState<number>(() => Date.now());
  const pollRef = useRef<number | null>(null);

  const selected = useMemo(
    () => items.find((x) => x.id === selectedId) || null,
    [items, selectedId]
  );

  async function refreshList(preferredSelectedId?: string | null): Promise<DocRow[]> {
    setErr(null);

    const data = await listDocuments({
      status: status || undefined,
      limit: 50,
    });

    const rawItems = (data.items || []) as DocRow[];
    const nextItems = dedupeDocuments(rawItems);
    setItems(nextItems);

    const wantedId = preferredSelectedId ?? selectedId;

    if (wantedId) {
      const found = nextItems.find((x) => x.id === wantedId);
      if (found) {
        if (selectedId !== wantedId) setSelectedId(wantedId);
      } else if (nextItems.length > 0) {
        setSelectedId(nextItems[0].id);
      } else {
        setSelectedId(null);
      }
    } else if (nextItems.length > 0) {
      setSelectedId(nextItems[0].id);
    }

    return nextItems;
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

  async function resolveSelectedDocId(newDocId: string) {
    if (!newDocId) return;
    setSelectedId(newDocId);
    await refreshList(newDocId);
    await refreshLinks(newDocId);
  }

  useEffect(() => {
    refreshList().catch((e) => setErr(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setLinks(null);
      return;
    }
    refreshLinks(selectedId).catch((e) => setErr(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  useEffect(() => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (!selectedId || !selected) return;

    const draftMissing = !selected.styled_draft_s3_key;
    const st = (selected.status || "").toUpperCase();
    const stillProcessing = st === "NEW" || st === "STYLING" || st === "FINALIZING";
    const shouldPoll = (draftMissing && st !== "REPLACED") || stillProcessing;

    if (shouldPoll) {
      pollRef.current = window.setInterval(() => {
        refreshList(selectedId).catch(() => {});
      }, 2500);
    }

    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
      pollRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, selected?.status, selected?.styled_draft_s3_key]);

  useEffect(() => {
    if (!selectedId || !selected) return;
    if (selected.styled_draft_s3_key) {
      refreshLinks(selectedId).catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.styled_draft_s3_key]);

  async function onRestyle() {
    if (!selectedId) return;
    setLoading(true);
    setMsg(null);
    setErr(null);

    try {
      const result = await restyleDoc(selectedId);
      const resolvedDocId = result?.doc_id || selectedId;

      await refreshList(resolvedDocId);
      await refreshLinks(resolvedDocId);

      if (resolvedDocId !== selectedId) {
        setSelectedId(resolvedDocId);
      }

      setMsg("Restyle complete ✅ Draft + fields ready.");
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function onGenerateInvoice() {
    const invoiceNumber = invoiceInput.trim();
    if (!invoiceNumber) return;

    setGenerating(true);
    setMsg(null);
    setErr(null);

    try {
      const data = await buildInvoiceByNumber(invoiceNumber);
      const newDocId = data?.doc_id || null;

      const refreshed = await refreshList(newDocId);

      if (newDocId) {
        setSelectedId(newDocId);
        await refreshLinks(newDocId);
      } else {
        const match = refreshed.find(
          (x) => String(x.invoice_number || "").trim() === invoiceNumber
        );
        if (match?.id) {
          setSelectedId(match.id);
          await refreshLinks(match.id);
        }
      }

      setMsg(`Invoice ${invoiceNumber} generated ✅`);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setGenerating(false);
    }
  }

  const topLabel =
    selected?.invoice_number ||
    selected?.quote_number ||
    selected?.job_report_number ||
    (selected?.id ? selected.id.slice(0, 8) : "");

  return (
    <div className="appShell">
      <aside className="sidebar">
        <div className="sidebarHeader">
          <div className="brandDot" />
          <div>
            <div className="brandTitle">PDF Polish</div>
            <div className="brandSub">Editor (v1)</div>
          </div>
        </div>

        <div className="searchBox">
          <div style={{ fontWeight: 900, marginBottom: 6 }}>Generate Invoice</div>

          <div className="row gap8" style={{ marginBottom: 8 }}>
            <input
              className="input"
              placeholder="Invoice # (e.g. 1013)"
              value={invoiceInput}
              onChange={(e) => setInvoiceInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onGenerateInvoice().catch(() => {});
              }}
            />
            <button
              className="btn btnPrimary"
              onClick={() => onGenerateInvoice().catch((e) => setErr(String(e)))}
              disabled={generating}
            >
              {generating ? "Generating..." : "Generate"}
            </button>
          </div>

          <div className="row gap8">
            <input
              className="input"
              placeholder="Status (optional)"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            />
            <button
              className="btn btnGhost"
              onClick={() => refreshList().catch((e) => setErr(String(e)))}
            >
              Refresh
            </button>
          </div>

          <div className="mutedSmall">{items.length} documents</div>
        </div>

        <div className="docList">
          {items.map((d) => {
            const label =
              d.invoice_number || d.quote_number || d.job_report_number || d.id.slice(0, 8);
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
                  {!selected.styled_draft_s3_key ? (
                    <span className="warnBadge">Draft generating…</span>
                  ) : null}
                </div>
              </div>

              <div className="row gap8">
                <button className="btn btnPrimary" disabled={loading || !selectedId} onClick={onRestyle}>
                  {loading ? "Working..." : "Restyle"}
                </button>
              </div>
            </div>

            {msg ? <div className="alert ok">{msg}</div> : null}
            {err ? <div className="alert err">{err}</div> : null}

            <DocumentPanel
              selected={selected}
              selectedId={selectedId!}
              links={links}
              reloadKey={reloadKey}
              onRestyle={onRestyle}
              loading={loading}
              onLinksUpdated={(l) => setLinks(l)}
              onResolvedDocId={resolveSelectedDocId}
            />
          </>
        )}
      </main>
    </div>
  );
}