// The "please confirm" box under a cleanup button. A permanent delete needs the word DELETE typed.
import { useState } from "react";

import Button from "../ui/Button.jsx";
import { canConfirm, CONFIRM_WORD } from "./dataCleanup.js";

export default function ConfirmBox({ text, hard, busy, onConfirm, onCancel, confirmLabel }) {
  const [typed, setTyped] = useState("");
  const mode = hard ? "hard" : "clear";
  return (
    <div className={`confirm-box ${hard ? "confirm-box--danger" : ""}`} role="alertdialog" aria-label="Please confirm">
      <p>{text}</p>
      {hard && (
        <label className="confirm-box__type">
          <span>Type <strong>{CONFIRM_WORD}</strong> to confirm</span>
          <input value={typed} onChange={(e) => setTyped(e.target.value)} autoFocus autoComplete="off"
            aria-label={`Type ${CONFIRM_WORD} to confirm`} />
        </label>
      )}
      <div className="row">
        <Button variant={hard ? "danger" : "primary"} size="sm" loading={busy} disabled={!canConfirm(mode, typed)}
          onClick={() => onConfirm(typed.trim())}>
          {confirmLabel || (hard ? "Delete for good" : "Yes, clear")}
        </Button>
        <Button variant="ghost" size="sm" onClick={onCancel} disabled={busy}>Cancel</Button>
      </div>
    </div>
  );
}
