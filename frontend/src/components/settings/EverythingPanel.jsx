// "Delete everything": all of Steward's own data in one go, after typing DELETE. The recycle bin and
// backups only when ticked; archives (the user's zipped files) never. Steward then starts fresh.
import { Trash2 } from "lucide-react";
import { useState } from "react";

import Button from "../ui/Button.jsx";
import ConfirmBox from "./ConfirmBox.jsx";
import { countOf, plural } from "./dataCleanup.js";

export default function EverythingPanel({ summary, busy, asking, onAsk, onCancel, onConfirm }) {
  const [emptyRecycle, setEmptyRecycle] = useState(false);
  const [deleteBackups, setDeleteBackups] = useState(false);
  const recycled = countOf(summary, "recycle");
  const backups = ((summary && summary.backups) || []).length;
  return (
    <div className="everything">
      <div className="setting-row">
        <div>
          <div className="setting-row__title">Delete everything</div>
          <div className="faint">
            Chats, knowledge notes, the scan history and file index, the to-do and action history, the search
            index and reports, in one go. The Dashboard is empty afterwards and Steward starts fresh with the
            next scan. Your archives are never deleted.
          </div>
        </div>
        <Button size="sm" variant="danger" icon={Trash2} disabled={busy} onClick={onAsk}>Delete everything</Button>
      </div>
      <label className="checkbox">
        <input type="checkbox" checked={emptyRecycle} disabled={!recycled} onChange={(e) => setEmptyRecycle(e.target.checked)} />
        <span>Also empty the recycle bin ({plural(recycled, "item")}); Undo stops working for them</span>
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={deleteBackups} disabled={!backups} onChange={(e) => setDeleteBackups(e.target.checked)} />
        <span>Also delete the backups ({plural(backups, "backup")})</span>
      </label>
      {asking && (
        <ConfirmBox text="Delete all of Steward's data for good? There is no backup and no undo." hard busy={busy}
          confirmLabel="Delete everything" onCancel={onCancel}
          onConfirm={(typed) => onConfirm({ emptyRecycle, deleteBackups, confirm: typed })} />
      )}
    </div>
  );
}
