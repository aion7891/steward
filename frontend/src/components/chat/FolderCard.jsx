// Shown inside an answer after Steward scanned a folder: real numbers and next steps.
import { Folder, Sparkles } from "lucide-react";

import { suggestionPrompt } from "../../utils/chatInsights.js";
import { formatBytes, formatNumber } from "../../utils/format.js";

/** The stats of a scanned folder as small tiles (also used in the side panel).
 *  compact: only files, size and space you can free (for all watched folders). */
export function FolderTiles({ folder, compact = false }) {
  if (!folder) {
    return <p className="panel-empty">Loading…</p>;
  }
  const all = [
    ["Files", formatNumber(folder.files)],
    ["Size", formatBytes(folder.total_bytes)],
    ["Duplicates", formatNumber(folder.duplicates)],
    ["Temporary", formatNumber(folder.temp)],
    ["Old", formatNumber(folder.stale)],
    ["Can free", formatBytes(folder.reclaimable_bytes)],
  ];
  const tiles = compact ? all.filter(([label]) => ["Files", "Size", "Can free"].includes(label)) : all;
  return (
    <dl className="folder-tiles">
      {tiles.map(([label, value]) => (
        <div key={label} className="folder-tile">
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export default function FolderCard({ folder, onAsk, busy }) {
  const tips = (folder.suggestions || []).slice(0, 3);
  return (
    <section className="folder-card" aria-label={`Scan results for ${folder.name}`}>
      <header className="folder-card__head">
        <Folder size={16} aria-hidden="true" />
        <strong>{folder.name}</strong>
        <span className="folder-card__path mono" title={folder.path}>{folder.path}</span>
      </header>
      <FolderTiles folder={folder} />
      {tips.length > 0 && (
        <div className="folder-card__tips">
          {tips.map((tip) => (
            <button key={tip.kind + tip.title} type="button" className="tip-chip" disabled={busy}
              onClick={() => onAsk(suggestionPrompt(tip, folder))} title={tip.reason}>
              <Sparkles size={13} aria-hidden="true" /> {tip.title}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
