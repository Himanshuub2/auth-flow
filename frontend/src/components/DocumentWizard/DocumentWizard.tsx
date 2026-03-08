import { useEffect, useState } from "react";
import {
  createDocument,
  updateDocument,
  getDocumentTypes,
  getLegislation,
  getSubLegislation,
  getLinkedOptions,
  getDivisions,
  getDesignations,
} from "../../api";
import TagInput from "../common/TagInput";
import type {
  DocumentData,
  SaveDocumentPayload,
  DocumentTypeOption,
  LegislationOption,
  SubLegislationOption,
  LinkedOption,
  LinkedDocumentDetail,
  ApplicabilityType,
} from "../../types";

interface Props {
  editDoc?: DocumentData | null;
  onClose: () => void;
  onSaved: () => void;
  setEditDoc?: (doc: DocumentData | null) => void;
}

interface FormState {
  name: string;
  document_type: string;
  tags: string[];
  summary: string;
  legislation_id: number | null;
  sub_legislation_id: number | null;
  version: number;
  next_review_date: string;
  download_allowed: boolean;
  linked_document_ids: number[];
  applicability_type: ApplicabilityType;
  applicability_refs: Record<string, number[]>;
  change_remarks: string;
}

const emptyForm: FormState = {
  name: "",
  document_type: "",
  tags: [],
  summary: "",
  legislation_id: null,
  sub_legislation_id: null,
  version: 1,
  next_review_date: "",
  download_allowed: true,
  linked_document_ids: [],
  applicability_type: "ALL",
  applicability_refs: {},
  change_remarks: "",
};

export default function DocumentWizard({ editDoc, onClose, onSaved, setEditDoc }: Props) {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<FormState>(() => {
    if (editDoc) {
      return {
        name: editDoc.name,
        document_type: editDoc.document_type,
        tags: editDoc.tags ?? [],
        summary: editDoc.summary ?? "",
        legislation_id: editDoc.legislation_id,
        sub_legislation_id: editDoc.sub_legislation_id,
        version: editDoc.version,
        next_review_date: editDoc.next_review_date ?? "",
        download_allowed: editDoc.download_allowed,
        linked_document_ids: editDoc.linked_document_ids ?? [],
        applicability_type: editDoc.applicability_type,
        applicability_refs: editDoc.applicability_refs ?? {},
        change_remarks: "",
      };
    }
    return { ...emptyForm };
  });
  const [files, setFiles] = useState<File[]>([]);
  /** Existing file IDs user chose to remove (so we don't send them in selected_filenames). */
  const [removedExistingIds, setRemovedExistingIds] = useState<number[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (editDoc) {
      setForm({
        name: editDoc.name,
        document_type: editDoc.document_type,
        tags: editDoc.tags ?? [],
        summary: editDoc.summary ?? "",
        legislation_id: editDoc.legislation_id,
        sub_legislation_id: editDoc.sub_legislation_id,
        version: editDoc.version,
        next_review_date: editDoc.next_review_date ?? "",
        download_allowed: editDoc.download_allowed,
        linked_document_ids: editDoc.linked_document_ids ?? [],
        applicability_type: editDoc.applicability_type,
        applicability_refs: editDoc.applicability_refs ?? {},
        change_remarks: "",
      });
      setFiles([]);
      setRemovedExistingIds([]);
      if (editDoc.linked_document_details?.length) {
        setLinkedItems(editDoc.linked_document_details.map((d) => ({ id: d.id, name: d.name, document_type: d.document_type })));
      }
    } else {
      setForm({ ...emptyForm });
      setFiles([]);
      setRemovedExistingIds([]);
      setLinkedItems([]);
    }
  }, [editDoc?.id]);

  const [docTypes, setDocTypes] = useState<DocumentTypeOption[]>([]);
  const [legislations, setLegislations] = useState<LegislationOption[]>([]);
  const [subLegislations, setSubLegislations] = useState<SubLegislationOption[]>([]);
  const [linkedOptions, setLinkedOptions] = useState<LinkedOption[]>([]);
  const [linkedTypeSelect, setLinkedTypeSelect] = useState<string>("");
  const [linkedItems, setLinkedItems] = useState<{ id: number; name: string; document_type: string }[]>(() => {
    if (editDoc?.linked_document_details?.length) {
      return editDoc.linked_document_details.map((d) => ({ id: d.id, name: d.name, document_type: d.document_type }));
    }
    if (editDoc?.linked_document_ids?.length) {
      return editDoc.linked_document_ids.map((id) => ({ id, name: `Document #${id}`, document_type: "" }));
    }
    return [];
  });
  const [selectedDocToAdd, setSelectedDocToAdd] = useState<number | "">("");
  const [divisions, setDivisions] = useState<{ id: number; name: string }[]>([]);
  const [designations, setDesignations] = useState<{ id: number; name: string }[]>([]);

  useEffect(() => {
    getDocumentTypes().then((r) => setDocTypes(r.data.data ?? []));
    getLegislation().then((r) => setLegislations(r.data.data ?? []));
    getDivisions().then((r) => setDivisions(r.data.data ?? []));
    getDesignations().then((r) => setDesignations(r.data.data ?? []));
  }, []);

  useEffect(() => {
    if (form.legislation_id) {
      getSubLegislation(form.legislation_id).then((r) => setSubLegislations(r.data.data ?? []));
    } else {
      setSubLegislations([]);
    }
  }, [form.legislation_id]);

  // Linked section: when type dropdown changes, fetch documents of that type
  useEffect(() => {
    const typeToFetch = linkedTypeSelect || form.document_type;
    if (typeToFetch && typeToFetch !== "FAQ") {
      getLinkedOptions(typeToFetch, editDoc?.id).then((r) => setLinkedOptions(r.data.data ?? []));
    } else {
      setLinkedOptions([]);
    }
  }, [linkedTypeSelect, form.document_type, editDoc?.id]);

  const set = <K extends keyof FormState>(key: K, val: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: val }));

  const isFAQ = form.document_type === "FAQ";
  const showLegislation = legislations.length > 1;

  const handleSave = async (status: string) => {
    if (!form.name.trim()) { setError("Name is required"); return; }
    if (!form.document_type) { setError("Document type is required"); return; }
    if (form.tags.length === 0) { setError("At least one tag is required"); return; }
    if (editDoc?.status === "PUBLISHED" && !form.change_remarks.trim() && status === "PUBLISHED") { setError("Change remarks required for editing"); return; }

    const keptExisting = (editDoc?.files ?? []).filter((f) => !removedExistingIds.includes(f.id));
    const existingFilenames = keptExisting.map((f) => f.original_filename);
    const newFilenames = files.map((f) => f.name);
    const allFilenames = [...new Set([...existingFilenames, ...newFilenames])];

    if (status === "PUBLISHED" && allFilenames.length === 0 && files.length === 0) {
      setError("At least 1 file required to publish");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const payload: SaveDocumentPayload = {
        name: form.name,
        document_type: form.document_type as any,
        tags: form.tags,
        summary: form.summary || null,
        legislation_id: form.legislation_id,
        sub_legislation_id: form.sub_legislation_id,
        version: form.version,
        next_review_date: form.next_review_date || null,
        download_allowed: form.download_allowed,
        linked_document_ids: isFAQ ? [] : form.linked_document_ids,
        applicability_type: form.applicability_type,
        applicability_refs: form.applicability_refs,
        status,
        selected_filenames: allFilenames,
        change_remarks: form.change_remarks || null,
      };

      if (editDoc) {
        const res = await updateDocument(editDoc.id, payload, files.length ? files : undefined);
        const body = res.data as any;
        const saved: DocumentData | undefined = body?.data;
        if (saved && saved.id !== editDoc.id && setEditDoc) {
          setEditDoc(saved);
        }
        if (status === "PUBLISHED") onSaved();
      } else {
        const res = await createDocument(payload, files.length ? files : undefined);
        const body = res.data as any;
        const saved: DocumentData | undefined = body?.data;
        if (saved && setEditDoc) {
          setEditDoc(saved);
        }
        if (status === "PUBLISHED") onSaved();
      }
    } catch (err: any) {
      setError(err?.response?.data?.message || err?.message || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const addLinked = () => {
    if (selectedDocToAdd === "" || linkedItems.length >= 6) return;
    const opt = linkedOptions.find((o) => o.id === selectedDocToAdd);
    if (!opt || linkedItems.some((i) => i.id === opt.id)) return;
    const typeLabel = docTypes.find((t) => t.value === (linkedTypeSelect || form.document_type))?.label ?? (linkedTypeSelect || form.document_type);
    const next = [...linkedItems, { id: opt.id, name: opt.name, document_type: typeLabel }];
    setLinkedItems(next);
    setForm((prev) => ({ ...prev, linked_document_ids: next.map((i) => i.id) }));
    setSelectedDocToAdd("");
  };

  const removeLinked = (id: number) => {
    const next = linkedItems.filter((i) => i.id !== id);
    setLinkedItems(next);
    setForm((prev) => ({ ...prev, linked_document_ids: next.map((i) => i.id) }));
  };

  const toggleApplicabilityRef = (key: string, id: number) => {
    setForm((prev) => {
      const current = prev.applicability_refs[key] ?? [];
      const next = current.includes(id)
        ? current.filter((x) => x !== id)
        : [...current, id];
      return { ...prev, applicability_refs: { ...prev.applicability_refs, [key]: next } };
    });
  };

  return (
    <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(0,0,0,0.4)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
      <div style={{ background: "#fff", borderRadius: 8, padding: 24, width: 700, maxHeight: "90vh", overflow: "auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <h2 style={{ margin: 0 }}>{editDoc ? "Edit Document" : "Add Document"}</h2>
          <button onClick={onClose}>&times;</button>
        </div>

        {/* Step tabs */}
        <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
          {["Details", isFAQ ? null : "Linked Items", "Applicability"].filter(Boolean).map((label, i) => (
            <button key={i} onClick={() => setStep(i)} style={{ fontWeight: step === i ? 700 : 400 }}>
              {i + 1}. {label}
            </button>
          ))}
        </div>

        {error && <p style={{ color: "red" }}>{error}</p>}

        {/* Step 0: Details */}
        {step === 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <label>Document Type *
              <select value={form.document_type} onChange={(e) => set("document_type", e.target.value)}>
                <option value="">Select</option>
                {docTypes.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </label>

            {showLegislation && (
              <>
                <label>Legislation
                  <select value={form.legislation_id ?? ""} onChange={(e) => set("legislation_id", e.target.value ? Number(e.target.value) : null)}>
                    <option value="">Select</option>
                    {legislations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                  </select>
                </label>
                {form.legislation_id && (
                  <label>Sub-Legislation
                    <select value={form.sub_legislation_id ?? ""} onChange={(e) => set("sub_legislation_id", e.target.value ? Number(e.target.value) : null)}>
                      <option value="">Select</option>
                      {subLegislations.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                  </label>
                )}
              </>
            )}

            <label>Name *
              <input value={form.name} onChange={(e) => set("name", e.target.value)} />
            </label>

            <label>Version
              <input type="number" value={form.version} onChange={(e) => set("version", Number(e.target.value))} min={1} />
            </label>

            <label>Next Review Date
              <input type="date" value={form.next_review_date} onChange={(e) => set("next_review_date", e.target.value)} />
            </label>

            <label>Summary
              <textarea value={form.summary} onChange={(e) => set("summary", e.target.value)} rows={3} />
            </label>

            <label>Tags *</label>
            <TagInput tags={form.tags} onChange={(tags) => set("tags", tags)} />

            <label>
              <input type="checkbox" checked={form.download_allowed} onChange={(e) => set("download_allowed", e.target.checked)} />
              Download Allowed
            </label>

            <label>Upload Attachments (1–6 files total, max 30MB each). Existing files are kept until you remove them; new uploads append.</label>
            {editDoc && editDoc.files?.length > 0 && (
              <div style={{ marginBottom: 8 }}>
                <strong>Existing files (remove to drop from document):</strong>
                <ul style={{ margin: "4px 0", paddingLeft: 20 }}>
                  {editDoc.files.map((f) => (
                    <li key={f.id} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      {f.original_filename}
                      {!removedExistingIds.includes(f.id) ? (
                        <button type="button" onClick={() => setRemovedExistingIds((prev) => [...prev, f.id])} style={{ fontSize: 12 }}>Remove</button>
                      ) : (
                        <button type="button" onClick={() => setRemovedExistingIds((prev) => prev.filter((id) => id !== f.id))} style={{ fontSize: 12 }}>Undo</button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <input
              type="file"
              multiple
              onChange={(e) => {
                const selected = Array.from(e.target.files ?? []);
                const keptCount = (editDoc?.files?.length ?? 0) - removedExistingIds.length;
                if (keptCount + files.length + selected.length > 6) {
                  setError("Max 6 files total");
                  return;
                }
                setFiles((prev) => [...prev, ...selected]);
                setError(null);
              }}
            />
            {files.length > 0 && <p>{files.length} new file(s) to add</p>}

            {editDoc && (
              <label>Change Remarks *
                <textarea value={form.change_remarks} onChange={(e) => set("change_remarks", e.target.value)} rows={2} />
              </label>
            )}
          </div>
        )}

        {/* Step 1: Linked Items (skip for FAQ) – pick type, then document, add (up to 6, any mix of types) */}
        {step === 1 && !isFAQ && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <p>Add up to 6 linked documents; they can be of different types.</p>
            <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
              <label>
                Document type
                <select
                  value={linkedTypeSelect || form.document_type}
                  onChange={(e) => setLinkedTypeSelect(e.target.value)}
                >
                  <option value="">Select type</option>
                  {docTypes.filter((t) => t.value !== "FAQ").map((t) => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </label>
              <label>
                Document
                <select
                  value={selectedDocToAdd}
                  onChange={(e) => setSelectedDocToAdd(e.target.value === "" ? "" : Number(e.target.value))}
                >
                  <option value="">Select document</option>
                  {linkedOptions
                    .filter((opt) => !linkedItems.some((i) => i.id === opt.id))
                    .map((opt) => (
                      <option key={opt.id} value={opt.id}>{opt.name}</option>
                    ))}
                </select>
              </label>
              <button type="button" onClick={addLinked} disabled={linkedItems.length >= 6 || selectedDocToAdd === ""}>
                Add
              </button>
            </div>
            {linkedOptions.length === 0 && (linkedTypeSelect || form.document_type) && (
              <p>No documents of this type available to link.</p>
            )}
            <p>Linked: {linkedItems.length}/6</p>
            {linkedItems.length > 0 && (
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {linkedItems.map((item) => (
                  <li key={item.id} style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <span>{item.name} ({item.document_type})</span>
                    <button type="button" onClick={() => removeLinked(item.id)}>Remove</button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Step 2 (or 1 for FAQ): Applicability */}
        {step === (isFAQ ? 1 : 2) && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <label>Applicability</label>
            <div style={{ display: "flex", gap: 12 }}>
              {(["ALL", "DIVISION", "EMPLOYEE"] as ApplicabilityType[]).map((t) => (
                <label key={t}>
                  <input type="radio" name="applicability" value={t} checked={form.applicability_type === t} onChange={() => set("applicability_type", t)} />
                  {t === "ALL" ? "All Division Clusters" : t === "DIVISION" ? "By Division Cluster/s" : "By Employee/s"}
                </label>
              ))}
            </div>

            {form.applicability_type === "DIVISION" && (
              <div>
                <label>Division Cluster</label>
                {divisions.map((d) => (
                  <label key={d.id} style={{ display: "block" }}>
                    <input type="checkbox" checked={(form.applicability_refs.division_ids ?? []).includes(d.id)} onChange={() => toggleApplicabilityRef("division_ids", d.id)} />
                    {d.name}
                  </label>
                ))}
              </div>
            )}

            {(form.applicability_type === "DIVISION" || form.applicability_type === "EMPLOYEE") && (
              <div>
                <label>Designation</label>
                {designations.map((d) => (
                  <label key={d.id} style={{ display: "block" }}>
                    <input type="checkbox" checked={(form.applicability_refs.designation_ids ?? []).includes(d.id)} onChange={() => toggleApplicabilityRef("designation_ids", d.id)} />
                    {d.name}
                  </label>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Footer */}
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 20 }}>
          <div style={{ display: "flex", gap: 8 }}>
            {step > 0 && <button onClick={() => setStep(step - 1)}>Back</button>}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button disabled={saving} onClick={() => handleSave("DRAFT")}>Save as Draft</button>
            {step < (isFAQ ? 1 : 2) ? (
              <button onClick={() => setStep(step + 1)}>Next</button>
            ) : (
              <button disabled={saving} onClick={() => handleSave("PUBLISHED")}>Publish Now</button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
