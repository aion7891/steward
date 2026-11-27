// Shows one report: the styled HTML version in a locked-down frame, or the Markdown as text.
import { Download, FileText } from "lucide-react";
import ReactMarkdown from "react-markdown";

import { getReport, reportDownloadUrl } from "../../api/steward.js";
import { useApi } from "../../hooks/useApi.js";
import { formatDateTime } from "../../utils/format.js";
import Alert from "../ui/Alert.jsx";
import Card from "../ui/Card.jsx";
import EmptyState from "../ui/EmptyState.jsx";
import { Loading } from "../ui/Spinner.jsx";

/** Prefer the HTML copy (it has proper tables and styling); fall back to Markdown. */
export function pickFormat(report) {
  const formats = (report && report.formats) || {};
  if (formats.html && formats.html.available) return { format: "html", id: formats.html.id };
  if (formats.markdown && formats.markdown.available) return { format: "markdown", id: formats.markdown.id };
  return null;
}

function DownloadLinks({ report }) {
  return (
    <div className="row">
      {Object.entries(report.formats).filter(([, f]) => f.available).map(([fmt, f]) => (
        <a key={fmt} className="btn btn--sm btn--secondary" href={reportDownloadUrl(f.id)} download>
          <Download size={14} aria-hidden="true" /> {fmt === "html" ? "HTML" : "Markdown"}
        </a>
      ))}
    </div>
  );
}

export default function ReportViewer({ report }) {
  const choice = pickFormat(report);
  const { data, error, loading } = useApi(() => (choice ? getReport(choice.id) : Promise.resolve(null)),
    [choice && choice.id]);
  if (!report) {
    return <Card><EmptyState icon={FileText} title="Pick a report to read it here" /></Card>;
  }
  const content = data && data.report && data.report.content;
  return (
    <Card title={`${report.period.charAt(0).toUpperCase() + report.period.slice(1)} report`}
      subtitle={formatDateTime(report.created_at)} actions={<DownloadLinks report={report} />}>
      {!choice && <Alert tone="warning">The files for this report no longer exist.</Alert>}
      {error && <Alert tone="danger" error={error} />}
      {choice && loading && !content && <Loading label="Loading report…" />}
      {content && choice.format === "html" && (
        // sandbox="" = no scripts, no forms, no navigation: the report can only be looked at
        <iframe className="report-frame" title="Report" sandbox="" srcDoc={content} />
      )}
      {content && choice.format === "markdown" && (
        <div className="chat-markdown report-markdown"><ReactMarkdown skipHtml>{content}</ReactMarkdown></div>
      )}
    </Card>
  );
}
