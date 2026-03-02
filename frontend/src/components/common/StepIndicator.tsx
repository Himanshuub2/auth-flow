interface Step {
  label: string;
  icon?: string;
}

interface StepIndicatorProps {
  steps: Step[];
  currentStep: number;
}

export default function StepIndicator({ steps, currentStep }: StepIndicatorProps) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", margin: "24px 0" }}>
      {steps.map((step, idx) => {
        const isActive = idx <= currentStep;
        const isCurrent = idx === currentStep;
        return (
          <div key={idx} style={{ display: "flex", alignItems: "center" }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
              <div
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: "50%",
                  background: isActive ? "#1a73e8" : "#e0e0e0",
                  color: isActive ? "#fff" : "#888",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontWeight: isCurrent ? 700 : 500,
                  fontSize: 14,
                }}
              >
                {idx + 1}
              </div>
              <span
                style={{
                  marginTop: 6,
                  fontSize: 12,
                  color: isActive ? "#1a73e8" : "#888",
                  fontWeight: isCurrent ? 600 : 400,
                }}
              >
                {step.label}
              </span>
            </div>
            {idx < steps.length - 1 && (
              <div
                style={{
                  width: 80,
                  height: 2,
                  background: idx < currentStep ? "#1a73e8" : "#e0e0e0",
                  margin: "0 8px",
                  marginBottom: 20,
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
