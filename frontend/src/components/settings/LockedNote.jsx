// Explains that a setting is fixed by a value in .env (which always wins over the UI).
import { Lock } from "lucide-react";

import Alert from "../ui/Alert.jsx";

export default function LockedNote({ variable }) {
  return (
    <Alert tone="info">
      <span>
        <Lock size={14} aria-hidden="true" className="locked-note__icon" /> Locked by <code>{variable}</code> in <code>.env</code>. Edit or remove
        that line and restart Steward to change it here.
      </span>
    </Alert>
  );
}
