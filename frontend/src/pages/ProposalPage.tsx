// frontend/src/pages/ProposalPage.tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { getProposalOpportunity, friendlyErrorMessage } from "../api";
import ProposalPanel from "../panels/proposal/ProposalPanel";
import type {
  ProposalContact,
  ProposalStaticFields,
  ProposalItem,
} from "../types";
import "../styles.css";

function todayIsoDate(): string {
  const d = new Date();
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

const DEFAULT_SCOPE_SUMMARY = `Complete the Following Fire & Life Safety Inspections and Testing in Accordance with OFC, OBC, CAN/ULC-S536, NFPA 25, NFPA 10, CSA B64.`;

const DEFAULT_EXCLUSIONS = `- Job to be completed during regular hours 08:00-16:30 Monday to Friday
- Pricing is subject to parts availability and all items being done concurrently`;

function parseMoney(value: string | number | null | undefined): number | null {
  if (value == null) return null;
  const raw = String(value).trim();
  if (!raw) return null;
  const cleaned = raw.replace(/[^0-9.\-]/g, "");
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

    items: [
      {
        item: "",
        description: "",
        price: "",
      },
    ],
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
    ...(Array.isArray(item.proposal_send_contacts)
      ? item.proposal_send_contacts
      : []),
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

  function patchFields(patch: Partial<ProposalStaticFields>) {
    setFields((prev) => calculateDerivedFields({ ...prev, ...patch }));
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
          "No property id found. Customer information was used as the property information. You can manually change it if needed."
        );
      }

      const contacts = getAllProposalContacts(item);
      const source = item.contact_source || "manual";

      setProposalContacts(contacts);

      if (contacts.length === 0) {
        notices.push(
          "No quote/all/proposal contact found from property or customer representatives. Please manually enter the Prepared For contact."
        );
      } else if (contacts.length === 1) {
        notices.push(
          `Contact found from ${source} representative and selected automatically.`
        );
        applySelectedContact(contacts[0]);
      } else {
        notices.push(
          `${contacts.length} contacts found. One contact will be used to build the proposal. The other contacts will be added to CC when sending.`
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
            Enter opportunity number, choose proposal type, complete items, then
            generate PDF.
          </div>
        </div>
      </aside>

      <main className="main">
        <div className="topBar">
          <div>
            <div className="pageTitle">Create Proposal</div>
            <div className="pageSub">
              Load proposal data from BuildOps opportunity number
            </div>
          </div>
        </div>

        <div className="panelCard" style={{ marginBottom: 16 }}>
          <div className="sectionTitle">Load Opportunity</div>

          <div className="row gap8">
            <input
              className="input"
              placeholder="Enter opportunity number..."
              value={opportunityNumber}
              onChange={(e) => setOpportunityNumber(e.target.value)}
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
                    Selected contact is used for the proposal. Other contacts are added to CC.
                  </div>
                </div>
              </div>

              <div className="proposalContactList">
                {proposalContacts.map((contact, index) => {
                  const email = contactEmail(contact);
                  const selected =
                    email &&
                    email.toLowerCase() === fields.contact_email.toLowerCase();

                  return (
                    <button
                      key={`${email || contact.full_name || "contact"}-${index}`}
                      type="button"
                      className={`proposalContactOption ${selected ? "selected" : ""}`}
                      onClick={() => applySelectedContact(contact)}
                    >
                      <div className="proposalContactMain">
                        <div className="proposalContactName">
                          {contact.full_name || "Unnamed Contact"}
                        </div>
                        {selected ? (
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