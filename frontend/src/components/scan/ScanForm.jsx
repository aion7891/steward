// The "which folder?" form: path box, quick-pick folders, options and the Scan button.
import { Folder, FolderSearch } from "lucide-react";
import { useState } from "react";

import { getFolderRoots, startFolderScan } from "../../api/steward.js";
import { useApi } from "../../hooks/useApi.js";
import Alert from "../ui/Alert.jsx";
import Button from "../ui/Button.jsx";
import Card from "../ui/Card.jsx";

function QuickPicks({ roots, onPick }) {
  const available = roots.filter((root) => root.available);
  if (available.length === 0) {
    return null;
  }
  return (
    <div className="quick-picks">
      <span className="faint">Quick pick:</span>
      {available.map((root) => (
        <button key={root.path} type="button" className="chip" title={root.host_path} onClick={() => onPick(root.host_path)}>
          <Folder size={13} aria-hidden="true" /> {root.label}
        </button>
      ))}
    </div>
  );
}

export default function ScanForm({ onStarted }) {
  const { data: rootsData } = useApi(getFolderRoots, []);
  const [path, setPath] = useState("");
  const [createProposals, setCreateProposals] = useState(true);
  const [indexForChat, setIndexForChat] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const roots = (rootsData && rootsData.roots) || [];
  const inDocker = Boolean(rootsData && rootsData.in_docker);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!path.trim()) {
      setError(new Error("Please enter a folder path."));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const response = await startFolderScan({ path: path.trim(), createProposals, indexForChat });
      onStarted(response.job);
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card title="Choose a folder" subtitle="Steward reads the folder (it never changes files during a scan).">
      <form className="stack" onSubmit={handleSubmit}>
        <div>
          <label className="label" htmlFor="folder-path">Folder path</label>
          <input id="folder-path" className="input mono" placeholder="/Users/you/Documents/Projects"
            value={path} onChange={(e) => setPath(e.target.value)} autoComplete="off" spellCheck="false" />
          <QuickPicks roots={roots} onPick={setPath} />
        </div>
        {inDocker && (
          <p className="faint">
            Steward runs in Docker and can scan folders inside: {roots.map((r) => r.host_path).join(", ")}.
          </p>
        )}
        <label className="checkbox">
          <input type="checkbox" checked={createProposals} onChange={(e) => setCreateProposals(e.target.checked)} />
          <span>
            <strong>Create cleanup proposals</strong>
            <span className="faint"> — duplicates and temp files go to your to-do list; nothing changes until you approve.</span>
          </span>
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={indexForChat} onChange={(e) => setIndexForChat(e.target.checked)} />
          <span>
            <strong>Also make documents searchable in Chat</strong>
            <span className="faint"> — slower: each document is read and embedded with the local model.</span>
          </span>
        </label>
        {error && <Alert tone={error.status === 409 ? "warning" : "danger"} error={error} />}
        <div>
          <Button type="submit" variant="primary" icon={FolderSearch} loading={submitting}>
            Scan folder
          </Button>
        </div>
      </form>
    </Card>
  );
}
