import { useRef, type DragEvent, useState } from "react";
import type { MediaItem, FileMetadataEditable } from "../../types";

const BACKEND_URL = "http://localhost:8000";

interface FileUploaderProps {
  files: File[];
  existingMedia: MediaItem[];
  fileMetadata: Record<string, FileMetadataEditable>;
  onFilesChange: (files: File[]) => void;
  onRemoveExisting: (id: number) => void;
  onUpdateExisting: (id: number, patch: Partial<FileMetadataEditable>) => void;
  onFileMetadataChange: (filename: string, patch: Partial<FileMetadataEditable>) => void;
}

export default function FileUploader({
  files,
  existingMedia,
  fileMetadata,
  onFilesChange,
  onRemoveExisting,
  onUpdateExisting,
  onFileMetadataChange,
}: FileUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const addFiles = (newFiles: FileList | File[]) => {
    const arr = Array.from(newFiles);
    onFilesChange([...files, ...arr]);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  };

  const removeFile = (idx: number) => {
    onFilesChange(files.filter((_, i) => i !== idx));
  };

  const cardStyle: React.CSSProperties = {
    border: "1px solid #ddd",
    borderRadius: 8,
    overflow: "hidden",
    background: "#fff",
    maxWidth: 280,
  };
  const fieldStyle: React.CSSProperties = {
    width: "100%",
    padding: "6px 8px",
    marginTop: 4,
    border: "1px solid #ddd",
    borderRadius: 4,
    fontSize: 12,
    boxSizing: "border-box",
  };
  const labelStyle: React.CSSProperties = { fontSize: 11, color: "#666", marginTop: 8, display: "block" };

  return (
    <div>
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `2px dashed ${dragOver ? "#1a73e8" : "#ccc"}`,
          borderRadius: 8,
          padding: "32px 16px",
          textAlign: "center",
          cursor: "pointer",
          background: dragOver ? "#f0f6ff" : "#fafafa",
          marginBottom: 16,
        }}
      >
        <p style={{ margin: 0, color: "#666" }}>
          Drag & Drop your files here or <span style={{ color: "#1a73e8", fontWeight: 600 }}>browse</span>
        </p>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "#999" }}>
          Max 50 Photos (20MB each) &amp; 5 Videos (500MB, mp4)
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept="image/*,video/mp4"
          style={{ display: "none" }}
          onChange={(e) => e.target.files && addFiles(e.target.files)}
        />
      </div>

      {existingMedia.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <h4 style={{ margin: "0 0 8px" }}>Selected Files</h4>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
            {existingMedia.map((m) => (
              <div key={m.id} style={cardStyle}>
                <div style={{ position: "relative", height: 140, background: "#eee" }}>
                  {m.file_type === "IMAGE" ? (
                    <img
                      src={`${BACKEND_URL}${m.file_url}`}
                      alt={m.original_filename}
                      style={{ width: "100%", height: "100%", objectFit: "cover" }}
                    />
                  ) : (
                    <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
                      {m.thumbnail_url ? (
                        <img src={m.thumbnail_url.startsWith("http") ? m.thumbnail_url : `${BACKEND_URL}${m.thumbnail_url}`} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                      ) : (
                        <span style={{ fontSize: 12, color: "#666" }}>Video: {m.original_filename}</span>
                      )}
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={() => onRemoveExisting(m.id)}
                    style={{
                      position: "absolute", top: 4, right: 4,
                      background: "rgba(0,0,0,0.6)", color: "#fff",
                      border: "none", borderRadius: "50%", width: 24, height: 24,
                      cursor: "pointer", fontSize: 14, lineHeight: "22px", padding: 0,
                    }}
                  >
                    &times;
                  </button>
                </div>
                <div style={{ padding: 8 }}>
                  <label style={labelStyle}>Caption</label>
                  <input
                    type="text"
                    value={m.caption ?? ""}
                    onChange={(e) => onUpdateExisting(m.id, { caption: e.target.value })}
                    placeholder="Caption"
                    style={fieldStyle}
                  />
                  <label style={labelStyle}>Description</label>
                  <textarea
                    value={m.description ?? ""}
                    onChange={(e) => onUpdateExisting(m.id, { description: e.target.value })}
                    placeholder="Description"
                    rows={2}
                    style={{ ...fieldStyle, resize: "vertical" }}
                  />
                  {m.file_type === "VIDEO" && (
                    <>
                      <label style={labelStyle}>Thumbnail URL</label>
                      <input
                        type="text"
                        value={m.thumbnail_url ?? ""}
                        onChange={(e) => onUpdateExisting(m.id, { thumbnail_url: e.target.value })}
                        placeholder="https://..."
                        style={fieldStyle}
                      />
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {files.length > 0 && (
        <div>
          <h4 style={{ margin: "0 0 8px" }}>New Files ({files.length})</h4>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
            {files.map((f, idx) => {
              const meta = fileMetadata[f.name] ?? { caption: "", description: "", thumbnail_url: "" };
              const isVideo = f.type.startsWith("video/");
              return (
                <div key={idx} style={{ ...cardStyle, position: "relative" }}>
                  <div style={{ position: "relative", height: 100, background: "#eee", display: "flex", alignItems: "center", justifyContent: "center", padding: 8 }}>
                    {f.type.startsWith("image/") ? (
                      <img src={URL.createObjectURL(f)} alt="" style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }} />
                    ) : (
                      <span style={{ fontSize: 12, color: "#666", wordBreak: "break-all" }}>{f.name}</span>
                    )}
                    <button
                      type="button"
                      onClick={() => removeFile(idx)}
                      style={{
                        position: "absolute", top: 4, right: 4,
                        background: "rgba(0,0,0,0.6)", color: "#fff",
                        border: "none", borderRadius: "50%", width: 24, height: 24,
                        cursor: "pointer", fontSize: 14, lineHeight: "22px", padding: 0,
                      }}
                    >
                      &times;
                    </button>
                  </div>
                  <div style={{ padding: 8 }}>
                    <label style={labelStyle}>Caption</label>
                    <input
                      type="text"
                      value={meta.caption}
                      onChange={(e) => onFileMetadataChange(f.name, { ...meta, caption: e.target.value })}
                      placeholder="Caption"
                      style={fieldStyle}
                    />
                    <label style={labelStyle}>Description</label>
                    <textarea
                      value={meta.description}
                      onChange={(e) => onFileMetadataChange(f.name, { ...meta, description: e.target.value })}
                      placeholder="Description"
                      rows={2}
                      style={{ ...fieldStyle, resize: "vertical" }}
                    />
                    {isVideo && (
                      <>
                        <label style={labelStyle}>Thumbnail URL</label>
                        <input
                          type="text"
                          value={meta.thumbnail_url}
                          onChange={(e) => onFileMetadataChange(f.name, { ...meta, thumbnail_url: e.target.value })}
                          placeholder="https://..."
                          style={fieldStyle}
                        />
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
