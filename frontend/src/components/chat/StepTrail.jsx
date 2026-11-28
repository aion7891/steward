// The steps behind an answer: which helper did what, and the outcome of each tool.
import { Check, ChevronRight, X } from "lucide-react";

import { stepLine } from "../../utils/chatJobs.js";
import { stepSummary } from "../../utils/chatInsights.js";
import Spinner from "../ui/Spinner.jsx";

function StepIcon({ status }) {
  if (status === "done") return <Check size={13} className="step__icon step__icon--done" aria-label="done" />;
  if (status === "error") return <X size={13} className="step__icon step__icon--error" aria-label="failed" />;
  return <Spinner />;
}

/** The plain list of steps (used live while working, and inside the collapsible trail). */
export function StepList({ steps }) {
  return (
    <ol className="steps">
      {(steps || []).map((step) => (
        <li key={step.id} className={`step step--${step.status} step--${step.kind}`}>
          <StepIcon status={step.status} />
          <div className="step__body">
            <span>{stepLine(step)}</span>
            {step.detail && <div className="step__detail">{step.detail}</div>}
          </div>
        </li>
      ))}
    </ol>
  );
}

/** "Worked 9 s · Scanner · 2 steps" above a finished answer; click to see every step. */
export default function StepTrail({ steps, durationSec }) {
  if (!steps || steps.length === 0) {
    return null;
  }
  return (
    <details className="step-trail">
      <summary>
        <ChevronRight size={14} className="step-trail__chevron" aria-hidden="true" />
        {stepSummary(steps, durationSec)}
      </summary>
      <StepList steps={steps} />
    </details>
  );
}
