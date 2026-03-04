// frontend/src/panels/DocumentPanel.tsx
import type { DocRow, Links } from "../types";
import ServiceQuotePanel from "./serviceQuote/ServiceQuotePanel";
import InvoicePanel from "./invoice/InvoicePanel";

export default function DocumentPanel(props: {
  selected: DocRow;
  selectedId: string; // must be a real string (MainApp will pass selectedId!)
  links: Links | null;
  reloadKey: number;

  onRestyle: () => Promise<void>;
  loading: boolean;
  onLinksUpdated: (links: Links) => void;
}) {
  const type = (props.selected.doc_type || "").toUpperCase();

  if (type.includes("SERVICE_QUOTE")) {
    return <ServiceQuotePanel {...props} />;
  }

  if (type.includes("INVOICE")) {
    return <InvoicePanel {...props} onLinksUpdated={props.onLinksUpdated} />;
  }

  return (
    <div className="card" style={{ padding: 12 }}>
      <div style={{ fontWeight: 900, marginBottom: 6 }}>Not supported yet</div>
      <div className="mutedSmall">
        Editor not enabled for this document type yet: <b>{props.selected.doc_type || "UNKNOWN"}</b>
      </div>
    </div>
  );
}