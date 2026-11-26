// The last few completed actions, each with an Undo button.
import { History, Undo2 } from "lucide-react";
import { useState } from "react";

import { listActions, undoAction } from "../../api/steward.js";
import { useApi } from "../../hooks/useApi.js";
import Alert from "../ui/Alert.jsx";
import Button from "../ui/Button.jsx";
import Card from "../ui/Card.jsx";
import EmptyState from "../ui/EmptyState.jsx";
import ActionItem from "./ActionItem.jsx";

export default function RecentActions({ refreshKey, onChanged }) {
  const { data, error, reload } = useApi(() => listActions("done", 5), [refreshKey]);
  const [busyId, setBusyId] = useState(null);
  const [notice, setNotice] = useState(null);
  const actions = (data && data.actions) || [];

  async function undo(actionId) {
    setBusyId(actionId);
    try {
      const result = await undoAction(actionId);
      const ok = result.status === "undone";
      setNotice({ tone: ok ? "success" : "danger", text: ok ? "Restored to its original place." : result.message });
      reload();
      onChanged();
    } catch (err) {
      setNotice({ tone: "danger", text: err.message });
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Card title="Recently completed" subtitle="Everything Steward changes can be undone.">
      <div className="stack">
        {error && <Alert tone="danger" error={error} />}
        {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}
        {actions.length === 0 ? (
          <EmptyState icon={History} title="Nothing changed yet" />
        ) : (
          <ul className="action-list">
            {actions.map((action) => (
              <ActionItem key={action.id} action={action}>
                <Button size="sm" variant="secondary" icon={Undo2} loading={busyId === action.id} onClick={() => undo(action.id)}>
                  Undo
                </Button>
              </ActionItem>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
