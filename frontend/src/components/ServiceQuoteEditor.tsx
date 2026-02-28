// frontend/src/components/ServiceQuoteEditor.tsx
import type { ServiceQuoteFields } from "../types";

function Field({
  label,
  value,
  onChange,
  readOnly = false,
}: {
  label: string;
  value: string;
  onChange?: (v: string) => void;
  readOnly?: boolean;
}) {
  return (
    <label style={{ display: "block", marginBottom: 10 }}>
      <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>{label}</div>
      <input
        value={value || ""}
        readOnly={readOnly}
        onChange={(e) => onChange?.(e.target.value)}
        style={{
          width: "100%",
          padding: 8,
          border: "1px solid #ddd",
          borderRadius: 8,
          background: readOnly ? "#fafafa" : "white",
        }}
      />
    </label>
  );
}

function TextArea({
  label,
  value,
  onChange,
  rows = 4,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
}) {
  return (
    <label style={{ display: "block", marginBottom: 10 }}>
      <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>{label}</div>
      <textarea
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        rows={rows}
        style={{ width: "100%", padding: 8, border: "1px solid #ddd", borderRadius: 8 }}
      />
    </label>
  );
}

export default function ServiceQuoteEditor({
  value,
  onChange,
  onSave,
  canSave = true,
  saving = false,
}: {
  value: ServiceQuoteFields;
  onChange: (v: ServiceQuoteFields) => void;
  onSave?: () => void;
  canSave?: boolean;
  saving?: boolean;
}) {
  const v = value;

  function set<K extends keyof ServiceQuoteFields>(key: K, val: ServiceQuoteFields[K]) {
    onChange({ ...v, [key]: val });
  }

  return (
    <div style={{ border: "1px solid #ddd", borderRadius: 12, padding: 12, marginTop: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontWeight: 900 }}>Editable Fields (Service Quote)</div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 10 }}>
        <div>
          <div style={{ fontWeight: 800, marginBottom: 6 }}>Client</div>
          <Field label="Client Name" value={v.client_name} onChange={(x) => set("client_name", x)} />
          <Field label="Client Phone" value={v.client_phone} onChange={(x) => set("client_phone", x)} />
          <Field label="Client Email" value={v.client_email} onChange={(x) => set("client_email", x)} />
        </div>

        <div>
          <div style={{ fontWeight: 800, marginBottom: 6 }}>Quote</div>
          <Field label="Quote Number" value={v.quote_number} onChange={(x) => set("quote_number", x)} />
          <Field label="Quote Date" value={v.quote_date} onChange={(x) => set("quote_date", x)} />
        </div>

        <div>
          <div style={{ fontWeight: 800, marginBottom: 6 }}>Company</div>
          <Field label="Company Name" value={v.company_name} onChange={(x) => set("company_name", x)} />
          <TextArea label="Company Address" value={v.company_address} onChange={(x) => set("company_address", x)} />
        </div>

        <div>
          <div style={{ fontWeight: 800, marginBottom: 6 }}>Property</div>
          <Field label="Property Name" value={v.property_name} onChange={(x) => set("property_name", x)} />
          <TextArea label="Property Address" value={v.property_address} onChange={(x) => set("property_address", x)} />
        </div>
      </div>

      <TextArea
        label="Scope / Quote Description"
        value={v.quote_description}
        onChange={(x) => set("quote_description", x)}
        rows={5}
      />

      <div style={{ marginTop: 10, fontWeight: 800 }}>Items</div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>
        {(v.items || []).map((it, idx) => (
          <div key={idx} style={{ border: "1px solid #eee", borderRadius: 10, padding: 10 }}>
            <div style={{ display: "flex", gap: 10 }}>
              <div style={{ flex: 2 }}>
                <Field
                  label="Item Name"
                  value={it.name}
                  onChange={(x) => {
                    const items = [...(v.items || [])];
                    items[idx] = { ...items[idx], name: x };
                    set("items", items);
                  }}
                />
              </div>
              <div style={{ flex: 1 }}>
                <Field
                  label="Price"
                  value={it.price}
                  onChange={(x) => {
                    const items = [...(v.items || [])];
                    items[idx] = { ...items[idx], price: x };
                    set("items", items);
                  }}
                />
              </div>
            </div>

            <TextArea
              label="Item Description (bullets or lines)"
              value={it.description}
              onChange={(x) => {
                const items = [...(v.items || [])];
                items[idx] = { ...items[idx], description: x };
                set("items", items);
              }}
              rows={4}
            />

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button
                onClick={() => {
                  const items = [...(v.items || [])];
                  items.splice(idx, 1);
                  set("items", items);
                }}
                style={{
                  padding: "8px 10px",
                  borderRadius: 10,
                  border: "1px solid #ddd",
                  background: "white",
                  cursor: "pointer",
                }}
              >
                Remove Item
              </button>
            </div>
          </div>
        ))}

        <button
          onClick={() => set("items", [...(v.items || []), { name: "", price: "", description: "" }])}
          style={{
            padding: "10px 12px",
            borderRadius: 10,
            border: "1px solid #ddd",
            background: "white",
            cursor: "pointer",
            alignSelf: "flex-start",
          }}
        >
          + Add Item
        </button>
      </div>

      {/* Totals: computed, read-only */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginTop: 12 }}>
        <Field label="Subtotal" value={v.subtotal} readOnly />
        <Field label="Tax" value={v.tax} readOnly />
        <Field label="Total" value={v.total} readOnly />
      </div>

      <div style={{ marginTop: 10, fontSize: 12, color: "#666" }}>
        Totals are auto-calculated from item prices (HST included).
      </div>

      {/* Bottom action bar (only show if onSave is provided) */}
      {onSave ? (
        <div
          style={{
            marginTop: 14,
            padding: 12,
            borderTop: "1px solid #eee",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 12,
            background: "#fafafa",
            borderRadius: 12,
          }}
        >
          <div style={{ fontSize: 12, color: "#666" }}>
            <div style={{ fontWeight: 900, color: "#111", fontSize: 13 }}>Ready to finalize?</div>
            <div>
              Click <b>Save Final</b> to lock these fields into the Final PDF.
            </div>
          </div>

          <button
            onClick={() => onSave?.()}
            disabled={!canSave || saving}
            style={{
              padding: "12px 16px",
              borderRadius: 14,
              border: "1px solid #ddd",
              background: !canSave || saving ? "#f3f3f3" : "#111",
              color: !canSave || saving ? "#888" : "white",
              cursor: !canSave || saving ? "not-allowed" : "pointer",
              fontWeight: 900,
              fontSize: 14,
              minWidth: 180,
              boxShadow: !canSave || saving ? "none" : "0 10px 24px rgba(0,0,0,0.14)",
            }}
          >
            {saving ? "Saving..." : "✅ Save Final"}
          </button>
        </div>
      ) : null}
    </div>
  );
}