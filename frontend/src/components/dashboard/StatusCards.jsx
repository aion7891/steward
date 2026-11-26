// The six headline numbers at the top of the dashboard.
import { AlertTriangle, Clock, Files, HardDrive, ListChecks, ScanLine } from "lucide-react";

import { formatBytes, formatDateTime, formatNumber, formatRelativeTime } from "../../utils/format.js";
import StatCard from "../ui/StatCard.jsx";

export default function StatusCards({ status }) {
  const pending = status.pending_actions || 0;
  const waiting = status.approved_waiting || 0;
  const errors = status.errors_24h || 0;
  return (
    <div className="grid grid--stats">
      <StatCard
        label="Last scan"
        icon={Clock}
        value={formatRelativeTime(status.last_scan_at)}
        hint={status.last_scan_at ? formatDateTime(status.last_scan_at) : "Run a scan to get started"}
      />
      <StatCard
        label="Files tracked"
        icon={Files}
        value={formatNumber(status.files_tracked)}
        hint={`${formatBytes(status.total_size_bytes)} · ${formatNumber(status.files_indexed)} searchable`}
      />
      <StatCard
        label="Checked today"
        icon={ScanLine}
        value={formatNumber(status.files_checked_today)}
        hint={`${formatNumber(status.files_changed_today)} changed · ${status.scans_today || 0} scan(s)`}
      />
      <StatCard
        label="To review"
        icon={ListChecks}
        tone={pending > 0 ? "warning" : "success"}
        value={formatNumber(pending)}
        hint={waiting > 0 ? `${waiting} approved, waiting to run` : "Actions waiting for your decision"}
      />
      <StatCard
        label="Space you can free"
        icon={HardDrive}
        value={formatBytes(status.reclaimable_bytes)}
        hint="Duplicates, temp and old files"
      />
      <StatCard
        label="Errors (24 h)"
        icon={AlertTriangle}
        tone={errors > 0 ? "danger" : "success"}
        value={formatNumber(errors)}
        hint={errors > 0 ? "Unreadable files or failed actions" : "Everything ran cleanly"}
      />
    </div>
  );
}
