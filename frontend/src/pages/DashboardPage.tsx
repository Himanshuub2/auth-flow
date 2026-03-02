import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import EventTable from "../components/EventTable/EventTable";
import EventWizard from "../components/EventWizard/EventWizard";
import type { EventData } from "../types";

export default function DashboardPage() {
  const [showWizard, setShowWizard] = useState(false);
  const [editEvent, setEditEvent] = useState<EventData | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const navigate = useNavigate();

  const user = useMemo(() => JSON.parse(localStorage.getItem("user") || "null"), []);

  useEffect(() => {
    if (!user) navigate("/login", { replace: true });
  }, [user, navigate]);

  if (!user) return null;

  const openCreate = () => {
    setEditEvent(null);
    setShowWizard(true);
  };

  const openEdit = (ev: EventData) => {
    setEditEvent(ev);
    setShowWizard(true);
  };

  const handleSaved = () => {
    setShowWizard(false);
    // setEditEvent(null);
    setRefreshKey((k) => k + 1);
  };

  const logout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    navigate("/login");
  };

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "20px 24px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 22 }}>Event Management</h1>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 13, color: "#666" }}>{user.full_name}</span>
          <button onClick={openCreate} style={primaryBtn}>+ New Event</button>
          <button onClick={logout} style={logoutBtn}>Logout</button>
        </div>
      </div>

      <EventTable onEdit={openEdit} refreshKey={refreshKey} />

      {showWizard && (
        <EventWizard
          editEvent={editEvent}
          onClose={() => { setShowWizard(false); setEditEvent(null); }}
          onSaved={handleSaved}
          setEditEvent={setEditEvent}
        />
      )}
    </div>
  );
}

const primaryBtn: React.CSSProperties = {
  padding: "8px 18px",
  background: "#1a73e8",
  color: "#fff",
  border: "none",
  borderRadius: 4,
  cursor: "pointer",
  fontWeight: 600,
  fontSize: 13,
};

const logoutBtn: React.CSSProperties = {
  padding: "8px 14px",
  background: "none",
  color: "#666",
  border: "1px solid #ccc",
  borderRadius: 4,
  cursor: "pointer",
  fontSize: 13,
};
