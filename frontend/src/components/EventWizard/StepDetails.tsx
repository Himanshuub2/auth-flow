import TagInput from "../common/TagInput";
import type { WizardFormState } from "../../types";

interface Props {
  form: WizardFormState;
  onChange: (patch: Partial<WizardFormState>) => void;
}

export default function StepDetails({ form, onChange }: Props) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div>
          <label style={{ fontWeight: 600, fontSize: 14 }}>Event Name *</label>
          <input
            value={form.event_name}
            onChange={(e) => onChange({ event_name: e.target.value })}
            style={inputStyle}
          />
        </div>
        <div>
          <label style={{ fontWeight: 600, fontSize: 14 }}>Sub-Event Name</label>
          <input
            value={form.sub_event_name}
            onChange={(e) => onChange({ sub_event_name: e.target.value })}
            style={inputStyle}
          />
        </div>
      </div>

      <div>
        <label style={{ fontWeight: 600, fontSize: 14 }}>Event Dates</label>
        <input
          type="date"
          onChange={(e) => {
            if (e.target.value && !form.event_dates.includes(e.target.value)) {
              onChange({ event_dates: [...form.event_dates, e.target.value] });
            }
          }}
          style={inputStyle}
        />
        {form.event_dates.length > 0 && (
          <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
            {form.event_dates.map((d) => (
              <span
                key={d}
                style={{
                  background: "#e3edf9",
                  color: "#1a73e8",
                  padding: "3px 8px",
                  borderRadius: 12,
                  fontSize: 12,
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                }}
              >
                {d}
                <button
                  type="button"
                  onClick={() => onChange({ event_dates: form.event_dates.filter((x) => x !== d) })}
                  style={{ background: "none", border: "none", cursor: "pointer", color: "#1a73e8", fontWeight: 700, padding: 0 }}
                >
                  &times;
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      <div>
        <label style={{ fontWeight: 600, fontSize: 14 }}>Event Description</label>
        <textarea
          value={form.description}
          onChange={(e) => onChange({ description: e.target.value })}
          rows={5}
          style={{ ...inputStyle, resize: "vertical" }}
        />
      </div>

      <div>
        <label style={{ fontWeight: 600, fontSize: 14 }}>Tags</label>
        <TagInput tags={form.tags} onChange={(tags) => onChange({ tags })} />
      </div>
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
  marginTop: 4,
};
