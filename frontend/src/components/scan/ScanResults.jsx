// Everything shown after a folder scan finishes: summary, warnings, suggestions, findings, proposals.
import { FileSearch, HardDrive, ListChecks, Sparkles } from "lucide-react";

import { formatBytes, formatNumber } from "../../utils/format.js";
import Suggestions from "../dashboard/Suggestions.jsx";
import Alert from "../ui/Alert.jsx";
import StatCard from "../ui/StatCard.jsx";
import FindingsList from "./FindingsList.jsx";
import ScanProposals from "./ScanProposals.jsx";

function candidateCount(findings) {
  return (findings.duplicates.extra_copies || 0) + findings.temp_files.count + findings.stale_files.count
    + findings.large_files.count;
}

function Notices({ result }) {
  const skipped = ((result.proposals && result.proposals.skipped_protected) || []).length;
  return (
    <>
      {result.protected && (
        <Alert tone="warning" title="Protected folder">
          This folder is on your protected list. Steward scanned it read-only and will never move or recycle its files.
        </Alert>
      )}
      {!result.protected && skipped > 0 && (
        <Alert tone="warning">{skipped} file(s) inside protected folders were skipped and got no proposal.</Alert>
      )}
      {result.scan.errors > 0 && (
        <Alert tone="warning">{result.scan.errors} file(s) could not be read (permissions or locked files).</Alert>
      )}
      {result.index && (
        <Alert tone="info">
          Chat search: {result.index.indexed} document(s) added, {result.index.skipped} skipped (unchanged, unsupported
          or private), {result.index.errors} error(s).
        </Alert>
      )}
    </>
  );
}

export default function ScanResults({ job, dryRun }) {
  const result = job.result;
  const proposals = result.proposals;
  return (
    <div className="stack">
      <div className="grid grid--stats">
        <StatCard label="Files scanned" icon={FileSearch} value={formatNumber(result.scan.files_seen)}
          hint={`${formatNumber(result.scan.hashed_files)} new or changed`} />
        <StatCard label="Space you can free" icon={HardDrive} value={formatBytes(result.reclaimable_bytes)}
          hint="Duplicates, temp and old files" />
        <StatCard label="Cleanup candidates" icon={Sparkles} tone={candidateCount(result.findings) ? "warning" : "success"}
          value={formatNumber(candidateCount(result.findings))} hint="Across all categories below" />
        <StatCard label="Proposals created" icon={ListChecks} value={proposals ? formatNumber(proposals.created.length) : "—"}
          hint={proposals ? "Waiting for your approval" : "Proposals were switched off"} />
      </div>
      <Notices result={result} />
      <div className="grid grid--two-even">
        <Suggestions suggestions={result.suggestions} subtitle={`For ${job.display_path}`} showScanLink={false} />
        {proposals && !result.protected ? <ScanProposals proposals={proposals} dryRun={dryRun} /> : <div />}
      </div>
      <FindingsList findings={result.findings} />
    </div>
  );
}
