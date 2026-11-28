// Settings: dry-run, AI model and watched folders. Saved to data/settings.override.yaml by the API.
import { CalendarClock } from "lucide-react";
import { useEffect, useState } from "react";

import { getModels, getSettings, saveSettings } from "../api/steward.js";
import { useChat } from "../chat/ChatProvider.jsx";
import PageHeader from "../components/layout/PageHeader.jsx";
import DataSettings from "../components/settings/DataSettings.jsx";
import FolderSettings from "../components/settings/FolderSettings.jsx";
import ModelSettings from "../components/settings/ModelSettings.jsx";
import SafetySettings from "../components/settings/SafetySettings.jsx";
import Alert from "../components/ui/Alert.jsx";
import Card from "../components/ui/Card.jsx";
import { Loading } from "../components/ui/Spinner.jsx";
import { useApi } from "../hooks/useApi.js";
import "../styles/settings.css";

function Schedule({ scheduler }) {
  const s = scheduler || {};
  return (
    <Card title="Schedule" subtitle="Background jobs (change in config.yaml)">
      <ul className="schedule-list">
        <li><CalendarClock size={14} /> Scan watched folders every <strong>{s.scan_interval_minutes} min</strong></li>
        <li><CalendarClock size={14} /> Look for cleanup suggestions every <strong>{s.cleanup_interval_hours} h</strong></li>
        <li><CalendarClock size={14} /> Weekly report every <strong>{s.report_day}</strong> at 09:00</li>
      </ul>
    </Card>
  );
}

export default function SettingsPage() {
  const { data, error, loading } = useApi(getSettings, []);
  const { data: models } = useApi(getModels, []);
  const chat = useChat();
  const [settings, setSettings] = useState(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState(null);
  useEffect(() => setSettings(data), [data]);

  // One save handler for every section; the API validates and explains any problem
  async function save(changes, successText) {
    setSaving(true);
    try {
      setSettings(await saveSettings(changes));
      setNotice({ tone: "success", text: successText });
    } catch (err) {
      setNotice({ tone: "danger", text: err.message });
    } finally {
      setSaving(false);
    }
  }

  const header = <PageHeader title="Settings" subtitle="Changes apply right away and are kept after a restart." />;
  if (!settings) {
    return <>{header}{error ? <Alert tone="danger" error={error} /> : loading && <Loading label="Loading settings…" />}</>;
  }
  return (
    <>
      {header}
      {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}
      <div className="grid settings-grid">
        <div className="stack">
          <SafetySettings settings={settings} saving={saving} onSave={save} />
          <Schedule scheduler={settings.scheduler} />
        </div>
        <div className="stack">
          <ModelSettings settings={settings} models={models} saving={saving} onSave={save} />
          <FolderSettings settings={settings} saving={saving} onSave={save} />
        </div>
      </div>
      {/* After chats are cleared or restored, the chat page starts a fresh conversation */}
      <DataSettings onChatsChanged={chat.newChat} />
      <p className="faint">
        Saved in <code>{settings.override_file}</code>. Your config.yaml is never rewritten; values in .env still win.
      </p>
    </>
  );
}
