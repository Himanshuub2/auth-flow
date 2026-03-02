interface Option {
  id: number;
  name: string;
}

interface MultiSelectProps {
  label: string;
  options: Option[];
  selected: number[];
  onChange: (selected: number[]) => void;
}

export default function MultiSelect({ label, options, selected, onChange }: MultiSelectProps) {
  const toggleOption = (id: number) => {
    onChange(selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id]);
  };

  return (
    <div style={{ marginBottom: 12 }}>
      <label style={{ fontWeight: 600, fontSize: 14, marginBottom: 4, display: "block" }}>{label}</label>
      <div
        style={{
          border: "1px solid #ccc",
          borderRadius: 4,
          padding: 8,
          maxHeight: 140,
          overflowY: "auto",
        }}
      >
        {options.map((opt) => (
          <label
            key={opt.id}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "3px 0", cursor: "pointer" }}
          >
            <input
              type="checkbox"
              checked={selected.includes(opt.id)}
              onChange={() => toggleOption(opt.id)}
            />
            {opt.name}
          </label>
        ))}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
        {selected.map((id) => {
          const opt = options.find((o) => o.id === id);
          return opt ? (
            <span
              key={id}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                background: "#e3edf9",
                color: "#1a73e8",
                padding: "4px 10px",
                borderRadius: 14,
                fontSize: 13,
              }}
            >
              {opt.name}
              <button
                type="button"
                onClick={() => onChange(selected.filter((s) => s !== id))}
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "#1a73e8",
                  fontWeight: 700,
                  fontSize: 14,
                  padding: 0,
                  lineHeight: 1,
                }}
              >
                &times;
              </button>
            </span>
          ) : null;
        })}
      </div>
    </div>
  );
}
