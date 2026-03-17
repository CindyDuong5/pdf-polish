// frontend/src/components/AdditionalDocumentsPanel.tsx
import { useEffect, useMemo, useRef, useState } from "react";
import {
  addAdditionalDocumentByUrl,
  deleteAdditionalDocument,
  listAdditionalDocuments,
  uploadAdditionalDocument,
  type AdditionalDocumentItem,
  friendlyErrorMessage,
} from "../api";

function formatBytes(v?: number | null) {
  const n = Number(v || 0);
  if (!n) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

type Props = {
  docId: string;
  disabled?: boolean;
  title?: string;
  helpText?: string;
  onChanged?: (items: AdditionalDocumentItem[]) => void;
};

export default function AdditionalDocumentsPanel(props: Props) {
  const [items, setItems] = useState<AdditionalDocumentItem[]>([]);
  const [loading, setLoading] = useState(false);

  const [uploading, setUploading] = useState(false);
  const [addingUrl, setAddingUrl] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const [displayName, setDisplayName] = useState("");
  const [fileUrl, setFileUrl] = useState("");

  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  async function loadItems() {
    if (!props.docId) return;
    setLoading(true);
    setErr(null);

    try {
      const res = await listAdditionalDocuments(props.docId);
      const next = Array.isArray(res?.items) ? res.items : [];
      setItems(next);
      props.onChanged?.(next);
    } catch (e: any) {
      setErr(friendlyErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadItems();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.docId]);

  const totalCount = useMemo(() => items.length, [items]);

  async function onPickFile(file: File | null) {
    if (!file || !props.docId) return;

    setMsg(null);
    setErr(null);

    const nextDisplayName =
      displayName.trim() || file.name.replace(/\.[^.]+$/, "").trim() || file.name;

    try {
      setUploading(true);
      await uploadAdditionalDocument(props.docId, file, nextDisplayName);
      setDisplayName("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      await loadItems();
      setMsg("Additional document uploaded ✅");
    } catch (e: any) {
      setErr(friendlyErrorMessage(e));
    } finally {
      setUploading(false);
    }
  }

  async function onAddByUrl() {
    if (!props.docId) return;

    const trimmedUrl = fileUrl.trim();
    const trimmedName = displayName.trim();

    if (!trimmedUrl) {
      setErr("Please enter a PDF URL.");
      return;
    }
    if (!trimmedName) {
      setErr("Please enter a display name.");
      return;
    }

    setMsg(null);
    setErr(null);

    try {
      setAddingUrl(true);
      await addAdditionalDocumentByUrl(props.docId, {
        file_url: trimmedUrl,
        display_name: trimmedName,
      });
      setFileUrl("");
      setDisplayName("");
      await loadItems();
      setMsg("Additional document added by URL ✅");
    } catch (e: any) {
      setErr(friendlyErrorMessage(e));
    } finally {
      setAddingUrl(false);
    }
  }

  async function onDelete(item: AdditionalDocumentItem) {
    if (!props.docId) return;

    const ok = window.confirm(`Delete "${item.display_name}"?`);
    if (!ok) return;

    setMsg(null);
    setErr(null);

    try {
      setDeletingId(item.id);
      await deleteAdditionalDocument(props.docId, item.id);
      await loadItems();
      setMsg("Additional document removed ✅");
    } catch (e: any) {
      setErr(friendlyErrorMessage(e));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div
      style={{
        marginTop: 12,
        border: "1px solid #e8e8e8",
        borderRadius: 16,
        background: "#fafafa",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: "14px 16px 10px 16px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 12,
        }}
      >
        <div style={{ fontWeight: 800, fontSize: 18, lineHeight: 1.1 }}>
          {props.title || "Additional Documents"}
        </div>
        <div
          className="mutedSmall"
          style={{ maxWidth: 260, textAlign: "left" }}
        >
          {props.helpText || "Upload or add extra files to include with this email."}
        </div>
      </div>

      <div style={{ padding: "0 16px 16px 16px" }}>
        {msg ? <div className="alert ok">{msg}</div> : null}
        {err ? <div className="alert err">{err}</div> : null}

        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>Display Name</div>
          <input
            className="input"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Ex: Deficiency Photos"
            disabled={props.disabled || uploading || addingUrl}
          />
          <div className="mutedSmall" style={{ marginTop: 6 }}>
            This is the file name the client will see in the email.
          </div>
        </div>

        <div
          style={{
            border: "1px solid #ececec",
            borderRadius: 12,
            background: "#fff",
            padding: 12,
            marginBottom: 12,
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 6 }}>Upload File</div>
          <input
            ref={fileInputRef}
            type="file"
            onChange={(e) => onPickFile(e.target.files?.[0] || null)}
            disabled={props.disabled || uploading || addingUrl}
          />
          <div className="mutedSmall" style={{ marginTop: 8 }}>
            Allowed: PDF, JPG, JPEG, PNG. Max 10 MB.
          </div>
        </div>

        <div
          style={{
            border: "1px solid #ececec",
            borderRadius: 12,
            background: "#fff",
            padding: 12,
            marginBottom: 16,
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 6 }}>Add by URL</div>
          <input
            className="input"
            value={fileUrl}
            onChange={(e) => setFileUrl(e.target.value)}
            placeholder="https://example.com/file.pdf"
            disabled={props.disabled || uploading || addingUrl}
          />
          <div className="mutedSmall" style={{ marginTop: 8, marginBottom: 10 }}>
            Please use a direct PDF link. The system will download the PDF from that URL and attach it to the email.
          </div>

          <button
            className="btn btnGhost"
            onClick={onAddByUrl}
            disabled={props.disabled || uploading || addingUrl}
          >
            {addingUrl ? "Adding..." : "Add PDF by URL"}
          </button>
        </div>

        <div style={{ fontWeight: 800, marginBottom: 8 }}>
          Attached Additional Documents ({totalCount})
        </div>

        {loading ? (
          <div className="mutedSmall">Loading additional documents...</div>
        ) : items.length === 0 ? (
          <div
            className="mutedSmall"
            style={{
              border: "1px dashed #d8d8d8",
              borderRadius: 12,
              padding: 12,
              background: "#fff",
            }}
          >
            No additional documents added yet.
          </div>
        ) : (
          <div style={{ display: "grid", gap: 10 }}>
            {items.map((item) => (
              <div
                key={item.id}
                style={{
                  border: "1px solid #e9e9e9",
                  borderRadius: 12,
                  padding: 12,
                  background: "#fff",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: 12,
                }}
              >
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div
                    style={{
                      fontWeight: 800,
                      fontSize: 15,
                      lineHeight: 1.25,
                      marginBottom: 2,
                    }}
                  >
                    {item.display_name}
                  </div>
                  <div className="mutedSmall" style={{ lineHeight: 1.35 }}>
                    {[item.original_filename, item.content_type, formatBytes(item.file_size)]
                      .filter(Boolean)
                      .join(" • ")}
                  </div>
                </div>

                <button
                  className="btn btnGhost"
                  onClick={() => onDelete(item)}
                  disabled={props.disabled || deletingId === item.id}
                >
                  {deletingId === item.id ? "Deleting..." : "Delete"}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}