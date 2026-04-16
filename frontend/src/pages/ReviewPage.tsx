// frontend/src/pages/ReviewPage.tsx
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { acceptQuote, rejectQuote, getQuoteDecision } from "../api";

type Action = "accept" | "reject";
type DecisionStatus = "PENDING" | "APPROVED" | "REJECTED" | null;

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

function errMsg(e: any): string {
  return e?.detail || e?.message || String(e);
}

export default function ReviewPage() {
  const [sp] = useSearchParams();
  const token = sp.get("token") || "";

  const claims = useMemo(() => decodeJwtPayload(token), [token]);

  const docId = claims?.doc_id || "";
  const action = (claims?.action as Action) || "";

  const docType = String(claims?.doc_type || "").toUpperCase();
  const tokenDocLabel = String(claims?.doc_label || "").trim();

  const isProposal =
    tokenDocLabel.toUpperCase() === "PROPOSAL" ||
    docType === "PROJECT_QUOTE" ||
    String(claims?.proposal_number || "").trim().length > 0 ||
    String(claims?.quote_number || "").trim().toUpperCase().startsWith("P-");

  const docLabel = isProposal ? "Proposal" : "Quote";

  const docNumber = (
    claims?.proposal_number ||
    claims?.quote_number ||
    docId.slice(0, 8) ||
    ""
  ).toString();

  const [po, setPo] = useState("");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");

  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(false);

  const [ok, setOk] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [done, setDone] = useState(false);
  const [decision, setDecision] = useState<DecisionStatus>(null);

  const valid = !!token && !!docId && (action === "accept" || action === "reject");
  const isFinal = decision === "APPROVED" || decision === "REJECTED";

  useEffect(() => {
    let cancelled = false;

    async function run() {
      if (!valid) return;

      setChecking(true);
      setErr(null);
      setOk(null);

      try {
        const res: any = await getQuoteDecision(docId, token);
        if (cancelled) return;

        const status = String(res?.status || "PENDING").toUpperCase();

        if (status === "APPROVED" || status === "REJECTED") {
          setDecision(status as DecisionStatus);
          setDone(true);

          if (status === "APPROVED") {
            setPo(res?.quote_po_number || "");
            setNote(res?.quote_note || "");
          } else {
            setReason(res?.reject_reason || res?.reason || "");
          }

          setOk(
            status === "APPROVED"
              ? `${docLabel} is already approved. Contact support@mainlinefire.com if you need help.`
              : `${docLabel} is already rejected. Contact support@mainlinefire.com if you need help.`
          );
        } else {
          setDecision("PENDING");
        }
      } catch (e: any) {
        if (!cancelled) setErr(errMsg(e));
      } finally {
        if (!cancelled) setChecking(false);
      }
    }

    run();
    return () => {
      cancelled = true;
    };
  }, [valid, docId, token, docLabel]);

  async function onConfirm() {
    setErr(null);
    setOk(null);

    if (!valid) {
      return setErr("This link is invalid or expired.");
    }

    if (isFinal) {
      return setOk(
        decision === "APPROVED"
          ? `${docLabel} is already approved. Contact support@mainlinefire.com if you need help.`
          : `${docLabel} is already rejected. Contact support@mainlinefire.com if you need help.`
      );
    }

    setLoading(true);
    try {
      if (action === "accept") {
        const res: any = await acceptQuote(docId, {
          token,
          quote_po_number: po.trim() || null,
          quote_note: note.trim() || null,
        });

        const msg =
          res?.message || `${docLabel} approved ✔ Our team has been notified.`;
        setOk(msg);

        setDecision("APPROVED");
        setDone(true);
      } else {
        const res: any = await rejectQuote(docId, {
          token,
          reason: reason.trim() || null,
        });

        const msg =
          res?.message || `${docLabel} rejected ✔ Our team has been notified.`;
        setOk(msg);

        setDecision("REJECTED");
        setDone(true);
      }
    } catch (e: any) {
      setErr(errMsg(e));
    } finally {
      setLoading(false);
    }
  }

  const actionLabel =
    action === "accept" ? `Approve ${docLabel}` : `Reject ${docLabel}`;

  const badgeColor = action === "accept" ? "#16a34a" : "#dc2626";

  return (
    <div style={{ maxWidth: 720, margin: "60px auto", padding: 20 }}>
      <div className="card" style={{ padding: 28 }}>
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 24, fontWeight: 800 }}>{actionLabel}</div>

          <div style={{ marginTop: 6, fontSize: 14 }}>
            {docLabel} #
            <span
              style={{
                marginLeft: 6,
                padding: "4px 10px",
                borderRadius: 20,
                background: "#f3f4f6",
                fontWeight: 700,
              }}
            >
              {docNumber || "—"}
            </span>
          </div>
        </div>

        {!valid ? (
          <div className="alert err">This link is invalid or expired.</div>
        ) : (
          <>
            {checking && (
              <div className="alert">
                Checking {docLabel.toLowerCase()} status...
              </div>
            )}

            {isFinal ? (
              <>
                {err && <div className="alert err">{err}</div>}
                {ok && <div className="alert ok">{ok}</div>}
              </>
            ) : (
              <>
                {action === "accept" ? (
                  <>
                    <label style={{ display: "block", marginBottom: 14 }}>
                      <div className="mutedSmall" style={{ marginBottom: 6 }}>
                        PO Number (optional)
                      </div>
                      <input
                        className="input"
                        value={po}
                        disabled={done || loading || checking}
                        onChange={(e) => setPo(e.target.value)}
                        placeholder="Enter PO Number"
                      />
                    </label>

                    <label style={{ display: "block", marginBottom: 14 }}>
                      <div className="mutedSmall" style={{ marginBottom: 6 }}>
                        Notes (optional)
                      </div>
                      <textarea
                        className="input"
                        style={{ minHeight: 120 }}
                        value={note}
                        disabled={done || loading || checking}
                        onChange={(e) => setNote(e.target.value)}
                        placeholder="Any notes for our team..."
                      />
                    </label>
                  </>
                ) : (
                  <label style={{ display: "block", marginBottom: 14 }}>
                    <div className="mutedSmall" style={{ marginBottom: 6 }}>
                      Reason for rejection
                    </div>
                    <textarea
                      className="input"
                      style={{ minHeight: 140 }}
                      value={reason}
                      disabled={done || loading || checking}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder={`Please tell us why you're rejecting this ${docLabel.toLowerCase()}...`}
                    />
                  </label>
                )}

                {err && <div className="alert err">{err}</div>}
                {ok && <div className="alert ok">{ok}</div>}

                <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 20 }}>
                  <button
                    disabled={
                      done ||
                      loading ||
                      checking ||
                      (action === "reject" && !reason.trim())
                    }
                    onClick={onConfirm}
                    style={{
                      background: badgeColor,
                      color: "#fff",
                      border: "none",
                      padding: "12px 24px",
                      borderRadius: 10,
                      fontWeight: 700,
                      cursor: done ? "default" : "pointer",
                      opacity: done || loading || checking ? 0.7 : 1,
                    }}
                  >
                    {loading
                      ? "Submitting..."
                      : action === "accept"
                        ? "Confirm Approval"
                        : "Confirm Rejection"}
                  </button>
                </div>

                <div style={{ marginTop: 16, fontSize: 13, color: "#6b7280" }}>
                  This will update the {docLabel.toLowerCase()} status and notify support@mainlinefire.com.
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}