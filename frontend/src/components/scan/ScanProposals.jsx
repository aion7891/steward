// The proposals created (or already waiting) for this folder, approvable right here.
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

import { listActions } from "../../api/steward.js";
import { useApi } from "../../hooks/useApi.js";
import TodoList from "../dashboard/TodoList.jsx";
import Alert from "../ui/Alert.jsx";

export default function ScanProposals({ proposals, dryRun }) {
  const ids = new Set([...(proposals.created || []), ...(proposals.already_open || [])].map((p) => p.id));
  const { data, error, reload } = useApi(() => listActions("proposed", 200), []);
  const open = ((data && data.actions) || []).filter((action) => ids.has(action.id));
  const created = (proposals.created || []).length;
  const alreadyOpen = (proposals.already_open || []).length;
  return (
    <div className="stack">
      <Alert tone="info" action={<Link to="/dashboard" className="btn btn--sm btn--secondary">Dashboard <ArrowRight size={14} /></Link>}>
        {created} new proposal(s) created{alreadyOpen > 0 ? `, ${alreadyOpen} were already waiting` : ""}. Approve them
        here or later from the Dashboard.
      </Alert>
      {error && <Alert tone="danger" error={error} />}
      {ids.size > 0 && (
        <TodoList title="Proposals for this folder" todo={open} waiting={[]} dryRun={dryRun} onChanged={reload} />
      )}
    </div>
  );
}
