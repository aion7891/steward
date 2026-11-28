// One file action (delete / move / archive) shown as a row with its buttons on the right.
import { Archive, FolderInput, Trash2 } from "lucide-react";

import { baseName, formatBytes, formatRelativeTime, shortPath } from "../../utils/format.js";

const KINDS = {
  delete: { icon: Trash2, label: "Recycle" },
  move: { icon: FolderInput, label: "Move" },
  archive: { icon: Archive, label: "Archive" },
};

function sourceLabel(sourcePath) {
  // Archive actions store a JSON list of paths
  if (String(sourcePath).startsWith("[")) {
    try {
      const paths = JSON.parse(sourcePath);
      return { name: `${paths.length} files`, folder: shortPath(paths[0], 3) };
    } catch {
      return { name: sourcePath, folder: "" };
    }
  }
  return { name: baseName(sourcePath), folder: shortPath(sourcePath, 4) };
}

export default function ActionItem({ action, children }) {
  const kind = KINDS[action.action_type] || { icon: FolderInput, label: action.action_type };
  const Icon = kind.icon;
  const { name, folder } = sourceLabel(action.source_path);
  return (
    <li className="action-item">
      <span className="action-item__icon" title={kind.label}>
        <Icon size={16} aria-hidden="true" />
      </span>
      <div className="action-item__main">
        <div className="action-item__title">
          <span className="action-item__kind">{kind.label}</span> {name}
        </div>
        <div className="action-item__meta" title={action.source_path}>
          {folder}
        </div>
        <div className="action-item__meta">
          {action.reason || "No reason given"}
          {action.size_bytes > 0 && ` · ${formatBytes(action.size_bytes)}`}
          {` · #${action.id} · ${formatRelativeTime(action.decided_at || action.timestamp)}`}
        </div>
        {action.target_path && action.action_type === "move" && (
          <div className="action-item__meta">→ {shortPath(action.target_path, 4)}</div>
        )}
      </div>
      <div className="action-item__actions">{children}</div>
    </li>
  );
}
