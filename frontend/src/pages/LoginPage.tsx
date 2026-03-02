import { useState, type FormEvent } from "react";
import { login } from "../api";
import { useNavigate } from "react-router-dom";

export default function LoginPage() {
  const [email, setEmail] = useState("admin@eventflow.local");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const res = await login(email, password);
      localStorage.setItem("token", res.data.access_token);
      localStorage.setItem("user", JSON.stringify(res.data.user));
      navigate("/");
    } catch {
      setError("Invalid credentials");
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#f0f2f5" }}>
      <form
        onSubmit={handleSubmit}
        style={{
          background: "#fff",
          padding: 32,
          borderRadius: 8,
          boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
          width: 360,
        }}
      >
        <h2 style={{ marginTop: 0, textAlign: "center" }}>Event Flow Login</h2>
        {error && <div style={{ background: "#fdecea", color: "#b71c1c", padding: 8, borderRadius: 4, marginBottom: 12, fontSize: 13 }}>{error}</div>}
        <div style={{ marginBottom: 14 }}>
          <label style={{ display: "block", fontWeight: 600, fontSize: 13, marginBottom: 4 }}>Email</label>
          <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required style={inputStyle} />
        </div>
        <div style={{ marginBottom: 20 }}>
          <label style={{ display: "block", fontWeight: 600, fontSize: 13, marginBottom: 4 }}>Password</label>
          <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" required style={inputStyle} />
        </div>
        <button type="submit" style={{ width: "100%", padding: "10px", background: "#1a73e8", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer", fontWeight: 600, fontSize: 14 }}>
          Sign In
        </button>
      </form>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 10px",
  border: "1px solid #ccc",
  borderRadius: 4,
  fontSize: 14,
  boxSizing: "border-box",
};
