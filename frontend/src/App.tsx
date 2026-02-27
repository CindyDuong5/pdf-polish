// frontend/src/App.tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { getLinks, listDocuments, restyleDoc } from "./api";

type DocRow = {
  id: string;
  doc_type: string | null;
  status: string | null;
  customer_name: string | null;
  property_address: string | null;
  invoice_number: string | null;
  quote_number: string | null;
  job_report_number: string | null;
  created_at: string | null;
  original_s3_key: string | null;
  styled_draft_s3_key: string | null;
  final_s3_key: string | null;
  error: string | null;
};

type Links = {
  id: string;
  doc_type: string;
  filename: string;
  original: { key: string | null; url: string | null };
  styled_draft: { key: string | null; url: string | null };
  final: { key: string | null; url: string | null };
};

export default function App() {
  const [items, setItems] = useState<DocRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [links, setLinks] = useState<Links | null>(null);

  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");

  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // Used to force iframe reload WITHOUT modifying presigned URLs.
  // We'll ONLY bump this when URLs actually change (no blinking).
  const [reloadKey, setReloadKey] = useState<number>(() => Date.now());

  // Auto-refresh timer while draft is still generating
  const pollRef = useRef<number | null>(null);

  const selected = useMemo(
    () => items.find((x) => x.id === selectedId) || null,
    [items, selectedId]
  );

  async function refreshList() {
    setErr(null);
    const data = await listDocuments({
      q: q || undefined,
      status: status || undefined,
      limit: 50,
    });
    setItems(data.items || []);
  }

  async function refreshLinks(id: string) {
    const data = await getLinks(id);

    // Only trigger iframe reload if any URL actually changed.
    setLinks((prev) => {
      const changed =
        prev?.original?.url !== data?.original?.url ||
        prev?.styled_draft?.url !== data?.styled_draft?.url ||
        prev?.final?.url !== data?.final?.url;

      if (changed) setReloadKey(Date.now());
      return data;
    });
  }

  // Initial load
  useEffect(() => {
    refreshList().catch((e) => setErr(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // When selecting a document, fetch its links once
  useEffect(() => {
    if (!selectedId) {
      setLinks(null);
      return;
    }
    refreshLinks(selectedId).catch((e) => setErr(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  // Poll ONLY the list while draft is missing or status indicates processing.
  // (Do NOT refreshLinks on every poll — that caused the blinking.)
  useEffect(() => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }

    if (!selectedId || !selected) return;

    const draftMissing = !selected.styled_draft_s3_key;
    const st = (selected.status || "").toUpperCase();
    const stillProcessing = st === "NEW" || st === "STYLING";

    if (draftMissing || stillProcessing) {
      pollRef.current = window.setInterval(() => {
        refreshList().catch(() => {
          // ignore polling errors
        });
      }, 2500);
    }

    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, selected?.status, selected?.styled_draft_s3_key]);

  // When draft first appears (styled_draft_s3_key becomes available),
  // refresh links ONCE so the draft iframe shows up.
  useEffect(() => {
    if (!selectedId || !selected) return;

    if (selected.styled_draft_s3_key) {
      refreshLinks(selectedId).catch(() => {
        // ignore
      });
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

      // refresh list so selected row updates (styled_draft_s3_key + status)
      await refreshList();

      // refresh links so iframe gets the new presigned URL
      await refreshLinks(selectedId);

      setMsg("Restyle complete ✅");
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  const originalUrl = links?.original?.url || null;
  const draftUrl = links?.styled_draft?.url || null;
  const finalUrl = links?.final?.url || null;

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "system-ui" }}>
      {/* Left: List */}
      <div style={{ width: 420, borderRight: "1px solid #ddd", padding: 12, overflow: "auto" }}>
        <h2 style={{ margin: "8px 0" }}>PDF Polish</h2>

        <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
          <input
            placeholder="Search invoice/quote/job/customer/address..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{ flex: 1, padding: 8 }}
          />
        </div>

        <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
          <input
            placeholder="Status (optional)"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            style={{ flex: 1, padding: 8 }}
          />
          <button
            onClick={() => refreshList().catch((e) => setErr(String(e)))}
            style={{ padding: "8px 10px" }}
          >
            Refresh
          </button>
        </div>

        <div style={{ fontSize: 12, color: "#666", marginBottom: 8 }}>
          {items.length} documents
        </div>

        {items.map((d) => {
          const label =
            d.invoice_number || d.quote_number || d.job_report_number || d.id.slice(0, 8);
          const isActive = d.id === selectedId;

          return (
            <div
              key={d.id}
              onClick={() => setSelectedId(d.id)}
              style={{
                padding: 10,
                marginBottom: 8,
                border: "1px solid #ddd",
                borderRadius: 10,
                cursor: "pointer",
                background: isActive ? "#f3f6ff" : "white",
              }}
            >
              <div style={{ fontWeight: 700 }}>
                {d.doc_type || "UNKNOWN"} — {label}
              </div>
              <div style={{ fontSize: 12, color: "#444", marginTop: 4 }}>
                Status: <b>{d.status || "-"}</b>
              </div>
              <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
                {d.customer_name || d.property_address || ""}
              </div>
              {d.error ? (
                <div style={{ fontSize: 12, color: "crimson", marginTop: 6 }}>
                  {d.error}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      {/* Right: Viewer */}
      <div style={{ flex: 1, padding: 12, overflow: "auto" }}>
        {!selected ? (
          <div style={{ color: "#666" }}>Select a document to preview.</div>
        ) : (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <h2 style={{ margin: "0 0 6px 0" }}>
                  {selected.doc_type || "UNKNOWN"} — {selected.id}
                </h2>
                <div style={{ color: "#666", fontSize: 13 }}>
                  Status: <b>{selected.status || "-"}</b>
                  {!selected.styled_draft_s3_key ? (
                    <span style={{ marginLeft: 10, color: "#a36a00", fontWeight: 600 }}>
                      Draft generating…
                    </span>
                  ) : null}
                </div>
              </div>

              <div style={{ display: "flex", gap: 8 }}>
                <button
                  disabled={loading || !selectedId}
                  onClick={onRestyle}
                  style={{ padding: "10px 12px" }}
                >
                  {loading ? "Restyling..." : "Restyle"}
                </button>
              </div>
            </div>

            {msg ? (
              <div style={{ marginTop: 10, color: "green", fontWeight: 600 }}>{msg}</div>
            ) : null}
            {err ? (
              <div style={{ marginTop: 10, color: "crimson", whiteSpace: "pre-wrap" }}>{err}</div>
            ) : null}

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr 1fr",
                gap: 12,
                marginTop: 14,
              }}
            >
              <PreviewCard title="Original" url={originalUrl} reloadKey={reloadKey} />
              <PreviewCard title="Draft" url={draftUrl} reloadKey={reloadKey} />
              <PreviewCard title="Final" url={finalUrl} reloadKey={reloadKey} />
            </div>

            <div style={{ marginTop: 14, fontSize: 12, color: "#666" }}>
              Tip: if a PDF doesn’t load inside the embedded viewer, click “Open in new tab”.
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function PreviewCard({
  title,
  url,
  reloadKey,
}: {
  title: string;
  url: string | null;
  reloadKey: number;
}) {
  return (
    <div style={{ border: "1px solid #ddd", borderRadius: 12, padding: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontWeight: 800 }}>{title}</div>
        {url ? (
          <a href={url} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>
            Open in new tab
          </a>
        ) : (
          <span style={{ fontSize: 12, color: "#999" }}>Not available</span>
        )}
      </div>

      <div
        style={{
          marginTop: 8,
          height: 520,
          borderRadius: 10,
          overflow: "hidden",
          border: "1px solid #eee",
        }}
      >
        {url ? (
          <iframe
            key={`${title}-${reloadKey}`} // Only changes when URLs change (no blinking)
            title={title}
            src={url}
            style={{ width: "100%", height: "100%", border: "0" }}
          />
        ) : (
          <div style={{ padding: 12, color: "#999", fontSize: 13 }}>
            No PDF yet. It will appear automatically once processing is done.
          </div>
        )}
      </div>
    </div>
  );
}