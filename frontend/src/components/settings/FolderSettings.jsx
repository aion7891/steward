// Watched folders: the folders the hourly background scan looks at.
import { FolderPlus, Save, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { baseName, shortPath } from "../../utils/format.js";
import Badge from "../ui/Badge.jsx";
import Button from "../ui/Button.jsx";
import Card from "../ui/Card.jsx";

export default function FolderSettings({ settings, saving, onSave }) {
  const saved = settings.folders || [];
  // Work on a draft list of paths (as the user knows them) until "Save folders" is clicked
  const [draft, setDraft] = useState(saved.map((f) => f.display_path));
  const [newPath, setNewPath] = useState("");
  useEffect(() => setDraft(saved.map((f) => f.display_path)), [settings]);

  const savedPaths = saved.map((f) => f.display_path);
  const changed = draft.join("\n") !== savedPaths.join("\n");
  const statusOf = (path) => saved.find((f) => f.display_path === path);

  function add(event) {
    event.preventDefault();
    const path = newPath.trim();
    if (path && !draft.includes(path)) {
      setDraft([...draft, path]);
    }
    setNewPath("");
  }

  return (
    <Card title="Watched folders" subtitle="Scanned automatically every hour by the background worker">
      <div className="stack">
        <ul className="folder-list">
          {draft.map((path) => {
            const status = statusOf(path);
            return (
              <li key={path} className="folder-row">
                <span className="folder-row__path" title={path}>
                  <strong>{baseName(path)}</strong> <span className="faint mono">{shortPath(path, 3)}</span>
                </span>
                {status ? (
                  <Badge tone={status.available ? "success" : "danger"}>{status.available ? "found" : "missing"}</Badge>
                ) : (
                  <Badge tone="info">new</Badge>
                )}
                <button type="button" className="chat-icon-btn" title="Remove" disabled={draft.length === 1}
                  onClick={() => setDraft(draft.filter((p) => p !== path))}>
                  <Trash2 size={14} />
                </button>
              </li>
            );
          })}
        </ul>
        <form className="row" onSubmit={add}>
          <input className="input mono" value={newPath} onChange={(e) => setNewPath(e.target.value)}
            placeholder="/Users/you/Documents/Projects" aria-label="Folder to add" />
          <Button type="submit" icon={FolderPlus} disabled={!newPath.trim()}>Add</Button>
        </form>
        <div className="row">
          <Button variant="primary" icon={Save} loading={saving} disabled={!changed}
            onClick={() => onSave({ watched_folders: draft }, "Watched folders saved. The next hourly scan uses them.")}>
            Save folders
          </Button>
          {changed && <span className="faint">Unsaved changes</span>}
        </div>
      </div>
    </Card>
  );
}
