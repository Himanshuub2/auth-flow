import { useEffect, useState } from "react";
import StepIndicator from "../common/StepIndicator";
import StepDetails from "./StepDetails";
import StepFiles from "./StepFiles";
import StepApplicability from "./StepApplicability";
import { createEvent, updateEvent, getEvent } from "../../api";
import type { WizardFormState, EventData, SaveEventPayload, FileMetadataState } from "../../types";

const STEPS = [
  { label: "Details" },
  { label: "Event Files" },
  { label: "Applicability" },
];

const defaultFileMeta = (): FileMetadataState => ({
  caption: "",
  description: "",
  thumbnailFile: null,
});

const emptyForm: WizardFormState = {
  event_name: "",
  sub_event_name: "",
  event_dates: [],
  description: "",
  tags: [],
  applicability_type: "ALL",
  applicability_refs: {},
  files: [],
  fileMetadata: {},
  existingMedia: [],
  change_remarks: "",
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
        fileMetadata: {},
        existingMedia: (editEvent.files ?? []) as import("../../types").MediaItem[],
        change_remarks: "",
      };
    }
    return { ...emptyForm };
  });

  useEffect(() => {
    if (editEvent) {
      // Refetch full detail (including files) so existing files are never missing when appending new ones
      getEvent(editEvent.id)
        .then((res) => {
          const data = (res.data as { data?: EventData })?.data;
          if (data) setEditEvent(data);
        })
        .catch(() => {});
    }
  }, [editEvent?.id]);

  useEffect(() => {
    if (editEvent) {
      setForm((prev) => ({
        ...prev,
        event_name: editEvent.event_name,
        sub_event_name: editEvent.sub_event_name || "",
        event_dates: Array.isArray(editEvent.event_dates) ? editEvent.event_dates : [],
        description: editEvent.description || "",
        tags: Array.isArray(editEvent.tags) ? editEvent.tags : [],
        applicability_type: editEvent.applicability_type,
        applicability_refs: editEvent.applicability_refs || {},
        files: [],
        fileMetadata: {},
        existingMedia: (editEvent.files ?? []) as import("../../types").MediaItem[],
      }));
    }
  }, [editEvent]);

  const patch = (p: Partial<WizardFormState>) => {
    if (p.files !== undefined) {
      const prevNames = new Set(form.files.map((f) => f.name));
      const nextNames = new Set(p.files.map((f) => f.name));
      const newNames = [...nextNames].filter((n) => !prevNames.has(n));
      const removed = [...prevNames].filter((n) => !nextNames.has(n));
      const fileMetadata = { ...form.fileMetadata };
      newNames.forEach((n) => {
        if (!fileMetadata[n]) fileMetadata[n] = defaultFileMeta();
      });
      removed.forEach((n) => delete fileMetadata[n]);
      setForm((prev) => ({ ...prev, ...p, fileMetadata }));
      return;
    }
    setForm((prev) => ({ ...prev, ...p }));
  };

  const handleSave = async (publish: boolean) => {
    if (!form.event_name.trim()) {
      setError("Event name is required");
      return;
    }
    if (editEvent && publish && !form.change_remarks.trim()) {
      setError("Change remarks are required when activating an edit");
      return;
    }
    setSaving(true);
    setError(null);

    try {
      const file_metadata = form.files.map((f) => {
        const meta = form.fileMetadata[f.name] ?? defaultFileMeta();
        return {
          original_filename: f.name,
          caption: meta.caption.trim() || null,
          description: meta.description.trim() || null,
          thumbnail_original_filename: meta.thumbnailFile?.name ?? null,
        };
      });
      const existingNames = form.existingMedia.map((m) => m.original_filename);
      const payload: SaveEventPayload = {
        event_name: form.event_name,
        sub_event_name: form.sub_event_name || null,
        event_dates: form.event_dates.length ? form.event_dates : null,
        description: form.description || null,
        tags: form.tags.length ? form.tags : null,
        applicability_type: form.applicability_type,
        applicability_refs: form.applicability_type === "ALL" ? null : form.applicability_refs,
        status: publish ? "ACTIVE" : "DRAFT",
        selected_filenames: [...existingNames, ...form.files.map((f) => f.name)],
        file_metadata: file_metadata.length ? file_metadata : undefined,
        change_remarks: form.change_remarks.trim() || null,
      };

      const mainFiles = form.files.length ? form.files : undefined;
      const thumbnailFiles = form.files.flatMap((f) => {
        const meta = form.fileMetadata[f.name];
        return meta?.thumbnailFile ? [meta.thumbnailFile] : [];
      });
      const allFiles = mainFiles
        ? thumbnailFiles.length
          ? [...mainFiles, ...thumbnailFiles]
          : mainFiles
        : undefined;

      if (editEvent) {
        const res = await updateEvent(editEvent.id, payload, allFiles);
        const body = res.data as any;
        const saved: EventData | undefined = body?.data;
        if (saved) {
          setEditEvent(saved);
        }
      } else {
        const res = await createEvent(payload, allFiles);
        const body = res.data as any;
        setEditEvent(body?.data ?? body);
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

        {editEvent && (
          <div style={{ marginTop: 16 }}>
            <label style={{ fontWeight: 600, fontSize: 14 }}>Change remarks (required when activating) *</label>
            <textarea
              value={form.change_remarks}
              onChange={(e) => patch({ change_remarks: e.target.value })}
              placeholder="Describe what changed in this edit"
              rows={2}
              style={{ width: "100%", padding: 8, marginTop: 4, borderRadius: 4, border: "1px solid #ccc" }}
            />
          </div>
        )}

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
              {saving ? "Activating..." : "Activate Now"}
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
