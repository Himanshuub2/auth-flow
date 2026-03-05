import FileUploader from "../common/FileUploader";
import type { WizardFormState } from "../../types";

interface Props {
  form: WizardFormState;
  onChange: (patch: Partial<WizardFormState>) => void;
}

export default function StepFiles({ form, onChange }: Props) {
  return (
    <div>
      <h3 style={{ marginTop: 0 }}>Upload Attachments</h3>
      <FileUploader
        files={form.files}
        existingMedia={form.existingMedia}
        fileMetadata={form.fileMetadata}
        onFilesChange={(files) => onChange({ files })}
        onRemoveExisting={(id) =>
          onChange({ existingMedia: form.existingMedia.filter((m) => m.id !== id) })
        }
        onUpdateExisting={(id, patch) =>
          onChange({
            existingMedia: form.existingMedia.map((m) =>
              m.id === id ? { ...m, ...patch } : m
            ),
          })
        }
        onFileMetadataChange={(filename, patch) =>
          onChange({
            fileMetadata: {
              ...form.fileMetadata,
              [filename]: {
                ...{ caption: "", description: "", thumbnail_url: "" },
                ...(form.fileMetadata[filename] ?? {}),
                ...patch,
              },
            },
          })
        }
      />
    </div>
  );
}
