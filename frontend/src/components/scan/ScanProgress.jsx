// Live progress of a folder scan: step indicator, progress bar and elapsed time.
import { Check } from "lucide-react";
import { useEffect, useState } from "react";

import { formatDuration } from "../../utils/format.js";
import Card from "../ui/Card.jsx";
import Spinner from "../ui/Spinner.jsx";

const STEP_LABELS = {
  scanning: "Scanning files",
  indexing: "Indexing for chat",
  analyzing: "Finding duplicates & clutter",
  proposing: "Creating proposals",
  done: "Done",
};

/**
 * Return the list of steps for a job with each step's state: "done", "active" or "waiting".
 * Optional steps (indexing, proposing) only appear when the user ticked them.
 */
export function stepsFor(job) {
  const options = job.options || {};
  const keys = ["scanning"];
  if (options.index_for_chat) keys.push("indexing");
  keys.push("analyzing");
  if (options.create_proposals) keys.push("proposing");
  keys.push("done");
  const currentIndex = job.status === "done" ? keys.length - 1 : keys.indexOf(job.step);
  return keys.map((key, index) => {
    let state = "waiting";
    if (job.status === "done" || index < currentIndex) state = "done";
    else if (index === currentIndex) state = "active";
    return { key, label: STEP_LABELS[key], state };
  });
}

function useElapsedSeconds(startIso, running) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);
  return startIso ? Math.max(0, (now - new Date(startIso).getTime()) / 1000) : 0;
}

export default function ScanProgress({ job }) {
  const running = job.status === "queued" || job.status === "running";
  const elapsed = useElapsedSeconds(job.started_at || job.created_at, running);
  return (
    <Card title={`Scanning ${job.display_path}`} subtitle={running ? `Running for ${formatDuration(elapsed)}` : "Finished"}
      actions={running ? <Spinner /> : null}>
      <div className="progress" role="progressbar" aria-valuenow={job.progress} aria-valuemin={0} aria-valuemax={100}>
        <div className="progress__fill" style={{ width: `${Math.max(4, job.progress || 0)}%` }} />
      </div>
      <ol className="steps">
        {stepsFor(job).map((step) => (
          <li key={step.key} className={`steps__item steps__item--${step.state}`}>
            <span className="steps__dot">{step.state === "done" ? <Check size={12} aria-hidden="true" /> : null}</span>
            {step.label}
          </li>
        ))}
      </ol>
    </Card>
  );
}
