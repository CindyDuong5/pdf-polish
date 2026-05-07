// frontend/src/pages/ProposalPage.tsx

import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  getProposalOpportunity,
  friendlyErrorMessage,
  getLinks,
  listDocuments,
  restyleDoc,
} from "../api";
import ProposalPanel from "../panels/proposal/ProposalPanel";
import DocumentPanel from "../panels/DocumentPanel";
import type {
  DocRow,
  Links,
  ProposalContact,
  ProposalStaticFields,
  ProposalItem,
} from "../types";
import {
  getDisplayDocType,
  getDisplayStatus,
  getStatusClass,
  getDocTypeClass,
} from "../uiLabels";
import "../styles.css";

function todayIsoDate(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()
  ).padStart(2, "0")}`;
}

function isProjectQuoteDoc(row: DocRow) {
  return (row.doc_type || "").toUpperCase().includes("PROJECT_QUOTE");
}

function docTime(row: DocRow) {
  return new Date(row.updated_at || row.created_at || 0).getTime();
}

function dedupeProposalDocuments(rows: DocRow[]): DocRow[] {
  const map = new Map<string, DocRow>();

  for (const row of rows) {
    const status = (row.status || "").toUpperCase();
    const quoteNumber = String(row.quote_number || "").trim();

    if (status === "REPLACED") continue;
    if (!isProjectQuoteDoc(row)) continue;

    const key = quoteNumber ? `proposal:${quoteNumber}` : `doc:${row.id}`;
    const existing = map.get(key);

    if (!existing || docTime(row) > docTime(existing)) {
      map.set(key, row);
    }
  }

  return Array.from(map.values()).sort((a, b) => docTime(b) - docTime(a));
}

const DEFAULT_SCOPE_SUMMARY = `Complete the Following Fire & Life Safety Inspections and Testing in Accordance with OFC, OBC, CAN/ULC-S536, NFPA 25, NFPA 10, CSA B64.`;

const DEFAULT_EXCLUSIONS = `- Job to be completed during regular hours 08:00-16:30 Monday to Friday
- Pricing is subject to parts availability and all items being done concurrently`;

const DEFAULT_ITEMS_BY_TYPE: Record<string, ProposalItem[]> = {
  Inspection: [
    {
      item: "Monthly / Bi-Monthly",
      description: `• Fire Alarm
• Fire Sprinkler
• Fire Pump
• Emergency Lighting
• Fire Extinguishers
• Fire Hose`,
      price: "",
    },
    {
      item: "Quarterly",
      description: `• Fire Sprinkler
• Fire Drill
• Elevator Recall
• Smoke Control`,
      price: "",
    },
    {
      item: "Annual",
      description: `• Fire Alarm w/ End of Line Resistor Verification
• Fire Sprinkler w/ Drum Drip Maintenance
• Fire Pump
• Emergency Lighting
• Fire Extinguishers
• Fire Hose
• Smoke Control
• Elevator Fire Recall
• Backflow Test w/ Forward Flow (3 Total)`,
      price: "",
    },
    {
      item: "Optional: Annual Building Audit & Fire Protection Forecasting Plan",
      description: `• A comprehensive review of all fire and life safety systems, including current condition, upcoming requirements, and a forward-looking schedule to help plan repairs, upgrades, and budgeting.
• Cost TBD.`,
      price: "TBD",
    },
    {
      item: "Optional: Custom-Branded Fire Extinguishers (Site-Specific Labeling)",
      description: `• Supply of fire extinguishers with customized labeling and identification tailored to your building, providing a clean, consistent look while maintaining full code compliance.
• Cost TBD.`,
      price: "TBD",
    },
    {
      item: "Optional: Custom-Built Fire Inspection Log Books (Site-Specific & Fully Tailored)",
      description: `• Designed and printed specifically for your building, with all fire and life safety systems pre-structured for accurate, organized, and compliant record keeping.
• Cost TBD.`,
      price: "TBD",
    },
  ],
};

function isEmptyItem(row: ProposalItem): boolean {
  return (
    !String(row.item || "").trim() &&
    !String(row.description || "").trim() &&
    !String(row.price || "").trim()
  );
}

function shouldApplyDefaultItems(items: ProposalItem[] | undefined): boolean {
  if (!items || items.length === 0) return true;
  return items.every(isEmptyItem);
}

function getDefaultItemsForType(proposalType: string): ProposalItem[] | null {
  const defaults = DEFAULT_ITEMS_BY_TYPE[proposalType];
  if (!defaults) return null;

  return defaults.map((row) => ({
    item: row.item,
    description: row.description,
    price: row.price,
  }));
}

function parseMoney(value: string | number | null | undefined): number | null {
  if (value == null) return null;
  const cleaned = String(value).trim().replace(/[^0-9.\-]/g, "");
  if (!cleaned) return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}

function money2(n: number): string {
  return round2(n).toFixed(2);
}

function calculateDerivedFields(next: ProposalStaticFields): ProposalStaticFields {
  const numericItemPrices = (next.items || [])
    .map((row: ProposalItem) => parseMoney(row.price))
    .filter((v): v is number => v !== null);

  const itemSubtotal = numericItemPrices.reduce((sum, n) => sum + n, 0);
  const hasAnyNumericItemPrice = numericItemPrices.length > 0;

  const manualSubtotal = parseMoney(next.subtotal);
  const effectiveSubtotal = hasAnyNumericItemPrice
    ? itemSubtotal
    : manualSubtotal ?? 0;

  const taxRate = parseMoney(next.tax_rate) ?? 13;
  const tax = effectiveSubtotal * (taxRate / 100);
  const total = effectiveSubtotal + tax;

  return {
    ...next,
    subtotal:
      hasAnyNumericItemPrice || manualSubtotal !== null
        ? money2(effectiveSubtotal)
        : "",
    tax_rate: String(taxRate),
    tax:
      hasAnyNumericItemPrice || manualSubtotal !== null ? money2(tax) : "",
    total:
      hasAnyNumericItemPrice || manualSubtotal !== null ? money2(total) : "",
  };
}

function buildInitialFields(): ProposalStaticFields {
  return calculateDerivedFields({
    proposal_number: "",
    proposal_date: todayIsoDate(),
    proposal_type: "",
    customer_id: "",
    customer_name: "",
    customer_address: "",
    property_id: "",
    property_name: "",
    property_address: "",
    contact_name: "",
    contact_email: "",
    contact_phone: "",
    prepared_by: "",
    scope_summary: DEFAULT_SCOPE_SUMMARY,
    exclusions: DEFAULT_EXCLUSIONS,
    subtotal: "",
    tax_rate: "13",
    tax: "",
    total: "",
    items: [{ item: "", description: "", price: "" }],
  });
}

function contactEmail(contact: ProposalContact): string {
  return String(contact.email_address || contact.email || "").trim();
}

function contactPhone(contact: ProposalContact): string {
  return String(
    contact.phone_mobile || contact.phone_primary || contact.phone_alternate || ""
  ).trim();
}

function dedupeContacts(contacts: ProposalContact[]): ProposalContact[] {
  const seen = new Set<string>();
  const result: ProposalContact[] = [];

  for (const contact of contacts) {
    const email = contactEmail(contact).toLowerCase();
    const name = String(contact.full_name || "").trim().toLowerCase();
    const key = email || name;

    if (!key || seen.has(key)) continue;
    seen.add(key);
    result.push(contact);
  }

  return result;
}

function getAllProposalContacts(item: any): ProposalContact[] {
  return dedupeContacts([
    ...(Array.isArray(item.proposal_send_contacts) ? item.proposal_send_contacts : []),
    ...(Array.isArray(item.property_quote_representatives)
      ? item.property_quote_representatives
      : []),
    ...(Array.isArray(item.customer_quote_representatives)
      ? item.customer_quote_representatives
      : []),
  ]);
}


export default function ProposalPage() {
  const navigate = useNavigate();

  const [fields, setFields] = useState<ProposalStaticFields>(buildInitialFields);
  const [opportunityNumber, setOpportunityNumber] = useState("");
  const [loadingOpportunity, setLoadingOpportunity] = useState(false);
  const [lookupMsg, setLookupMsg] = useState<string | null>(null);
  const [lookupErr, setLookupErr] = useState<string | null>(null);
  const [lookupNotices, setLookupNotices] = useState<string[]>([]);
  const [proposalContacts, setProposalContacts] = useState<ProposalContact[]>([]);

  const [proposalDocs, setProposalDocs] = useState<DocRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [links, setLinks] = useState<Links | null>(null);
  const [reloadKey, setReloadKey] = useState<number>(() => Date.now());

  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const selected = useMemo(
    () => proposalDocs.find((x) => x.id === selectedId) || null,
    [proposalDocs, selectedId]
  );

  const selectedLabel =
    selected?.quote_number ||
    selected?.invoice_number ||
    selected?.job_report_number ||
    (selected?.id ? selected.id.slice(0, 8) : "");

  function startNewProposal() {
    setSelectedId(null);
    setLinks(null);
    setReloadKey(Date.now());
    setMsg(null);
    setErr(null);

    setFields(buildInitialFields());
    setOpportunityNumber("");
    setLookupMsg(null);
    setLookupErr(null);
    setLookupNotices([]);
    setProposalContacts([]);
  }
  
  async function refreshProposalDocs(preferredSelectedId?: string | null): Promise<DocRow[]> {
    const data = await listDocuments({ limit: 50 });
    const rows = dedupeProposalDocuments((data.items || []) as DocRow[]);
    setProposalDocs(rows);

    const wantedId = preferredSelectedId ?? selectedId;

    if (wantedId && rows.some((x) => x.id === wantedId)) {
      setSelectedId(wantedId);
    } else if (wantedId && !rows.some((x) => x.id === wantedId)) {
      setSelectedId(null);
    }

    return rows;
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
    await refreshProposalDocs(newDocId);
    await refreshLinks(newDocId);
  }

  async function onRestyle() {
    if (!selectedId || !selected) return;

    setLoading(true);
    setMsg(null);
    setErr(null);

    try {
      const result = await restyleDoc(selectedId);
      const resolvedDocId = result?.doc_id || selectedId;

      await refreshProposalDocs(resolvedDocId);
      await refreshLinks(resolvedDocId);

      if (resolvedDocId !== selectedId) setSelectedId(resolvedDocId);

      setMsg("Restyle complete ✅ Draft + fields ready.");
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshProposalDocs().catch((e) => setErr(String(e)));
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

  function patchFields(patch: Partial<ProposalStaticFields>) {
    setFields((prev) => {
      const next: ProposalStaticFields = { ...prev, ...patch };

      if (
        patch.proposal_type &&
        patch.proposal_type !== prev.proposal_type &&
        shouldApplyDefaultItems(prev.items)
      ) {
        const defaultItems = getDefaultItemsForType(patch.proposal_type);
        if (defaultItems) next.items = defaultItems;
      }

      return calculateDerivedFields(next);
    });
  }

  function applySelectedContact(contact: ProposalContact) {
    patchFields({
      contact_name: String(contact.full_name || ""),
      contact_email: contactEmail(contact),
      contact_phone: contactPhone(contact),
    });
  }

  async function onLoadOpportunity() {
    const number = opportunityNumber.trim();

    if (!number) {
      setLookupErr("Please enter opportunity number.");
      return;
    }

    setLookupMsg(null);
    setLookupErr(null);
    setLookupNotices([]);
    setProposalContacts([]);

    try {
      setLoadingOpportunity(true);

      const res = await getProposalOpportunity(number);
      const item = res.item;
      const hasPropertyId = Boolean(String(item.property_id || "").trim());

      patchFields({
        proposal_number: item.proposal_number || number,
        proposal_date: todayIsoDate(),
        prepared_by: item.prepared_by || "",
        customer_id: item.customer_id || "",
        customer_name: item.customer_name || "",
        customer_address: item.customer_address || "",
        property_id: item.property_id || "",
        property_name: item.property_name || item.customer_name || "",
        property_address: item.property_address || item.customer_address || "",
        contact_name: item.contact_name || "",
        contact_email: item.contact_email || "",
        contact_phone: item.contact_phone || "",
      });

      const notices: string[] = [];

      if (!hasPropertyId) {
        notices.push(
          "No property was found for this opportunity. We used the customer info as the property. You can update it if needed."
        );
      }

      const contacts = getAllProposalContacts(item);
      setProposalContacts(contacts);

      if (contacts.length === 0) {
        notices.push(
          "We couldn’t find any contact for this proposal. Please enter the contact details manually."
        );
      } else if (contacts.length === 1) {
        notices.push("We found one contact and selected it for you.");
        applySelectedContact(contacts[0]);
      } else {
        notices.push(
          `${contacts.length} contacts found. Choose one for the proposal. The others will be included in CC when sending the email.`
        );
      }

      setLookupNotices(notices);
      setLookupMsg("Opportunity loaded");
    } catch (e: any) {
      setLookupErr(friendlyErrorMessage(e));
    } finally {
      setLoadingOpportunity(false);
    }
  }

  function onClearAll() {
    setFields(buildInitialFields());
    setOpportunityNumber("");
    setLookupMsg(null);
    setLookupErr(null);
    setLookupNotices([]);
    setProposalContacts([]);
  }

  return (
    <div className="appShell">
      <aside className="sidebar">
        <div className="sidebarHeader">
          <div className="brandDot" />
          <div>
            <div className="brandTitle">PDF Polish</div>
            <div className="brandSub">Proposal Builder</div>
          </div>
        </div>

        <div className="searchBox">
          <div style={{ fontWeight: 900, marginBottom: 8 }}>Proposal</div>

          <div className="row gap8" style={{ marginBottom: 8 }}>
            <button className="btn" onClick={() => navigate("/")}>
              Back to Home
            </button>
          </div>

          <div className="mutedSmall">
            Enter opportunity number, choose proposal type, complete items, then generate PDF.
          </div>

          <div className="sidebarListHeader" style={{ marginTop: 18 }}>
            <div className="sidebarSectionTitle">Recent Proposals</div>
            <button className="btn btnPrimary" type="button" onClick={startNewProposal}>
              + New Proposal
            </button>
            <div className="mutedSmall">{proposalDocs.length} proposals</div>
          </div>
        </div>

        <div className="docList">
          {proposalDocs.map((d) => {
            const label = d.quote_number || d.id.slice(0, 8);
            const isActive = d.id === selectedId;
            const displayStatus = getDisplayStatus(d);
            const statusClass = getStatusClass(displayStatus);
            const docTypeClass = getDocTypeClass(d);

            return (
              <button
                key={d.id}
                className={`docCard ${docTypeClass} ${isActive ? "active" : ""}`}
                onClick={() => setSelectedId(d.id)}
              >
                <div className="docCardTop">
                  <span className={`pill ${getDisplayDocType(d).replace(/\s+/g, "")}`}>
                    {getDisplayDocType(d)}
                  </span>
                  <span className="docLabel">{label}</span>
                </div>

                <div className={`docMeta statusRow ${statusClass}`}>
                  <span className={`statusDot ${statusClass}`} />
                  <span className="statusText">Status: {displayStatus}</span>
                </div>

                <div className="docMeta muted docSummary">
                  {d.customer_name || d.property_address || ""}
                </div>

                {d.error ? <div className="docError">{d.error}</div> : null}
              </button>
            );
          })}
        </div>
      </aside>

      <main className="main">
        <div className="topBar">
          <div>
            <div className="pageTitle">Proposal Builder</div>
            <div className="pageSub">
              Select a previous proposal on the left, or create a new one below.
            </div>
          </div>
        </div>

        {selected ? (
          <div style={{ marginBottom: 16 }}>
            <div className="topBar">
              <div>
                <div className="pageTitle">
                  {getDisplayDocType(selected)} <span className="muted">—</span>{" "}
                  {selectedLabel}
                </div>
                <div className="pageSub">
                  Status: <b>{getDisplayStatus(selected)}</b>
                  {!selected.styled_draft_s3_key ? (
                    <span className="warnBadge">Draft generating…</span>
                  ) : null}
                </div>
              </div>

              <div className="row gap8">
                <button
                  className="btn btnPrimary"
                  disabled={loading || !selectedId}
                  onClick={onRestyle}
                >
                  {loading ? "Working..." : "Restyle Proposal"}
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
          </div>
        ) : (
          <div className="emptyState" style={{ marginBottom: 16 }}>
            Select a proposal from the left to preview/edit it.
          </div>
        )}

        <div className="panelCard" style={{ marginBottom: 16 }}>
          <div className="sectionTitle">Load Opportunity</div>

          <div className="row gap8">
            <input
              className="input"
              placeholder="Enter opportunity number..."
              value={opportunityNumber}
              onFocus={startNewProposal}
              onChange={(e) => {
                startNewProposal();
                setOpportunityNumber(e.target.value);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") onLoadOpportunity();
              }}
            />

            <button
              className="btn btnPrimary"
              type="button"
              onClick={onLoadOpportunity}
              disabled={loadingOpportunity}
            >
              {loadingOpportunity ? "Loading..." : "Load"}
            </button>
          </div>

          {lookupMsg ? (
            <div className="proposalNotice success" style={{ marginTop: 10 }}>
              <div className="proposalNoticeIcon">✅</div>
              <div>
                <div className="proposalNoticeTitle">Opportunity loaded</div>
                <div className="proposalNoticeText">
                  Proposal information has been filled from BuildOps.
                </div>
              </div>
            </div>
          ) : null}

          {lookupNotices.length > 0 ? (
            <div className="proposalNotice warning" style={{ marginTop: 10 }}>
              <div className="proposalNoticeIcon">ℹ️</div>
              <div>
                <div className="proposalNoticeTitle">Please review</div>
                <div className="proposalNoticeText">
                  {lookupNotices.map((notice, index) => (
                    <div key={index}>{notice}</div>
                  ))}
                </div>
              </div>
            </div>
          ) : null}

          {proposalContacts.length > 1 ? (
            <div className="proposalContactBox">
              <div className="proposalContactHeader">
                <div>
                  <div className="proposalContactTitle">Select Proposal Contact</div>
                  <div className="proposalContactSub">
                    Selected contact is used for the proposal. Other contacts are added
                    to CC.
                  </div>
                </div>
              </div>

              <div className="proposalContactList">
                {proposalContacts.map((contact, index) => {
                  const email = contactEmail(contact);
                  const selectedContact =
                    email &&
                    email.toLowerCase() === fields.contact_email.toLowerCase();

                  return (
                    <button
                      key={`${email || contact.full_name || "contact"}-${index}`}
                      type="button"
                      className={`proposalContactOption ${
                        selectedContact ? "selected" : ""
                      }`}
                      onClick={() => applySelectedContact(contact)}
                    >
                      <div className="proposalContactMain">
                        <div className="proposalContactName">
                          {contact.full_name || "Unnamed Contact"}
                        </div>
                        {selectedContact ? (
                          <span className="proposalSelectedBadge">Selected</span>
                        ) : null}
                      </div>

                      <div className="proposalContactMeta">
                        <span>{email || "No email"}</span>
                        {contact.role ? <span>• {contact.role}</span> : null}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}

          {lookupErr ? (
            <div className="alert err" style={{ marginTop: 10 }}>
              {lookupErr}
            </div>
          ) : null}
        </div>

        <ProposalPanel
          fields={fields}
          onChange={patchFields}
          proposalContacts={proposalContacts}
          onClear={onClearAll}
        />

        <div className="panelCard" style={{ marginTop: 16 }}>
          <div className="sectionTitle">Current Payload Preview</div>
          <pre
            style={{
              margin: 0,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              fontSize: 13,
            }}
          >
            {JSON.stringify(fields, null, 2)}
          </pre>
        </div>
      </main>
    </div>
  );
}