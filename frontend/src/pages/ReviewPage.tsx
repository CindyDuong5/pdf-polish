// frontend/src/pages/ReviewPage.tsx
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { acceptQuote, rejectQuote } from "../api";

type Action = "accept" | "reject";

function decodeJwtPayload(token: string): any | null {
  try {
    const parts = token.split(".");
    if (parts.length < 2) return null;
    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const json = atob(payload);
    return JSON.parse(json);
  } catch {
    return null;
  }
}

export default function ReviewPage() {
  const [sp] = useSearchParams();
  const token = sp.get("token") || "";

  const claims = useMemo(() => decodeJwtPayload(token), [token]);
  const docId = (claims?.doc_id as string) || "";
  const action = (claims?.action as Action) || "";

  const [po, setPo] = useState("");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");

  const [loading, setLoading] = useState(false);
  const [ok, setOk] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const valid = !!token && !!docId && (action === "accept" || action === "reject");

  async function onConfirm() {
    setErr(null);
    setOk(null);
    if (!valid) return setErr("Invalid or missing token.");

    setLoading(true);
    try {
      if (action === "accept") {
        await acceptQuote(docId, {
          token,
          quote_po_number: po.trim() || null,
          quote_note: note.trim() || null,
        });
        setOk("Approved ✅ Thank you! Our team has been notified.");
      } else {
        await rejectQuote(docId, { token, reason: reason.trim() || null });
        setOk("Rejected ✅ Thank you! Our team has been notified.");
      }
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 720, margin: "40px auto", padding: 16 }}>
      <div style={{ marginBottom: 12 }}>
        <Link to="/" className="link">
          ← Back to PDF Polish
        </Link>
      </div>

      <div className="card">
        <div className="cardHeader">
          <div>
            <div className="cardTitle">Quote Confirmation</div>
            <div className="mutedSmall">
              {docId ? (
                <>
                  Doc: <b>{docId.slice(0, 8)}</b> — Action: <b>{action}</b>
                </>
              ) : (
                "Invalid link"
              )}
            </div>
          </div>
        </div>

        {!valid ? (
          <div className="alert err">This link is invalid or expired.</div>
        ) : (
          <>
            {action === "accept" ? (
              <>
                <div style={{ fontWeight: 800, marginBottom: 8 }}>Approve</div>

                <label style={{ display: "block", marginBottom: 10 }}>
                  <div className="mutedSmall" style={{ marginBottom: 4 }}>
                    PO Number (optional)
                  </div>
                  <input className="input" value={po} onChange={(e) => setPo(e.target.value)} placeholder="PO Number" />
                </label>

                <label style={{ display: "block", marginBottom: 10 }}>
                  <div className="mutedSmall" style={{ marginBottom: 4 }}>
                    Notes (optional)
                  </div>
                  <textarea
                    className="input"
                    style={{ minHeight: 120 }}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder="Any notes for our team..."
                  />
                </label>
              </>
            ) : (
              <>
                <div style={{ fontWeight: 800, marginBottom: 8 }}>Reject</div>

                <label style={{ display: "block", marginBottom: 10 }}>
                  <div className="mutedSmall" style={{ marginBottom: 4 }}>
                    Reason (required)
                  </div>
                  <textarea
                    className="input"
                    style={{ minHeight: 140 }}
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="Please tell us why you’re rejecting this quote..."
                  />
                </label>
              </>
            )}

            {err ? <div className="alert err">{err}</div> : null}
            {ok ? <div className="alert ok">{ok}</div> : null}

            <div className="row gap8" style={{ justifyContent: "flex-end", marginTop: 10 }}>
              <button
                className="btn btnPrimary"
                disabled={loading || (action === "reject" && !reason.trim())}
                onClick={onConfirm}
              >
                {loading ? "Submitting..." : "Confirm"}
              </button>
            </div>

            <div className="mutedSmall" style={{ marginTop: 10 }}>
              This will update the quote status and notify support@mainlinefire.com.
            </div>
          </>
        )}
      </div>
    </div>
  );
}