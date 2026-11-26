// "What needs to be done": proposed actions (approve / reject) and approved ones waiting to run.
import { Check, CheckCircle2, Play, X } from "lucide-react";
import { useState } from "react";

import { approveAction, executeAction, rejectAction } from "../../api/steward.js";
import Alert from "../ui/Alert.jsx";
import Badge from "../ui/Badge.jsx";
import Button from "../ui/Button.jsx";
import Card from "../ui/Card.jsx";
import EmptyState from "../ui/EmptyState.jsx";
import ActionItem from "./ActionItem.jsx";

const CONFIRM_REAL = "This changes files on disk (deleted files go to Steward's recycle bin and can be undone). Continue?";

/** Turn an action result from the API into a message for the user. */
export function describeResult(result) {
  const status = result && result.status;
  if (status === "dry_run") {
    return { tone: "info", text: "Preview only: dry-run is on, so no file was changed. It now waits under “Approved, waiting to run”." };
  }
  if (status === "done") {
    return { tone: "success", text: "Done. You can undo it from “Recently completed”." };
  }
  if (status === "rejected") {
    return { tone: "info", text: "Rejected. Nothing on disk was changed." };
  }
  return { tone: "danger", text: (result && result.message) || "The action could not be completed." };
}

export default function TodoList({ todo, waiting, dryRun, onChanged }) {
  const [busyId, setBusyId] = useState(null);
  const [notice, setNotice] = useState(null);

  async function run(actionId, apiCall, confirmText) {
    if (confirmText && !window.confirm(confirmText)) {
      return;
    }
    setBusyId(actionId);
    try {
      setNotice(describeResult(await apiCall(actionId)));
      onChanged();
    } catch (error) {
      setNotice({ tone: "danger", text: error.message });
    } finally {
      setBusyId(null);
    }
  }

  const subtitle = dryRun
    ? "Dry-run is ON: approving previews an action without changing files."
    : "Dry-run is OFF: approving changes files right away.";
  return (
    <Card title="To-do" subtitle={subtitle} actions={<Badge tone={todo.length ? "warning" : "success"}>{todo.length} open</Badge>}>
      <div className="stack">
        {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}
        {todo.length === 0 && waiting.length === 0 ? (
          <EmptyState icon={CheckCircle2} title="All caught up">
            New suggestions appear here after a scan.
          </EmptyState>
        ) : (
          <ul className="action-list">
            {todo.map((action) => (
              <ActionItem key={action.id} action={action}>
                <Button size="sm" variant="primary" icon={Check} loading={busyId === action.id}
                  onClick={() => run(action.id, (id) => approveAction(id), dryRun ? null : CONFIRM_REAL)}>
                  Approve
                </Button>
                <Button size="sm" variant="ghost" icon={X} disabled={busyId === action.id}
                  onClick={() => run(action.id, (id) => rejectAction(id))}>
                  Reject
                </Button>
              </ActionItem>
            ))}
          </ul>
        )}
        {waiting.length > 0 && <WaitingList waiting={waiting} dryRun={dryRun} busyId={busyId} run={run} />}
      </div>
    </Card>
  );
}

function WaitingList({ waiting, dryRun, busyId, run }) {
  return (
    <div>
      <h4 className="section-label">Approved, waiting to run ({waiting.length})</h4>
      <ul className="action-list">
        {waiting.map((action) => (
          <ActionItem key={action.id} action={action}>
            <Button size="sm" variant="secondary" icon={Play} loading={busyId === action.id} disabled={dryRun}
              title={dryRun ? "Turn dry-run off to run approved actions" : "Run this action now"}
              onClick={() => run(action.id, (id) => executeAction(id), CONFIRM_REAL)}>
              Run now
            </Button>
          </ActionItem>
        ))}
      </ul>
    </div>
  );
}
