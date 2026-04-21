// frontend/src/pages/DocumentHistoryPage.tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listDocumentHistory } from "../api";
import type { DocumentHistoryRow } from "../types";
import {
  getDisplayDocType,
  getDisplayStatus,
  getStatusClass,
  getDocTypeClass,
} from "../uiLabels";
import "../styles.css";

function displayNumber(row: DocumentHistoryRow) {
  return row.invoice_number || row.quote_number || row.job_report_number || "-";
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString();
}

export default function DocumentHistoryPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<DocumentHistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [searchValue, setSearchValue] = useState("");

  async function load(q?: string) {
    setLoading(true);
    setErr(null);

    try {
      const data = await listDocumentHistory({ limit: 300, q });
      setItems((data.items || []) as DocumentHistoryRow[]);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(searchValue).catch((e) => setErr(String(e)));
  }, [searchValue]);

  return (
    <div className="historyPage">
      <div className="historyHeader">
        <div>
          <div className="pageTitle">Document History</div>
          <div className="pageSub">All stored quotes, proposals, and invoices</div>
        </div>

        <div className="row gap8">
          <button className="btn btnGhost" onClick={() => navigate("/")}>
            Back
          </button>
          <button className="btn btnPrimary" onClick={() => load(searchValue)}>
            Refresh History
          </button>
        </div>
      </div>

      <div className="historySearchBar">
        <input
          className="input"
          placeholder="Search by invoice #, quote #, or proposal #"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              setSearchValue(searchInput.trim());
            }
          }}
        />
        <button
          className="btn btnPrimary"
          onClick={() => setSearchValue(searchInput.trim())}
        >
          Search
        </button>
        <button
          className="btn btnGhost"
          onClick={() => {
            setSearchInput("");
            setSearchValue("");
          }}
        >
          Clear
        </button>
      </div>

      {loading ? <div className="alert">Loading history...</div> : null}
      {err ? <div className="alert err">{err}</div> : null}

      {!loading && !err ? (
        <div className="historyCard">
          <div className="historyMeta">
            <div className="mutedSmall">{items.length} documents</div>
            {searchValue ? (
              <div className="mutedSmall">Search: {searchValue}</div>
            ) : null}
          </div>

          <div className="historyTableWrap">
            <table className="historyTable">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Number</th>
                  <th>Status</th>
                  <th>Updated</th>
                  <th>Final PDF</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => {
                  const displayStatus = getDisplayStatus(row);
                  const statusClass = getStatusClass(displayStatus);
                  const docTypeClass = getDocTypeClass(row);

                  return (
                    <tr key={row.id}>
                      <td>
                        <span className={`historyTypeBadge ${docTypeClass}`}>
                          {getDisplayDocType(row)}
                        </span>
                      </td>
                      <td>{displayNumber(row)}</td>
                      <td>
                        <span className={`historyStatusBadge ${statusClass}`}>
                          {displayStatus}
                        </span>
                      </td>
                      <td>{formatDate(row.updated_at || row.created_at)}</td>
                      <td>
                        {row.final_url ? (
                          <a
                            className="btn btnGhost btnSm"
                            href={row.final_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Open PDF
                          </a>
                        ) : (
                          <span className="historyEmptyBadge">No Final PDF</span>
                        )}
                      </td>
                    </tr>
                  );
                })}

                {!items.length ? (
                  <tr>
                    <td colSpan={5}>
                      <div className="muted" style={{ padding: "12px 0" }}>
                        No documents found.
                      </div>
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}