// Reports: list of weekly/daily reports, generate one now, and read it in the page.
import { useEffect, useState } from "react";

import { generateReport, getReportLibrary } from "../api/steward.js";
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
  const [notice, setNotice] = useState(null);
  const reports = (data && data.reports) || [];

  // Show the newest report until the user picks another one
  useEffect(() => {
    if (!selectedKey && reports.length > 0) setSelectedKey(reports[0].key);
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
            onGenerate={handleGenerate} generating={generating} />
          <ReportViewer report={reports.find((r) => r.key === selectedKey) || null} />
        </div>
      )}
    </>
  );
}
