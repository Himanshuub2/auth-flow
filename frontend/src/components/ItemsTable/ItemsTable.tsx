import { useEffect, useState } from "react";
import {
  listCombinedItems,
  getItemDetail,
  listItemRevisions,
  getItemRevisionSnapshot,
  deleteEvent,
  toggleEventStatus,
  deactivateDocument,
  toggleDocumentStatus,
} from "../../api";
import type { CombinedItem } from "../../types";
import RevisionBrowser from "../EventTable/RevisionBrowser";

interface Props {
  onEditEvent: (event: import("../../types").EventData) => void;
  onEditDocument: (doc: import("../../types").DocumentData) => void;
  refreshKey: number;
}

export default function ItemsTable({ onEditEvent, onEditDocument, refreshKey }: Props) {
  const [items, setItems] = useState<CombinedItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [revisionItemId, setRevisionItemId] = useState<number | null>(null);
  const [revisionItemType, setRevisionItemType] = useState<"event" | "document">("event");

  const load = async () => {
    setLoading(true);
    try {
      const res = await listCombinedItems(page, 20);
      const data = res.data?.data ?? [];
      setItems(data);
      setTotal(res.data?.total ?? 0);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [page, refreshKey]);

  const handleEdit = async (id: number, itemType: "event" | "document") => {
    const res = await getItemDetail(id, itemType);
    const data = res.data?.data;
    if (!data) return;
    if (itemType === "event") onEditEvent(data as import("../../types").EventData);
    else onEditDocument(data as import("../../types").DocumentData);
  };

  const handleDeactivateEvent = async (id: number) => {
    const remarks = prompt("Enter deactivation remarks:");
    if (!remarks?.trim()) return;
    await deleteEvent(id, remarks.trim());
    load();
  };

  const handleToggleEvent = async (id: number) => {
    if (!confirm("Toggle event status?")) return;
    await toggleEventStatus(id);
    load();
  };

  const handleDeactivateDocument = async (id: number) => {
    const remarks = prompt("Enter deactivation remarks:");
    if (!remarks) return;
    await deactivateDocument(id, remarks);
    load();
  };

  const handleToggleDocument = async (id: number,status:string) => {
    const deactivate_remarks = status === "ACTIVE" ? prompt("Enter deactivation remarks:") : null;
    if (!confirm("Toggle document status?")) return;
    await toggleDocumentStatus(id,deactivate_remarks);
    load();
  };

  const totalPages = Math.ceil(total / 20);

  return (
    <div>
      <div style={{ marginBottom: 12, color: "#888", fontSize: 13 }}>{total} item(s)</div>

      {loading ? (
        <p>Loading...</p>
      ) : items.length === 0 ? (
        <p>No items found</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={thStyle}>ID</th>
              <th style={thStyle}>Name</th>
              <th style={thStyle}>Type</th>
              <th style={thStyle}>Version</th>
              <th style={thStyle}>Status</th>
              <th style={thStyle}>Created By</th>
              <th style={thStyle}>Updated</th>
              <th style={thStyle}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr
                key={`${row.item_type}-${row.id}`}
                style={{ background: row.item_type === "event" ? "#b3d9ff" : "#ffcccc", borderBottom: "1px solid black" , borderTop: "1px solid black", borderLeft: "1px solid black", borderRight: "1px solid black", padding: "10px" }}
              >
                <td>{row.id}</td>
                <td>{row.name}</td>
                <td>{row.item_type === "event" ? "Event" : (row.document_type ?? "Document")}</td>
                <td>{row.version_display}</td>
                <td>{row.status}</td>
                <td>{row.created_by_name}</td>
                <td>{new Date(row.updated_at).toLocaleDateString()}</td>
                <td style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <button onClick={() => handleEdit(row.id, row.item_type as "event" | "document")}>Edit</button>
                  <button
                    onClick={() => {
                      setRevisionItemId(row.id);
                      setRevisionItemType(row.item_type as "event" | "document");
                    }}
                  >
                    Revisions
                  </button>
                  {row.item_type === "event" && (row.status === "ACTIVE" || row.status === "INACTIVE") && (
                    <button onClick={() => handleToggleEvent(row.id)}>Toggle</button>
                  )}
                  {row.item_type === "event" && row.status !== "INACTIVE" && (
                    <button onClick={() => handleDeactivateEvent(row.id)}>Deactivate</button>
                  )}
                  {row.item_type === "document" && (row.status === "ACTIVE" || row.status === "INACTIVE") && (
                    <button onClick={() => handleToggleDocument(row.id, row.status)}>Toggle</button>
                  )}
                  {row.item_type === "document" && row.status !== "INACTIVE" && (
                    <button onClick={() => handleDeactivateDocument(row.id)}>Deactivate</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {totalPages > 1 && (
        <div style={{ marginTop: 12, display: "flex", gap: 6 }}>
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</button>
          <span>Page {page} / {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}

      {revisionItemId !== null && (
        <RevisionBrowser
          eventId={revisionItemId}
          itemType={revisionItemType}
          onClose={() => setRevisionItemId(null)}
          listRevisions={() => listItemRevisions(revisionItemId, revisionItemType)}
          getRevisionSnapshot={(mv, rn) =>
            getItemRevisionSnapshot(revisionItemId, mv, rn, revisionItemType)
          }
        />
      )}
    </div>
  );
}

const thStyle: React.CSSProperties = { padding: "8px 10px", textAlign: "left", borderBottom: "1px solid #ddd" };
