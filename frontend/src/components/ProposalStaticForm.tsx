// frontend/src/components/ProposalStaticForm.tsx
import type { ProposalItem, ProposalStaticFields } from "../types";

type Props = {
  fields: ProposalStaticFields;
  onChange: (patch: Partial<ProposalStaticFields>) => void;
};

const PREPARED_BY_OPTIONS = ["Aidan Quinn", "Nick Janevski", "Rob Felstead", "Sarah Caley"];
const PROPOSAL_TYPE_OPTIONS = ["Project", "Service", "Inspection"];

function sectionCardStyle(): React.CSSProperties {
  return {
    border: "1px solid rgba(0,0,0,0.08)",
    borderRadius: 14,
    padding: 16,
    background: "#fff",
    boxShadow: "0 2px 10px rgba(0,0,0,0.04)",
  };
}

function sectionTitleStyle(): React.CSSProperties {
  return {
    fontWeight: 800,
    fontSize: 16,
    marginBottom: 14,
  };
}

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

function threeColRowStyle(): React.CSSProperties {
  return {
    display: "grid",
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
    gap: 14,
  };
}

function twoColRowStyle(): React.CSSProperties {
  return {
    display: "grid",
    gridTemplateColumns: "minmax(240px, 0.9fr) minmax(0, 1.8fr)",
    gap: 14,
  };
}

export default function ProposalStaticForm({ fields, onChange }: Props) {
  function updateItemRow(index: number, patch: Partial<ProposalItem>) {
    const nextItems = [...fields.items];
    nextItems[index] = { ...nextItems[index], ...patch };
    onChange({ items: nextItems });
  }

  function addItemRow() {
    onChange({
      items: [
        ...fields.items,
        {
          item: "",
          description: "",
          price: "",
        },
      ],
    });
  }

  function removeItemRow(index: number) {
    const nextItems = fields.items.filter((_, i) => i !== index);
    onChange({
      items:
        nextItems.length > 0
          ? nextItems
          : [
              {
                item: "",
                description: "",
                price: "",
              },
            ],
    });
  }

  const numericItemPrices = fields.items
    .map((row) => parseMoney(row.price))
    .filter((v): v is number => v !== null);

  const calculatedItemsSubtotal = numericItemPrices.reduce((sum, n) => sum + n, 0);

  const manualSubtotal = parseMoney(fields.subtotal);
  const hasAnyNumericItemPrice = numericItemPrices.length > 0;

  const effectiveSubtotal = hasAnyNumericItemPrice
    ? calculatedItemsSubtotal
    : (manualSubtotal ?? 0);

  const taxRate = parseMoney(fields.tax_rate) ?? 13;
  const calculatedTax = effectiveSubtotal * (taxRate / 100);
  const calculatedTotal = effectiveSubtotal + calculatedTax;

  const hasManualSubtotal = String(fields.subtotal || "").trim().length > 0;

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div style={sectionCardStyle()}>
        <div style={sectionTitleStyle()}>Prepared For</div>
        <div style={threeColRowStyle()}>
          <div>
            <label className="label">Contact Name</label>
            <input
              className="input"
              placeholder="Enter contact name"
              value={fields.contact_name}
              onChange={(e) => onChange({ contact_name: e.target.value })}
            />
          </div>

          <div>
            <label className="label">Contact Email</label>
            <input
              className="input"
              placeholder="Enter contact email"
              value={fields.contact_email}
              onChange={(e) => onChange({ contact_email: e.target.value })}
            />
          </div>

          <div>
            <label className="label">Contact Phone</label>
            <input
              className="input"
              placeholder="Enter contact phone"
              value={fields.contact_phone}
              onChange={(e) => onChange({ contact_phone: e.target.value })}
            />
          </div>
        </div>
      </div>

      <div style={sectionCardStyle()}>
        <div style={sectionTitleStyle()}>Company</div>
        <div style={twoColRowStyle()}>
          <div>
            <label className="label">Customer Name</label>
            <input
              className="input"
              value={fields.customer_name}
              onChange={(e) => onChange({ customer_name: e.target.value })}
            />
          </div>

          <div>
            <label className="label">Customer Address</label>
            <input
              className="input"
              value={fields.customer_address}
              onChange={(e) => onChange({ customer_address: e.target.value })}
            />
          </div>
        </div>
      </div>

      <div style={sectionCardStyle()}>
        <div style={sectionTitleStyle()}>Property</div>
        <div style={twoColRowStyle()}>
          <div>
            <label className="label">Property Name</label>
            <input
              className="input"
              value={fields.property_name}
              onChange={(e) => onChange({ property_name: e.target.value })}
            />
          </div>

          <div>
            <label className="label">Property Address</label>
            <input
              className="input"
              value={fields.property_address}
              onChange={(e) => onChange({ property_address: e.target.value })}
            />
          </div>
        </div>
      </div>

      <div style={sectionCardStyle()}>
        <div style={sectionTitleStyle()}>Proposal Details</div>
        <div className="proposalFormGrid">
          <div>
            <label className="label">Proposal Number</label>
            <input
              className="input"
              placeholder="Enter proposal number"
              value={fields.proposal_number}
              onChange={(e) => onChange({ proposal_number: e.target.value })}
            />
          </div>

          <div>
            <label className="label">Proposal Date</label>
            <input
              type="date"
              className="input"
              value={fields.proposal_date}
              onChange={(e) => onChange({ proposal_date: e.target.value })}
            />
          </div>

          <div>
            <label className="label">Prepared By</label>
            <select
              className="input"
              value={fields.prepared_by}
              onChange={(e) => onChange({ prepared_by: e.target.value })}
            >
              <option value="">Select user...</option>
              {PREPARED_BY_OPTIONS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="label">Proposal Type</label>
            <select
              className="input"
              value={fields.proposal_type}
              onChange={(e) => onChange({ proposal_type: e.target.value })}
            >
              <option value="">Select type...</option>
              {PROPOSAL_TYPE_OPTIONS.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div style={sectionCardStyle()}>
        <div style={sectionTitleStyle()}>Scope of Work</div>
        <div>
          <label className="label">Scope Summary</label>
          <textarea
            className="input"
            rows={6}
            value={fields.scope_summary}
            onChange={(e) => onChange({ scope_summary: e.target.value })}
          />
        </div>
      </div>

      <div style={sectionCardStyle()}>
        <div style={sectionTitleStyle()}>Items</div>

        <div style={{ display: "grid", gap: 12 }}>
          {fields.items.map((row, index) => (
            <div
              key={index}
              style={{
                display: "grid",
                gridTemplateColumns: "1.1fr 2.4fr 0.9fr auto",
                gap: 10,
                alignItems: "start",
                padding: 12,
                border: "1px solid rgba(0,0,0,0.07)",
                borderRadius: 12,
                background: "#fafafa",
              }}
            >
              <div>
                <label className="label">Item</label>
                <input
                  className="input"
                  placeholder="Item"
                  value={row.item}
                  onChange={(e) => updateItemRow(index, { item: e.target.value })}
                />
              </div>

              <div>
                <label className="label">Description</label>
                <textarea
                  className="input"
                  placeholder="Item description"
                  rows={3}
                  value={row.description}
                  onChange={(e) =>
                    updateItemRow(index, { description: e.target.value })
                  }
                />
              </div>

              <div>
                <label className="label">Price</label>
                <input
                  className="input"
                  placeholder="1000.00 or TBD"
                  value={row.price}
                  onChange={(e) => updateItemRow(index, { price: e.target.value })}
                />
              </div>

              <div style={{ paddingTop: 26 }}>
                <button
                  type="button"
                  className="btn"
                  onClick={() => removeItemRow(index)}
                >
                  Remove
                </button>
              </div>
            </div>
          ))}

          <div>
            <button type="button" className="btn btnPrimary" onClick={addItemRow}>
              Add Item
            </button>
          </div>
        </div>
      </div>

      <div style={sectionCardStyle()}>
        <div style={sectionTitleStyle()}>Subtotal / Tax / Total</div>

        <div className="proposalFormGrid">
          <div>
            <label className="label">Calculated Items Subtotal</label>
            <input className="input" value={money2(calculatedItemsSubtotal)} readOnly />
            <div className="mutedSmall">
              Only numeric item prices are included. Values like TBD are ignored.
            </div>
          </div>

          <div>
            <label className="label">Manual Subtotal</label>
            <input
              className="input"
              placeholder="Leave blank to use item total"
              value={fields.subtotal}
              onChange={(e) => onChange({ subtotal: e.target.value })}
            />
            <div className="mutedSmall">
              If item prices are entered → subtotal is auto-calculated.  
              If no item prices → you can enter subtotal manually.
            </div>
          </div>

          <div>
            <label className="label">Tax Rate (%)</label>
            <input
              className="input"
              value={fields.tax_rate}
              onChange={(e) => onChange({ tax_rate: e.target.value })}
            />
          </div>

          <div>
            <label className="label">Tax</label>
            <input className="input" value={money2(calculatedTax)} readOnly />
          </div>

          <div>
            <label className="label">Total</label>
            <input className="input" value={money2(calculatedTotal)} readOnly />
          </div>

          <div style={{ gridColumn: "1 / -1" }}>
            <div
              style={{
                marginTop: 4,
                padding: 12,
                borderRadius: 12,
                background: "#f6f8fb",
                border: "1px solid rgba(0,0,0,0.06)",
                fontSize: 13,
              }}
            >
              <strong>Using:</strong>{" "}
              {hasAnyNumericItemPrice
                ? "Auto-calculated from item prices"
                : hasManualSubtotal
                ? "Manual subtotal entered by user"
                : "No prices entered"}
            </div>
          </div>
        </div>
      </div>

      <div style={sectionCardStyle()}>
        <div style={sectionTitleStyle()}>Exclusions</div>
        <div>
          <label className="label">Exclusions</label>
          <textarea
            className="input"
            rows={5}
            value={fields.exclusions}
            onChange={(e) => onChange({ exclusions: e.target.value })}
          />
        </div>
      </div>
    </div>
  );
}