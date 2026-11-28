// List of generated reports (newest first) with a "Generate report now" button.
import { FilePlus2, FileText } from "lucide-react";

import { formatDateTime, formatRelativeTime } from "../../utils/format.js";
import Badge from "../ui/Badge.jsx";
import Button from "../ui/Button.jsx";
import Card from "../ui/Card.jsx";
import EmptyState from "../ui/EmptyState.jsx";

export default function ReportList({ reports, selectedKey, onSelect, onGenerate, generating }) {
  return (
    <Card title="Reports" subtitle="Auto: Sundays 09:00"
      actions={<Button size="sm" variant="primary" icon={FilePlus2} loading={generating} onClick={onGenerate}>Generate now</Button>}>
      {reports.length === 0 ? (
        <EmptyState icon={FileText} title="No reports yet">Click <strong>Generate now</strong> for your first report.</EmptyState>
      ) : (
        <ul className="report-list">
          {reports.map((report) => (
            <li key={report.key}>
              <button type="button" className={`report-item ${report.key === selectedKey ? "report-item--active" : ""}`}
                onClick={() => onSelect(report.key)} title={formatDateTime(report.created_at)}>
                <span className="report-item__title">
                  {report.period.charAt(0).toUpperCase() + report.period.slice(1)} report
                </span>
                <span className="row">
                  <span className="faint">{formatRelativeTime(report.created_at)}</span>
                  {Object.keys(report.formats).map((fmt) => (
                    <Badge key={fmt} tone={report.formats[fmt].available ? "neutral" : "danger"}>
                      {fmt === "markdown" ? "MD" : "HTML"}
                    </Badge>
                  ))}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
