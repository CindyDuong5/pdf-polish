// frontend/src/api.ts
const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

async function httpJson(url: string, init?: RequestInit) {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

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
  return httpJson(`${API_BASE}/api/documents?${usp.toString()}`);
}

export async function getLinks(docId: string) {
  return httpJson(`${API_BASE}/api/documents/${docId}/links`);
}

export async function restyleDoc(docId: string) {
  return httpJson(`${API_BASE}/api/documents/${docId}/restyle`, { method: "POST" });
}

// ✅ NEW
export async function getFields(docId: string) {
  return httpJson(`${API_BASE}/api/documents/${docId}/fields`);
}

// ✅ NEW
export async function saveFinal(docId: string, fields: any) {
  return httpJson(`${API_BASE}/api/documents/${docId}/save-final`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fields }),
  });
}