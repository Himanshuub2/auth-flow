import { useEffect, useState } from "react";
import MultiSelect from "../common/MultiSelect";
import { getDivisions, getDesignations } from "../../api";
import type { WizardFormState, Division, Designation, ApplicabilityType } from "../../types";

interface Props {
  form: WizardFormState;
  onChange: (patch: Partial<WizardFormState>) => void;
}

export default function StepApplicability({ form, onChange }: Props) {
  const [divisions, setDivisions] = useState<Division[]>([]);
  const [designations, setDesignations] = useState<Designation[]>([]);

  useEffect(() => {
    getDivisions().then((r) => setDivisions(r.data.data ?? []));
    getDesignations().then((r) => setDesignations(r.data.data ?? []));
  }, []);

  const setType = (type: ApplicabilityType) => {
    onChange({
      applicability_type: type,
      applicability_refs: type === "ALL" ? {} : form.applicability_refs,
    });
  };

  return (
    <div>
      <h3 style={{ marginTop: 0 }}>Applicability</h3>

      <div style={{ display: "flex", gap: 24, marginBottom: 16 }}>
        {(["ALL", "DIVISION", "EMPLOYEE"] as const).map((type) => (
          <label key={type} style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
            <input
              type="radio"
              name="applicabilityType"
              checked={form.applicability_type === type}
              onChange={() => setType(type)}
            />
            {type === "ALL" ? "Applicable to All" : type === "DIVISION" ? "By Division Cluster/s" : "By Employee/s"}
          </label>
        ))}
      </div>

      {form.applicability_type === "DIVISION" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <MultiSelect
            label="Division Cluster"
            options={divisions}
            selected={form.applicability_refs.divisions || []}
            onChange={(ids) =>
              onChange({
                applicability_refs: { ...form.applicability_refs, divisions: ids },
              })
            }
          />
          <MultiSelect
            label="Designation"
            options={designations}
            selected={form.applicability_refs.designations || []}
            onChange={(ids) =>
              onChange({
                applicability_refs: { ...form.applicability_refs, designations: ids },
              })
            }
          />
        </div>
      )}

      {form.applicability_type === "EMPLOYEE" && (
        <div>
          <label style={{ fontWeight: 600, fontSize: 14 }}>Employee IDs (comma-separated)</label>
          <input
            value={(form.applicability_refs.employees || []).join(", ")}
            onChange={(e) =>
              onChange({
                applicability_refs: {
                  ...form.applicability_refs,
                  employees: e.target.value
                    .split(",")
                    .map((s) => parseInt(s.trim(), 10))
                    .filter((n) => !isNaN(n)),
                },
              })
            }
            style={{
              width: "100%",
              padding: "8px 10px",
              border: "1px solid #ccc",
              borderRadius: 4,
              marginTop: 4,
              boxSizing: "border-box",
            }}
            placeholder="e.g. 1, 2, 3"
          />
        </div>
      )}
    </div>
  );
}
