import { useEffect, useState } from "react";
import { listRevisions, getRevisionSnapshot } from "../../api";
import type { RevisionSummary, RevisionDetail, DocumentRevisionDetail } from "../../types";

const BACKEND_URL = "http://localhost:8000";

function isDocumentRevisionDetail(d: RevisionDetail): d is DocumentRevisionDetail {
  return "files" in d;
}

interface Props {
  eventId: number;
  /** When from Items table, pass "event" or "document" so we can render document revisions */
  itemType?: "event" | "document";
  onClose: () => void;
  /** When provided (e.g. from Items table), use generic items API for revisions */
  listRevisions?: () => Promise<{ data: { data?: RevisionSummary[] } }>;
  getRevisionSnapshot?: (mediaVersion: number, revisionNumber: number) => Promise<{ data: { data?: RevisionDetail } }>;
}

export default function RevisionBrowser({
  eventId,
  itemType = "event",
  onClose,
  listRevisions: listRevisionsProp,
  getRevisionSnapshot: getSnapshotProp,
}: Props) {
  const [revisions, setRevisions] = useState<RevisionSummary[]>([]);
  const [selected, setSelected] = useState<RevisionDetail | null>(null);
  const [loading, setLoading] = useState(false);

  const listFn = listRevisionsProp ?? (() => listRevisions(eventId));
  const getSnapshotFn = getSnapshotProp ?? ((mv: number, rn: number) => getRevisionSnapshot(eventId, mv, rn));

  useEffect(() => {
    listFn().then((r) => {
      const list = r.data?.data ?? [];
      setRevisions(list);
      if (list.length > 0) {
        const first = list[0];
        loadSnapshot(first.media_version, first.revision_number);
      }
    });
  }, [eventId, itemType]);

  const loadSnapshot = async (mediaVersion: number, revisionNumber: number) => {
    setLoading(true);
    const r = await getSnapshotFn(mediaVersion, revisionNumber);
    setSelected(r.data?.data ?? null);
    setLoading(false);
  };

  const handleSelect = (value: string) => {
    const [mv, rn] = value.split(".").map(Number);
    loadSnapshot(mv, rn);
  };

  const selectedKey = selected
    ? `${selected.revision.media_version}.${selected.revision.revision_number}`
    : "";

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div style={{ background: "#fff", borderRadius: 8, width: "90%", maxWidth: 800, maxHeight: "85vh", overflow: "auto", padding: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h2 style={{ margin: 0 }}>Revision History</h2>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 24, cursor: "pointer" }}>&times;</button>
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ fontWeight: 600, marginRight: 8 }}>Select Revision:</label>
          <select
            onChange={(e) => handleSelect(e.target.value)}
            value={selectedKey}
            style={{ padding: "6px 10px", borderRadius: 4, border: "1px solid #ccc" }}
          >
            {revisions.map((r) => (
              <option key={r.version_display} value={r.version_display}>
                v{r.version_display} — {new Date(r.created_at).toLocaleDateString()}
              </option>
            ))}
          </select>
        </div>

        {loading && <p>Loading...</p>}

        {selected && !loading && (
          <div>
            {isDocumentRevisionDetail(selected) ? (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
                  <div>
                    <strong>Name:</strong> {selected.revision.name}
                  </div>
                  <div>
                    <strong>Type:</strong> {selected.revision.document_type}
                  </div>
                  <div>
                    <strong>Version:</strong> {selected.revision.version_display}
                  </div>
                </div>
                {selected.revision.summary && (
                  <div style={{ marginBottom: 16 }}>
                    <strong>Summary:</strong>
                    <p style={{ margin: "4px 0", color: "#555" }}>{selected.revision.summary}</p>
                  </div>
                )}
                {selected.revision.tags && selected.revision.tags.length > 0 && (
                  <div style={{ marginBottom: 16 }}>
                    <strong>Tags:</strong>{" "}
                    {selected.revision.tags.map((t) => (
                      <span key={t} style={{ background: "#e3edf9", color: "#1a73e8", padding: "2px 8px", borderRadius: 12, fontSize: 12, marginRight: 4 }}>{t}</span>
                    ))}
                  </div>
                )}
                {selected.files.length > 0 && (
                  <div>
                    <strong>Files ({selected.files.length}):</strong>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
                      {selected.files.map((f) => (
                        <div key={f.id} style={{ width: 120, border: "1px solid #ddd", borderRadius: 4, overflow: "hidden" }}>
                          {f.file_type === "IMAGE" ? (
                            <img src={`${BACKEND_URL}${f.file_url}`} alt={f.original_filename} style={{ width: "100%", height: 80, objectFit: "cover" }} />
                          ) : (
                            <div style={{ height: 80, display: "flex", alignItems: "center", justifyContent: "center", background: "#f5f5f5", fontSize: 11 }}>
                              {f.original_filename}
                            </div>
                          )}
                          <div style={{ padding: 4, fontSize: 11, color: "#666", wordBreak: "break-all" }}>{f.original_filename}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
                  <div>
                    <strong>Event Name:</strong> {selected.revision.event_name}
                  </div>
                  <div>
                    <strong>Sub-Event:</strong> {selected.revision.sub_event_name || "—"}
                  </div>
                  <div>
                    <strong>Dates:</strong>{" "}
                    {Array.isArray(selected.revision.event_dates) ? selected.revision.event_dates.join(", ") : "—"}
                  </div>
                  <div>
                    <strong>Version:</strong> {selected.revision.version_display}
                  </div>
                </div>
                {selected.revision.change_remarks && (
                  <div style={{ marginBottom: 16 }}>
                    <strong>Change remarks:</strong>
                    <p style={{ margin: "4px 0", color: "#555" }}>{selected.revision.change_remarks}</p>
                  </div>
                )}
                {selected.revision.description && (
                  <div style={{ marginBottom: 16 }}>
                    <strong>Description:</strong>
                    <p style={{ margin: "4px 0", color: "#555" }}>{selected.revision.description}</p>
                  </div>
                )}
                {selected.revision.tags && selected.revision.tags.length > 0 && (
                  <div style={{ marginBottom: 16 }}>
                    <strong>Tags:</strong>{" "}
                    {selected.revision.tags.map((t) => (
                      <span key={t} style={{ background: "#e3edf9", color: "#1a73e8", padding: "2px 8px", borderRadius: 12, fontSize: 12, marginRight: 4 }}>{t}</span>
                    ))}
                  </div>
                )}
                {selected.media_items.length > 0 && (
                  <div>
                    <strong>Media ({selected.media_items.length} files):</strong>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
                      {selected.media_items.map((m) => (
                        <div key={m.id} style={{ width: 120, border: "1px solid #ddd", borderRadius: 4, overflow: "hidden" }}>
                          {m.file_type === "IMAGE" ? (
                            <img src={`${BACKEND_URL}${m.file_url}`} alt={m.original_filename} style={{ width: "100%", height: 80, objectFit: "cover" }} />
                          ) : (
                            <div style={{ height: 80, display: "flex", alignItems: "center", justifyContent: "center", background: "#f5f5f5", fontSize: 11 }}>
                              {m.original_filename}
                            </div>
                          )}
                          <div style={{ padding: 4, fontSize: 11, color: "#666", wordBreak: "break-all" }}>
                            {m.caption || m.original_filename}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
