// The last folder scans started from this page (kept in the API's memory until it restarts).
import { History } from "lucide-react";

import { listFolderScans } from "../../api/steward.js";
import { useApi } from "../../hooks/useApi.js";
import { baseName, formatRelativeTime, shortPath } from "../../utils/format.js";
import Badge from "../ui/Badge.jsx";
import Card from "../ui/Card.jsx";
import EmptyState from "../ui/EmptyState.jsx";

const STATUS_TONE = { done: "success", failed: "danger", running: "info", queued: "info" };

export default function RecentFolderScans({ currentJobId, refreshKey, onSelect }) {
  const { data } = useApi(() => listFolderScans(8), [refreshKey]);
  const jobs = (data && data.jobs) || [];
  return (
    <Card title="Recent folder scans">
      {jobs.length === 0 ? (
        <EmptyState icon={History} title="No folder scans yet" />
      ) : (
        <ul className="recent-scans">
          {jobs.map((job) => (
            <li key={job.id}>
              <button type="button" className={`recent-scans__item ${job.id === currentJobId ? "recent-scans__item--active" : ""}`}
                onClick={() => onSelect(job.id)} title={job.display_path}>
                <span className="recent-scans__name">{baseName(job.display_path)}</span>
                <span className="recent-scans__path mono faint">{shortPath(job.display_path, 3)}</span>
                <span className="row">
                  <Badge tone={STATUS_TONE[job.status] || "neutral"}>{job.status}</Badge>
                  <span className="faint">{formatRelativeTime(job.created_at)}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
