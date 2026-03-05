import { useRef, type DragEvent, useState } from "react";
import type { MediaItem, FileMetadataState } from "../../types";

interface FileUploaderProps {
  files: File[];
  fileMetadata: Record<string, FileMetadataState>;
  existingMedia: MediaItem[];
  onFilesChange: (files: File[]) => void;
  onFileMetadataChange: (filename: string, meta: FileMetadataState) => void;
  onRemoveExisting: (id: number) => void;
}

const BACKEND_URL = "http://localhost:8000";

function isVideo(file: File): boolean {
  return file.type.startsWith("video/") || /\.(mp4|webm)$/i.test(file.name);
}

export default function FileUploader({
  files,
  fileMetadata,
  existingMedia,
  onFilesChange,
  onFileMetadataChange,
  onRemoveExisting,
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
    const f = files[idx];
    if (f) {
      const next = { ...fileMetadata };
      delete next[f.name];
    }
    onFilesChange(files.filter((_, i) => i !== idx));
  };

  const getMeta = (filename: string): FileMetadataState =>
    fileMetadata[filename] ?? { caption: "", description: "", thumbnailFile: null };

  const setMeta = (filename: string, patch: Partial<FileMetadataState>) => {
    onFileMetadataChange(filename, { ...getMeta(filename), ...patch });
  };

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

      {/* Existing media from previous versions */}
      {existingMedia.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <h4 style={{ margin: "0 0 8px" }}>Existing Files</h4>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {existingMedia.map((m) => (
              <div key={m.id} style={{ position: "relative", width: 200, height: 80, border: "1px solid #ddd", borderRadius: 4, overflow: "hidden" ,flexDirection: "column"}}>
                {m.file_type === "IMAGE" ? (
                  <img src={`${BACKEND_URL}${m.file_url}`} alt={m.original_filename} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                ) : (
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", fontSize: 11, color: "#666", padding: 4 }}>
                    {m.original_filename}
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => onRemoveExisting(m.id)}
                  style={{
                    position: "absolute", top: 2, right: 2,
                    background: "rgba(0,0,0,0.5)", color: "#fff",
                    border: "none", borderRadius: "50%", width: 20, height: 20,
                    cursor: "pointer", fontSize: 12, lineHeight: "20px", padding: 0,
                  }}
                >
                  &times;
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {files.length > 0 && (
        <div>
          <h4 style={{ margin: "0 0 8px" }}>New Files ({files.length})</h4>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {files.map((f, idx) => {
              const meta = getMeta(f.name);
              const showThumb = isVideo(f);
              return (
                <div key={idx} style={{ border: "1px solid #ddd", borderRadius: 4, padding: 8, width: 260 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <span style={{ fontSize: 11, wordBreak: "break-all" }}>{f.name}</span>
                    <button
                      type="button"
                      onClick={() => removeFile(idx)}
                      style={{
                        background: "rgba(0,0,0,0.5)", color: "#fff",
                        border: "none", borderRadius: "50%", width: 20, height: 20,
                        cursor: "pointer", fontSize: 12, lineHeight: "20px", padding: 0,
                      }}
                    >
                      &times;
                    </button>
                  </div>
                  <label style={{ display: "block", marginBottom: 4 }}>
                    Caption
                    <input
                      type="text"
                      value={meta.caption}
                      onChange={(e) => setMeta(f.name, { caption: e.target.value })}
                      placeholder="Caption"
                      style={{ display: "block", width: "100%", marginTop: 2, padding: 4 }}
                    />
                  </label>
                  <label style={{ display: "block", marginBottom: 4 }}>
                    Description
                    <input
                      type="text"
                      value={meta.description}
                      onChange={(e) => setMeta(f.name, { description: e.target.value })}
                      placeholder="Description"
                      style={{ display: "block", width: "100%", marginTop: 2, padding: 4 }}
                    />
                  </label>
                  {showThumb && (
                    <label style={{ display: "block", marginBottom: 4 }}>
                      Thumbnail (optional)
                      <input
                        type="file"
                        accept="image/*"
                        style={{ display: "block", marginTop: 2, fontSize: 11 }}
                        onChange={(e) => {
                          const thumb = e.target.files?.[0];
                          setMeta(f.name, { thumbnailFile: thumb ?? null });
                        }}
                      />
                      {meta.thumbnailFile && <span style={{ fontSize: 11, color: "#666" }}> {meta.thumbnailFile.name}</span>}
                    </label>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
