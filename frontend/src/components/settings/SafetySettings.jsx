// Safety: the dry-run switch (with a plain explanation) and the protected folders.
import { Lock, ShieldCheck } from "lucide-react";

import Card from "../ui/Card.jsx";
import LockedNote from "./LockedNote.jsx";

const TURN_OFF_WARNING =
  "Turn dry-run OFF?\n\nApproved actions will then really move files (deleted files go to Steward's " +
  "recycle bin and can be undone). Steward still never changes anything without your approval.";

export default function SafetySettings({ settings, saving, onSave }) {
  const dryRun = Boolean(settings.safety && settings.safety.dry_run);
  const locked = settings.locked && settings.locked.dry_run;
  const protectedPaths = (settings.safety && settings.safety.protected_paths) || [];

  function toggle() {
    if (dryRun && !window.confirm(TURN_OFF_WARNING)) {
      return;
    }
    onSave({ dry_run: !dryRun }, dryRun ? "Dry-run is OFF: approved actions now change files." : "Dry-run is ON: actions are previews only.");
  }

  return (
    <Card title="Safety" subtitle="How careful Steward is with your files">
      <div className="stack">
        <div className="setting-row">
          <div>
            <div className="setting-row__title">Dry-run (practice mode)</div>
            <div className="faint">
              When ON, approving an action only previews it; no file is moved or recycled. Turn it OFF when you
              trust the suggestions.
            </div>
          </div>
          <button type="button" role="switch" aria-checked={dryRun} className={`switch ${dryRun ? "switch--on" : ""}`}
            disabled={Boolean(locked) || saving} onClick={toggle} title={dryRun ? "Dry-run is ON" : "Dry-run is OFF"}>
            <span className="switch__thumb" />
          </button>
        </div>
        {locked && <LockedNote variable={locked} />}
        <div>
          <div className="setting-row__title row"><ShieldCheck size={16} /> Protected folders</div>
          <div className="faint">Never moved or recycled, even if approved. Change them in config.yaml.</div>
          <ul className="path-list">
            {protectedPaths.map((path) => (
              <li key={path} className="mono"><Lock size={12} aria-hidden="true" /> {path}</li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  );
}
