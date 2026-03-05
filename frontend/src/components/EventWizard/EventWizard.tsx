import { useEffect, useState } from "react";
import StepIndicator from "../common/StepIndicator";
import StepDetails from "./StepDetails";
import StepFiles from "./StepFiles";
import StepApplicability from "./StepApplicability";
import { createEvent, updateEvent, getMedia } from "../../api";
import type { WizardFormState, EventData, SaveEventPayload } from "../../types";

const STEPS = [
  { label: "Details" },
  { label: "Event Files" },
  { label: "Applicability" },
];

const emptyForm: WizardFormState = {
  event_name: "",
  sub_event_name: "",
  event_dates: [],
  description: "",
  tags: [],
  applicability_type: "ALL",
  applicability_refs: {},
  files: [],
  existingMedia: [],
  fileMetadata: {},
};

interface Props {
  editEvent?: EventData | null;
  onClose: () => void;
  onSaved: () => void;
  setEditEvent: (event: EventData | null) => void;
}

export default function EventWizard({ editEvent, onClose, onSaved, setEditEvent }: Props) {
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<WizardFormState>(() => {
    if (editEvent) {
      return {
        event_name: editEvent.event_name,
        sub_event_name: editEvent.sub_event_name || "",
        event_dates: Array.isArray(editEvent.event_dates) ? editEvent.event_dates : [],
        description: editEvent.description || "",
        tags: Array.isArray(editEvent.tags) ? editEvent.tags : [],
        applicability_type: editEvent.applicability_type,
        applicability_refs: editEvent.applicability_refs || {},
        files: [],
        existingMedia: [],
        fileMetadata: {},
      };
    }
    return { ...emptyForm };
  });

  useEffect(() => {
    if (editEvent) {
      getMedia(editEvent.id).then((r) => {
        setForm((prev) => ({ ...prev, existingMedia: r.data }));
      });
    }
  }, [editEvent]);

  const patch = (p: Partial<WizardFormState>) => setForm((prev) => ({ ...prev, ...p }));

  const handleSave = async (publish: boolean) => {
    if (!form.event_name.trim()) {
      setError("Event name is required");
      return;
    }
    setSaving(true);
    setError(null);

    try {
      const file_metadata = [
        ...form.existingMedia.map((m) => ({
          original_filename: m.original_filename,
          caption: m.caption ?? null,
          description: m.description ?? null,
          thumbnail_url: m.thumbnail_url ?? null,
        })),
        ...form.files.map((f) => ({
          original_filename: f.name,
          caption: form.fileMetadata[f.name]?.caption || null,
          description: form.fileMetadata[f.name]?.description || null,
          thumbnail_url: form.fileMetadata[f.name]?.thumbnail_url || null,
        })),
      ];

      const payload: SaveEventPayload = {
        event_name: form.event_name,
        sub_event_name: form.sub_event_name || null,
        event_dates: form.event_dates.length ? form.event_dates : null,
        description: form.description || null,
        tags: form.tags.length ? form.tags : null,
        applicability_type: form.applicability_type,
        applicability_refs: form.applicability_type === "ALL" ? null : form.applicability_refs,
        status: publish ? "PUBLISHED" : "DRAFT",
        selected_filenames: form.existingMedia.map((m) => m.original_filename),
        file_metadata,
      };

      const files = form.files.length ? form.files : undefined;

      if (editEvent) {
        await updateEvent(editEvent.id, payload, files);
      } else {
        const res = await createEvent(payload, files);
        setEditEvent(res.data);
      }

      if(publish) onSaved();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Save failed";
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

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
      <div
        style={{
          background: "#fff",
          borderRadius: 8,
          width: "90%",
          maxWidth: 800,
          maxHeight: "90vh",
          overflow: "auto",
          padding: 24,
          position: "relative",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2 style={{ margin: 0 }}>{editEvent ? "Edit Event" : "Add Event"}</h2>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", fontSize: 24, cursor: "pointer" }}
          >
            &times;
          </button>
        </div>

        <StepIndicator steps={STEPS} currentStep={step} />

        {error && (
          <div style={{ background: "#fdecea", color: "#b71c1c", padding: "8px 12px", borderRadius: 4, marginBottom: 12 }}>
            {error}
          </div>
        )}

        <div style={{ minHeight: 250 }}>
          {step === 0 && <StepDetails form={form} onChange={patch} />}
          {step === 1 && <StepFiles form={form} onChange={patch} />}
          {step === 2 && <StepApplicability form={form} onChange={patch} />}
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 20 }}>
          {step > 0 && (
            <button onClick={() => setStep(step - 1)} style={btnSecondary} disabled={saving}>
              Back
            </button>
          )}
          <button onClick={() => handleSave(false)} style={btnDraft} disabled={saving}>
            {saving ? "Saving..." : "Save as Draft"}
          </button>
          {step < STEPS.length - 1 ? (
            <button onClick={() => setStep(step + 1)} style={btnPrimary} disabled={saving}>
              Next
            </button>
          ) : (
            <button onClick={() => handleSave(true)} style={btnPublish} disabled={saving}>
              {saving ? "Publishing..." : "Publish Now"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

const btnBase: React.CSSProperties = {
  padding: "8px 20px",
  borderRadius: 4,
  border: "none",
  cursor: "pointer",
  fontWeight: 600,
  fontSize: 14,
};
const btnPrimary: React.CSSProperties = { ...btnBase, background: "#1a73e8", color: "#fff" };
const btnDraft: React.CSSProperties = { ...btnBase, background: "#1a73e8", color: "#fff" };
const btnPublish: React.CSSProperties = { ...btnBase, background: "#0d47a1", color: "#fff" };
const btnSecondary: React.CSSProperties = { ...btnBase, background: "#e0e0e0", color: "#333" };
