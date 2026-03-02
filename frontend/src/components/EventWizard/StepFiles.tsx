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
        onFilesChange={(files) => onChange({ files })}
        onRemoveExisting={(id) =>
          onChange({ existingMedia: form.existingMedia.filter((m) => m.id !== id) })
        }
      />
    </div>
  );
}
