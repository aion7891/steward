// Scan a folder: pick a path, watch the scan run, then review suggestions and proposals.
// The job id lives in the address (/scan?job=...), so refreshing the page keeps the results.
import { useEffect, useState } from "react";
import { useOutletContext, useSearchParams } from "react-router-dom";

import { getFolderScan } from "../api/steward.js";
import PageHeader from "../components/layout/PageHeader.jsx";
import RecentFolderScans from "../components/scan/RecentFolderScans.jsx";
import ScanForm from "../components/scan/ScanForm.jsx";
import ScanProgress from "../components/scan/ScanProgress.jsx";
import ScanResults from "../components/scan/ScanResults.jsx";
import Alert from "../components/ui/Alert.jsx";
import Card from "../components/ui/Card.jsx";
import { Loading } from "../components/ui/Spinner.jsx";
import { usePolling } from "../hooks/usePolling.js";
import "../styles/scan.css";

const POLL_MS = 1000;

function HowItWorks() {
  return (
    <Card title="How it works">
      <ol className="how-list">
        <li>Steward walks the folder and fingerprints new or changed files.</li>
        <li>It finds duplicates, temporary, old and large files inside that folder only.</li>
        <li>Optional: safe proposals are added to your to-do list. Nothing moves until you approve.</li>
      </ol>
    </Card>
  );
}

function JobView({ jobId, dryRun, onFinished }) {
  const [finished, setFinished] = useState(false);
  // Poll every second, and stop asking the API once the job has finished
  const { data, error } = usePolling(() => getFolderScan(jobId), POLL_MS, !finished);
  const job = data && data.job;
  useEffect(() => {
    if (job && (job.status === "done" || job.status === "failed")) {
      setFinished(true);
      onFinished();
    }
    // onFinished is recreated on every render; reacting to `job` alone is enough
  }, [job]);
  if (error && !job) {
    return <Alert tone="danger" title="Could not load this scan" error={error} />;
  }
  if (!job) {
    return <Loading label="Loading scan…" />;
  }
  return (
    <div className="stack">
      {!finished || job.status === "failed" ? <ScanProgress job={job} /> : null}
      {job.status === "failed" && <Alert tone="danger" title="The scan failed">{job.error}</Alert>}
      {job.status === "done" && <ScanResults job={job} dryRun={dryRun} />}
    </div>
  );
}

export default function ScanPage() {
  const [params, setParams] = useSearchParams();
  const { health } = useOutletContext() || {};
  const jobId = params.get("job");
  const [finishedCount, setFinishedCount] = useState(0);
  const dryRun = health ? Boolean(health.safety && health.safety.dry_run) : true;
  return (
    <>
      <PageHeader title="Scan a folder" subtitle="Pick a folder; Steward scans it and suggests what to do." />
      <div className="grid grid--two">
        <ScanForm onStarted={(job) => setParams({ job: job.id })} />
        <div className="stack">
          <HowItWorks />
          {/* Reload the list when a scan starts AND when it finishes, so statuses stay current */}
          <RecentFolderScans currentJobId={jobId} refreshKey={`${jobId}-${finishedCount}`}
            onSelect={(id) => setParams({ job: id })} />
        </div>
      </div>
      {jobId && (
        <JobView key={jobId} jobId={jobId} dryRun={dryRun} onFinished={() => setFinishedCount((n) => n + 1)} />
      )}
    </>
  );
}
