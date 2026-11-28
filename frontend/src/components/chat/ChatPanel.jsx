// Cards on the right of the chat: the folder you are working on, what to do next,
// approvals waiting for you, and what Steward is doing right now. Everything updates live.
import { Activity, Folder, Hand, PanelRightClose, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getDashboard, getFolderCard } from "../../api/steward.js";
import { activitySteps, latestFolder, pendingApprovals, suggestionPrompt } from "../../utils/chatInsights.js";
import { formatBytes, formatNumber, formatRelativeTime } from "../../utils/format.js";
import { FolderTiles } from "./FolderCard.jsx";
import { StepList } from "./StepTrail.jsx";

function PanelCard({ icon: Icon, title, children, aside }) {
  return (
    <section className="panel-card">
      <header className="panel-card__head"><Icon size={15} aria-hidden="true" /> <h3>{title}</h3>{aside}</header>
      {children}
    </section>
  );
}

function Suggestions({ tips, folder, onAsk, busy }) {
  if (!tips.length) {
    return <p className="panel-empty">Nothing to suggest yet. Ask Steward to scan a folder.</p>;
  }
  return (
    <ul className="panel-tips">
      {tips.map((tip) => (
        <li key={tip.kind + tip.title}>
          <button type="button" className="panel-tip" disabled={busy} title={tip.reason}
            onClick={() => onAsk(suggestionPrompt(tip, folder))}>
            <span className={`panel-tip__dot panel-tip__dot--${tip.priority}`} aria-hidden="true" />
            <span className="panel-tip__title">{tip.title}</span>
            {tip.reclaimable_mb > 0 && <span className="panel-tip__size">{formatBytes(tip.reclaimable_mb * 1048576)}</span>}
          </button>
        </li>
      ))}
    </ul>
  );
}

export default function ChatPanel({ messages, job, busy, onAsk, onClose }) {
  const [overview, setOverview] = useState(null);
  const [fresh, setFresh] = useState(null);
  const scanned = latestFolder(messages);
  const scannedPath = scanned ? scanned.path : null;

  // Machine-wide numbers and the folder's current stats, refreshed whenever an answer finishes
  // (an approved archive or delete changes them)
  useEffect(() => {
    if (busy) return;
    getDashboard(7).then(setOverview).catch(() => setOverview(null));
    if (scannedPath) {
      getFolderCard(scannedPath).then((data) => setFresh(data.folder)).catch(() => setFresh(null));
    }
  }, [busy, messages.length, scannedPath]);

  const folder = fresh && scanned && fresh.path === scanned.path ? fresh : scanned;
  const tips = folder ? folder.suggestions || [] : ((overview && overview.suggestions) || []).slice(0, 5);
  const approvals = pendingApprovals(messages);
  const waiting = overview ? overview.status.pending_actions : 0;
  const steps = activitySteps(messages, job).slice(-8);

  return (
    <aside className="chat-panel" aria-label="Workspace">
      <div className="chat-panel__top">
        <span className="chat-panel__label">Workspace</span>
        <button type="button" className="chat-icon-btn" onClick={onClose} title="Hide panel" aria-label="Hide panel">
          <PanelRightClose size={16} />
        </button>
      </div>
      <PanelCard icon={Folder} title={folder ? folder.name : "All watched folders"}
        aside={folder && <span className="panel-card__aside">{formatRelativeTime(folder.scanned_at)}</span>}>
        {folder ? <FolderTiles folder={folder} /> : (
          <FolderTiles folder={overview ? {
            files: overview.status.files_tracked, total_bytes: overview.status.total_size_bytes,
            reclaimable_bytes: overview.status.reclaimable_mb * 1048576,
          } : null} compact />
        )}
        {folder && <p className="panel-path mono" title={folder.path}>{folder.path}</p>}
      </PanelCard>
      <PanelCard icon={Sparkles} title="Suggestions">
        <Suggestions tips={tips} folder={folder} onAsk={onAsk} busy={busy} />
      </PanelCard>
      <PanelCard icon={Hand} title="Needs your approval"
        aside={<span className="panel-card__aside">{formatNumber(approvals.length + waiting)}</span>}>
        {approvals.length === 0 && waiting === 0 && <p className="panel-empty">Nothing is waiting for you.</p>}
        {approvals.map((m) => (
          <p key={m.id} className="panel-line">{(m.approvals && m.approvals[0] && m.approvals[0].summary) || "A file change"} · <em>in this chat</em></p>
        ))}
        {waiting > 0 && <p className="panel-line"><Link to="/dashboard">{waiting} suggestion(s) on the Dashboard</Link></p>}
      </PanelCard>
      <PanelCard icon={Activity} title={job ? "Working now" : "Last answer"}>
        {steps.length ? <StepList steps={steps} /> : <p className="panel-empty">Steps appear here while Steward works.</p>}
      </PanelCard>
    </aside>
  );
}
