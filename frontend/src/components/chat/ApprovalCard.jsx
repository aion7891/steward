// Shown when the AI wants to change files: what it wants to do, and Approve / Reject buttons.
import { Check, ShieldAlert, ShieldCheck, X } from "lucide-react";

import Badge from "../ui/Badge.jsx";
import Button from "../ui/Button.jsx";

const NAMES_SHOWN = 5;

function Step({ step }) {
  const names = step.names || [];
  return (
    <li className="approval-step">
      <div className="approval-step__title">{step.summary}</div>
      {names.length > 0 && (
        <div className="approval-step__files mono" title={(step.paths || []).join("\n")}>
          {names.slice(0, NAMES_SHOWN).join(", ")}
          {names.length > NAMES_SHOWN && ` +${names.length - NAMES_SHOWN} more`}
        </div>
      )}
      {step.reason && <div className="faint">Why: {step.reason}</div>}
      {step.dry_run ? (
        <Badge tone="success" icon={ShieldCheck}>Dry-run ON: preview only, no file changes</Badge>
      ) : (
        <Badge tone="warning" icon={ShieldAlert}>Will change files (undo is available)</Badge>
      )}
    </li>
  );
}

export default function ApprovalCard({ message, busy, onDecide }) {
  const decided = message.decision;
  return (
    <div className="approval-card">
      <div className="approval-card__title">Steward wants to change files and needs your approval</div>
      <ul className="approval-steps">
        {(message.approvals || []).map((step, index) => <Step key={`${step.tool}-${index}`} step={step} />)}
      </ul>
      {decided ? (
        <div className="faint">You {decided === "approved" ? "approved" : "rejected"} this.</div>
      ) : (
        <div className="row">
          <Button size="sm" variant="primary" icon={Check} loading={busy} onClick={() => onDecide(message, true)}>
            Approve
          </Button>
          <Button size="sm" variant="ghost" icon={X} disabled={busy} onClick={() => onDecide(message, false)}>
            Reject
          </Button>
        </div>
      )}
    </div>
  );
}
