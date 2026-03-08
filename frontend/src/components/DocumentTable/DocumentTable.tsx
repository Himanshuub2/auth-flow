import { useEffect, useState } from "react";
import { listDocuments, getDocument, deactivateDocument, toggleDocumentStatus } from "../../api";
import type { DocumentData, EventStatus, DocumentType } from "../../types";

interface Props {
  onEdit: (doc: DocumentData) => void;
  refreshKey: number;
}

export default function DocumentTable({ onEdit, refreshKey }: Props) {
  const [docs, setDocs] = useState<DocumentData[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<EventStatus | "">("");
  const [typeFilter, setTypeFilter] = useState<DocumentType | "">("");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await listDocuments(page, 20, statusFilter || undefined, typeFilter || undefined);
      setDocs(res.data.data ?? []);
      setTotal(res.data.total ?? 0);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [page, statusFilter, typeFilter, refreshKey]);

  const handleDeactivate = async (doc: DocumentData) => {
    const remarks = prompt("Enter deactivation remarks:");
    if (!remarks) return;
    await deactivateDocument(doc.id, remarks);
    load();
  };

  const handleToggle = async (doc: DocumentData) => {
    const action = doc.status === "ACTIVE" ? "deactivate" : "activate";
    if (!confirm(`${action.charAt(0).toUpperCase() + action.slice(1)} this document?`)) return;
    await toggleDocumentStatus(doc.id);
    load();
  };

  const handleEdit = async (doc: DocumentData) => {
    const res = await getDocument(doc.id);
    const body = res.data as { data?: DocumentData };
    if (body?.data) onEdit(body.data);
  };

  const totalPages = Math.ceil(total / 20);

  return (
    <div>
      <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
        <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value as EventStatus | ""); setPage(1); }}>
          <option value="">All Statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="ACTIVE">Active</option>
          <option value="INACTIVE">Inactive</option>
        </select>
        <select value={typeFilter} onChange={(e) => { setTypeFilter(e.target.value as DocumentType | ""); setPage(1); }}>
          <option value="">All Types</option>
          <option value="POLICY">Policy</option>
          <option value="GUIDANCE_NOTE">Guidance Note</option>
          <option value="LAW_REGULATION">Law/Regulation</option>
          <option value="TRAINING_MATERIAL">Training Material</option>
          <option value="EWS">EWS</option>
          <option value="FAQ">FAQ</option>
          <option value="LATEST_NEWS">Latest News</option>
          <option value="ANNOUNCEMENTS">Announcements</option>
        </select>
      </div>

      {loading && <p>Loading...</p>}
      <table style={{ width: "100%", borderCollapse: "collapse" , }}>
        <thead>
          <tr>
            <th>ID</th><th>Name</th><th>Type</th><th>Version</th><th>Status</th><th>Created</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {docs.map((d) => (
            <tr key={d.id} style={{ backgroundColor:"green" }}>
              <td>{d.id}</td>
              <td>{d.name}</td>
              <td>{d.document_type}</td>
              <td>{d.version_display}</td>
              <td>{d.status}</td>
              <td>{new Date(d.created_at).toLocaleDateString()}</td>
              <td style={{ display: "flex", gap: 6 }}>

                <button onClick={() => handleEdit(d)}>Edit</button>
                {(d.status === "ACTIVE" || d.status === "INACTIVE") && (
                  <button onClick={() => handleToggle(d)}>
                    {d.status === "ACTIVE" ? "Deactivate" : "Activate"}
                  </button>
                )}
                {d.status !== "INACTIVE" && (
                  <button onClick={() => handleDeactivate(d)}>Deactivate</button>
                )}
              </td>
            </tr>
          ))}
          {!loading && docs.length === 0 && (
            <tr><td colSpan={7} style={{ textAlign: "center" }}>No documents found</td></tr>
          )}
        </tbody>
      </table>

      {totalPages > 1 && (
        <div style={{ marginTop: 12, display: "flex", gap: 6 }}>
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</button>
          <span>Page {page} / {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}
    </div>
  );
}
