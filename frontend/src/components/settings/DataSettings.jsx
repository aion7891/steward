// Data & cleanup: clear Steward's own data (chats, knowledge notes, topics, recycle bin) and
// restore backups. "Clear" keeps a backup; deleting for good needs the word DELETE typed.
import { ArchiveRestore, Eraser, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { clearData, deleteBackup, deleteEverything, getDataSummary, restoreBackup } from "../../api/steward.js";
import { announceDataChanged } from "../../utils/dataEvents.js";
import { formatBytes, formatDateTime } from "../../utils/format.js";
import Alert from "../ui/Alert.jsx";
import Button from "../ui/Button.jsx";
import Card from "../ui/Card.jsx";
import ConfirmBox from "./ConfirmBox.jsx";
import { confirmText, countOf, plural, TARGETS } from "./dataCleanup.js";
import EverythingPanel from "./EverythingPanel.jsx";

function TargetRow({ target, summary, pending, busy, onAsk, onConfirm, onCancel }) {
  const count = countOf(summary, target.key);
  const size = summary && summary[target.key] && summary[target.key].size_bytes;
  const asking = pending && pending.key === target.key;
  return (
    <div className="data-row">
      <div className="setting-row">
        <div>
          <div className="setting-row__title">{target.title}</div>
          <div className="faint">{target.explain}</div>
          <div className="data-row__count">{plural(count, target.noun)}{size ? ` · ${formatBytes(size)}` : ""}</div>
        </div>
        <div className="row data-row__actions">
          {target.backup && (
            <Button size="sm" icon={Eraser} disabled={!count || busy} onClick={() => onAsk(target.key, false)}>Clear</Button>
          )}
          <Button size="sm" variant="danger" icon={Trash2} disabled={!count || busy} onClick={() => onAsk(target.key, true)}>
            {target.hardLabel || "Delete for good"}
          </Button>
        </div>
      </div>
      {asking && (
        <ConfirmBox text={confirmText(target, pending.hard ? "hard" : "clear", count)} hard={pending.hard} busy={busy}
          onConfirm={onConfirm} onCancel={onCancel} />
      )}
    </div>
  );
}

function Backups({ backups, pending, busy, onRestore, onAsk, onConfirm, onCancel }) {
  if (!backups || backups.length === 0) {
    return <p className="faint">No backups yet. "Clear" keeps one here, so it can be restored.</p>;
  }
  return (
    <ul className="backup-list">
      {backups.map((b) => (
        <li key={b.id} className="backup-list__item">
          <div className="setting-row">
            <div>
              <div className="setting-row__title">
                {b.label}{b.items != null ? ` · ${plural(b.items, b.kind === "chats" ? "chat" : "note")}` : ""}
              </div>
              <div className="faint">{formatDateTime(b.created_at)} · {formatBytes(b.size_bytes)}</div>
            </div>
            <div className="row">
              <Button size="sm" icon={ArchiveRestore} disabled={busy} onClick={() => onRestore(b.id)}>Restore</Button>
              <Button size="sm" variant="ghost" icon={Trash2} disabled={busy} onClick={() => onAsk(b.id)} aria-label={`Delete backup ${b.id}`} />
            </div>
          </div>
          {pending && pending.backupId === b.id && (
            <ConfirmBox text="Delete this backup for good? It can't be restored afterwards." hard busy={busy}
              onConfirm={onConfirm} onCancel={onCancel} />
          )}
        </li>
      ))}
    </ul>
  );
}

export default function DataSettings({ onChatsChanged }) {
  const [summary, setSummary] = useState(null);
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  const refresh = () => getDataSummary().then(setSummary).catch((err) => setNotice({ tone: "danger", text: err.message }));
  useEffect(() => { refresh(); }, []);

  // Every action: run it, show Steward's own message, refresh the numbers
  async function run(action, after) {
    setBusy(true);
    try {
      const result = await action();
      setNotice({ tone: "success", text: result.message });
      setPending(null);
      announceDataChanged();  // e.g. the "to review" badge refreshes at once
      if (after) after();
    } catch (err) {
      setNotice({ tone: "danger", text: err.message });
    } finally {
      setBusy(false);
      refresh();
    }
  }

  function confirm(typed) {
    if (pending.everything) {
      run(() => deleteEverything(typed), onChatsChanged);  // typed = {emptyRecycle, deleteBackups, confirm}
    } else if (pending.backupId) {
      run(() => deleteBackup(pending.backupId, typed));
    } else {
      const key = pending.key;
      run(() => clearData(key, pending.hard, typed), key === "chats" ? onChatsChanged : null);
    }
  }

  const cancel = () => setPending(null);
  return (
    <Card title="Data & cleanup" subtitle="Steward's own data. Files in your folders are never touched here.">
      <div className="stack">
        {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}
        <EverythingPanel summary={summary} busy={busy} asking={Boolean(pending && pending.everything)}
          onAsk={() => setPending({ everything: true })} onCancel={cancel} onConfirm={confirm} />
        {TARGETS.map((target) => (
          <TargetRow key={target.key} target={target} summary={summary} pending={pending} busy={busy}
            onAsk={(key, hard) => setPending({ key, hard })} onConfirm={confirm} onCancel={cancel} />
        ))}
        <h4 className="data-backups__title">Backups</h4>
        <Backups backups={summary && summary.backups} pending={pending} busy={busy}
          onRestore={(id) => run(() => restoreBackup(id), id.startsWith("chats-") ? onChatsChanged : null)}
          onAsk={(backupId) => setPending({ backupId })} onConfirm={confirm} onCancel={cancel} />
      </div>
    </Card>
  );
}
