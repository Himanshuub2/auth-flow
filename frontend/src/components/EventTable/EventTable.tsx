import { useEffect, useState } from "react";
import { listEvents, deleteEvent, toggleEventStatus } from "../../api";
import type { EventData, EventStatus } from "../../types";
import RevisionBrowser from "./RevisionBrowser";

interface Props {
  onEdit: (event: EventData) => void;
  refreshKey: number;
}

export default function EventTable({ onEdit, refreshKey }: Props) {
  const [events, setEvents] = useState<EventData[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<EventStatus | "">("");
  const [revisionEventId, setRevisionEventId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  const loadEvents = async () => {
    setLoading(true);
    try {
      const res = await listEvents(page, 20, statusFilter || undefined);
      setEvents(res.data);
      setTotal(res.total);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadEvents();
  }, [page, statusFilter, refreshKey]);

  const handleDelete = async (id: number) => {
    if (!confirm("Deactivate this event?")) return;
    await deleteEvent(id);
    loadEvents();
  };

  const handleToggle = async (ev: EventData) => {
    const action = ev.status === "ACTIVE" ? "deactivate" : "activate";
    if (!confirm(`${action.charAt(0).toUpperCase() + action.slice(1)} this event?`)) return;
    await toggleEventStatus(ev.id);
    loadEvents();
  };

  const statusBadge = (s: EventStatus) => {
    const colors: Record<EventStatus, { bg: string; text: string }> = {
      DRAFT: { bg: "#fff3e0", text: "#e65100" },
      PUBLISHED: { bg: "#e8f5e9", text: "#2e7d32" },
      ACTIVE: { bg: "#e3f2fd", text: "#1565c0" },
      INACTIVE: { bg: "#f5f5f5", text: "#757575" },
    };
    const c = colors[s];
    return (
      <span style={{ background: c.bg, color: c.text, padding: "3px 10px", borderRadius: 12, fontSize: 12, fontWeight: 600 }}>
        {s}
      </span>
    );
  };

  const totalPages = Math.ceil(total / 20);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div>
          <label style={{ fontWeight: 600, marginRight: 8 }}>Filter:</label>
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value as EventStatus | ""); setPage(1); }}
            style={{ padding: "6px 10px", borderRadius: 4, border: "1px solid #ccc" }}
          >
            <option value="">All</option>
            <option value="DRAFT">Draft</option>
            <option value="PUBLISHED">Published</option>
            <option value="ACTIVE">Active</option>
            <option value="INACTIVE">Inactive</option>
          </select>
        </div>
        <span style={{ color: "#888", fontSize: 13 }}>{total} event(s)</span>
      </div>

      {loading ? (
        <p style={{ textAlign: "center", color: "#888" }}>Loading...</p>
      ) : events.length === 0 ? (
        <p style={{ textAlign: "center", color: "#888" }}>No events found</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#f5f5f5", textAlign: "left" }}>
              <th style={thStyle}>Event Name</th>
              <th style={thStyle}>Status</th>
              <th style={thStyle}>Version</th>
              <th style={thStyle}>Files</th>
              <th style={thStyle}>Created By</th>
              <th style={thStyle}>Created</th>
              <th style={thStyle}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {events.map((ev) => (
              <tr key={ev.id} style={{ borderBottom: "1px solid #eee" }}>
                <td style={tdStyle}>
                  <div>{ev.event_name || "—"}</div>
                  {ev.sub_event_name && (
                    <div style={{ fontSize: 11, color: "#888" }}>{ev.sub_event_name}</div>
                  )}
                </td>
                <td style={tdStyle}>{statusBadge(ev.status)}</td>
                <td style={tdStyle}>{ev.version_display || "—"}</td>
                <td style={tdStyle}>
                  {ev.files.length > 0 ? (
                    <span title={ev.files.map((f) => f.original_filename).join(", ")} style={{ cursor: "default" }}>
                      {ev.files.length} file{ev.files.length > 1 ? "s" : ""}
                    </span>
                  ) : (
                    <span style={{ color: "#aaa" }}>—</span>
                  )}
                </td>
                <td style={tdStyle}>{ev.created_by_name}</td>
                <td style={tdStyle}>{new Date(ev.created_at).toLocaleDateString()}</td>
                <td style={tdStyle}>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button onClick={() => onEdit(ev)} style={actionBtn}>Edit</button>
                    <button onClick={() => setRevisionEventId(ev.id)} style={actionBtn}>History</button>
                    {(ev.status === "ACTIVE" || ev.status === "INACTIVE") ? (
                      <button
                        onClick={() => handleToggle(ev)}
                        style={{
                          ...actionBtn,
                          color: ev.status === "INACTIVE" ? "#2e7d32" : "#d32f2f",
                        }}
                      >
                        {ev.status === "INACTIVE" ? "Activate" : "Deactivate"}
                      </button>
                    ) : (
                      <button onClick={() => handleDelete(ev.id)} style={{ ...actionBtn, color: "#d32f2f" }}>
                        Deactivate
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 16 }}>
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} style={actionBtn}>Prev</button>
          <span style={{ padding: "6px 10px", fontSize: 13 }}>Page {page} of {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} style={actionBtn}>Next</button>
        </div>
      )}

      {revisionEventId !== null && (
        <RevisionBrowser eventId={revisionEventId} onClose={() => setRevisionEventId(null)} />
      )}
    </div>
  );
}

const thStyle: React.CSSProperties = { padding: "10px 12px", fontSize: 13, fontWeight: 600 };
const tdStyle: React.CSSProperties = { padding: "10px 12px", fontSize: 13 };
const actionBtn: React.CSSProperties = {
  padding: "4px 10px",
  background: "none",
  border: "1px solid #ccc",
  borderRadius: 4,
  cursor: "pointer",
  fontSize: 12,
};
