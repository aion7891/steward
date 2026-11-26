// File types by size, learned work habits, and the most recent scans.
import { formatBytes, formatDateTime, formatNumber } from "../../utils/format.js";
import Badge from "../ui/Badge.jsx";
import Card from "../ui/Card.jsx";
import EmptyState from "../ui/EmptyState.jsx";

export function CategoryBreakdown({ categories }) {
  const largest = Math.max(1, ...categories.map((c) => c.size_bytes));
  return (
    <Card title="File types" subtitle="Share of disk space by category">
      {categories.length === 0 ? (
        <EmptyState title="No files tracked yet" />
      ) : (
        <ul className="bar-list">
          {categories.map((c) => (
            <li key={c.category} className="bar-row">
              <div className="bar-row__label">
                <span>{c.category}</span>
                <span className="faint">
                  {formatNumber(c.count)} · {formatBytes(c.size_bytes)}
                </span>
              </div>
              <div className="bar-row__track">
                <div className="bar-row__fill" style={{ width: `${Math.max(2, (c.size_bytes / largest) * 100)}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function Patterns({ patterns }) {
  return (
    <Card title="Work habits" subtitle="What Steward has noticed">
      {patterns.length === 0 ? (
        <EmptyState title="Still learning">Habits appear after a few scans and reports.</EmptyState>
      ) : (
        <ul className="pattern-list">
          {patterns.map((p) => (
            <li key={p.title}>
              <div className="suggestion__title">{p.title}</div>
              <div className="faint">{p.description}</div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function RecentScans({ scans }) {
  return (
    <Card title="Recent scans" subtitle="Latest background and folder scans">
      {scans.length === 0 ? (
        <EmptyState title="No scans yet" />
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Finished</th>
                <th>Files</th>
                <th>Changed</th>
                <th>Duplicates</th>
                <th>Errors</th>
              </tr>
            </thead>
            <tbody>
              {scans.map((s) => (
                <tr key={s.id}>
                  <td>{formatDateTime(s.completed_at)}</td>
                  <td>{formatNumber(s.files_seen)}</td>
                  <td>{formatNumber(s.hashed_files)}</td>
                  <td>{formatNumber(s.duplicates_found)}</td>
                  <td>{s.errors ? <Badge tone="danger">{s.errors}</Badge> : <span className="faint">0</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
