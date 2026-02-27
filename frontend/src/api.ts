// frontend/src/api.ts
const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

export async function listDocuments(params: {
  q?: string;
  doc_type?: string;
  status?: string;
  limit?: number;
}) {
  const usp = new URLSearchParams();
  if (params.q) usp.set("q", params.q);
  if (params.doc_type) usp.set("doc_type", params.doc_type);
  if (params.status) usp.set("status", params.status);
  usp.set("limit", String(params.limit ?? 50));

  const res = await fetch(`${API_BASE}/api/documents?${usp.toString()}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getLinks(docId: string) {
  const res = await fetch(`${API_BASE}/api/documents/${docId}/links`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function restyleDoc(docId: string) {
  const res = await fetch(`${API_BASE}/api/documents/${docId}/restyle`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}