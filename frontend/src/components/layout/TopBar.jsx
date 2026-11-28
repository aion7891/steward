// Top bar: API connection status, active model, dry-run mode and pending approvals.
import { Bell, Cpu, ShieldCheck, ShieldOff } from "lucide-react";
import { Link } from "react-router-dom";

import Badge from "../ui/Badge.jsx";

function ConnectionStatus({ health, error }) {
  if (error) {
    return (
      <span className="row faint" title={error.message}>
        <span className="status-dot status-dot--down" /> API unreachable
      </span>
    );
  }
  if (!health) {
    return (
      <span className="row faint">
        <span className="status-dot" /> Connecting…
      </span>
    );
  }
  return (
    <span className="row faint">
      <span className="status-dot status-dot--ok" /> Connected
    </span>
  );
}

export default function TopBar({ health, error }) {
  const models = (health && health.models) || {};
  const dryRun = health ? Boolean(health.safety && health.safety.dry_run) : null;
  const pending = (health && health.pending_actions) || 0;
  return (
    <header className="topbar">
      <ConnectionStatus health={health} error={error} />
      {models.chat_model && (
        <Badge tone="neutral" icon={Cpu} title={`Provider: ${models.chat_provider}`}>
          {models.chat_model}
        </Badge>
      )}
      {dryRun !== null && (
        <Badge
          tone={dryRun ? "success" : "warning"}
          icon={dryRun ? ShieldCheck : ShieldOff}
          title={dryRun ? "Practice mode: approved actions are previewed, files are not changed" : "Approved actions change files"}
        >
          {dryRun ? "Dry-run ON" : "Dry-run OFF"}
        </Badge>
      )}
      {pending > 0 && (
        <Link to="/dashboard#todo" title="Open the to-do list on the Dashboard">
          <Badge tone="warning" icon={Bell}>
            {pending} to review
          </Badge>
        </Link>
      )}
    </header>
  );
}
