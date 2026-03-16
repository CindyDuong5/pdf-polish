// frontend/src/panels/DocumentPanel.tsx
import type { DocRow, Links } from "../types";
import ServiceQuotePanel from "./serviceQuote/ServiceQuotePanel";
import InvoicePanel from "./invoice/InvoicePanel";

export default function DocumentPanel(props: {
  selected: DocRow;
  selectedId: string;
  links: Links | null;
  reloadKey: number;
  onRestyle: () => Promise<void>;
  loading: boolean;
  onLinksUpdated: (links: Links) => void;
  onResolvedDocId: (docId: string) => void;
}) {
  const type = (props.selected.doc_type || "").toUpperCase();

  if (
    type.includes("SERVICE_QUOTE") ||
    type.includes("PROJECT_QUOTE") ||
    type.includes("QUOTE")
  ) {
    return (
      <ServiceQuotePanel
        selected={props.selected}
        selectedId={props.selectedId}
        links={props.links}
        reloadKey={props.reloadKey}
        onRestyle={props.onRestyle}
        loading={props.loading}
        onLinksUpdated={props.onLinksUpdated}
        onResolvedDocId={props.onResolvedDocId}
      />
    );
  }

  if (type.includes("INVOICE")) {
    return (
      <InvoicePanel
        selected={props.selected}
        selectedId={props.selectedId}
        links={props.links}
        reloadKey={props.reloadKey}
        loading={props.loading}
        onLinksUpdated={props.onLinksUpdated}
      />
    );
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