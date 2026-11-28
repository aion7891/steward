// Reports: list of weekly/daily reports, generate one now, and read it in the page.
import { useEffect, useState } from "react";

import { deleteReport, generateReport, getReportLibrary } from "../api/steward.js";
import { formatDateTime } from "../utils/format.js";
import PageHeader from "../components/layout/PageHeader.jsx";
import ReportList from "../components/reports/ReportList.jsx";
import ReportViewer from "../components/reports/ReportViewer.jsx";
import Alert from "../components/ui/Alert.jsx";
import { Loading } from "../components/ui/Spinner.jsx";
import { useApi } from "../hooks/useApi.js";
import "../styles/reports.css";

export default function ReportsPage() {
  const { data, error, loading, reload } = useApi(getReportLibrary, []);
  const [selectedKey, setSelectedKey] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [deleting, setDeleting] = useState(null);
  const [notice, setNotice] = useState(null);
  const reports = (data && data.reports) || [];

  // Show the newest report until the user picks another one, and again when the open one was deleted
  useEffect(() => {
    if (reports.length > 0 && !reports.some((r) => r.key === selectedKey)) setSelectedKey(reports[0].key);
  }, [reports, selectedKey]);

  async function handleGenerate() {
    setGenerating(true);
    try {
      const result = await generateReport("weekly");
      setNotice({ tone: "success", text: result.message });
      if (result.report) setSelectedKey(result.report.key);
      await reload();
    } catch (err) {
      setNotice({ tone: "danger", text: err.message });
    } finally {
      setGenerating(false);
    }
  }

  // Delete one report after asking; if it was open, the newest remaining report is shown (see above)
  async function handleDelete(report) {
    const name = `${report.period} report of ${formatDateTime(report.created_at)}`;
    if (!window.confirm(`Delete the ${name}?\n\nIts Markdown and HTML files are deleted for good.`)) return;
    setDeleting(report.key);
    try {
      const result = await deleteReport(report.key);
      setNotice({ tone: "success", text: result.message });
      await reload();
    } catch (err) {
      setNotice({ tone: "danger", text: err.message });
    } finally {
      setDeleting(null);
    }
  }

  return (
    <>
      <PageHeader title="Reports" subtitle="Disk use, file types, activity and cleanup suggestions, in plain words." />
      {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}
      {error && <Alert tone="danger" error={error} />}
      {loading && !data ? (
        <Loading label="Loading reports…" />
      ) : (
        <div className="grid reports-grid">
          <ReportList reports={reports} selectedKey={selectedKey} onSelect={setSelectedKey}
            onGenerate={handleGenerate} generating={generating} onDelete={handleDelete} deleting={deleting} />
          <ReportViewer report={reports.find((r) => r.key === selectedKey) || null} />
        </div>
      )}
    </>
  );
}
