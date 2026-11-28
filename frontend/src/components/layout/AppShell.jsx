// Page frame shared by every route: sidebar, top bar, warnings, then the page itself.
// It polls /steward/health and hands the result to pages via the router's outlet context.
import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";

import { getHealth } from "../../api/steward.js";
import { usePolling } from "../../hooks/usePolling.js";
import { onDataChanged } from "../../utils/dataEvents.js";
import { loadFlag, saveFlag, SIDEBAR_KEY } from "../../utils/layoutPrefs.js";
import Alert from "../ui/Alert.jsx";
import Sidebar from "./Sidebar.jsx";
import TopBar from "./TopBar.jsx";

const HEALTH_INTERVAL_MS = 15000;

/** True for Ollama models that run on Ollama's servers ("...-cloud" or "...:cloud"). */
export function isCloudModelName(name) {
  return /(-|:)cloud$/.test(String(name || ""));
}

function GlobalWarnings({ health, error }) {
  if (error) {
    return (
      <Alert tone="danger" title="Steward API is not reachable">
        Start it with <code>docker compose up -d</code> (or <code>uv run python -m steward.api</code>). This page
        retries automatically.
      </Alert>
    );
  }
  const models = (health && health.models) || {};
  const provider = models.chat_provider;
  // Ollama "cloud" models (e.g. gpt-oss:20b-cloud) also run off this computer
  const ollamaCloud = provider === "ollama" && isCloudModelName(models.chat_model);
  if (provider && (provider !== "ollama" || ollamaCloud)) {
    return (
      <Alert tone="warning" title="Cloud model active">
        Chat questions and document snippets are sent to {ollamaCloud ? "Ollama's cloud" : provider}. Pick a local
        model in Settings to keep everything on this computer.
      </Alert>
    );
  }
  return null;
}

export default function AppShell() {
  // Reload health at once when data changed (for example the "to review" badge after Delete everything)
  const [refreshKey, setRefreshKey] = useState(0);
  useEffect(() => onDataChanged(() => setRefreshKey((n) => n + 1)), []);
  const { data: health, error } = usePolling(getHealth, HEALTH_INTERVAL_MS, true, refreshKey);
  // The sidebar can collapse to icons; remembered for this browser
  const [collapsed, setCollapsed] = useState(() => loadFlag(SIDEBAR_KEY, false));
  return (
    <div className={`app ${collapsed ? "app--collapsed" : ""}`}>
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(saveFlag(SIDEBAR_KEY, !collapsed))} />
      <div className="app__main">
        <TopBar health={health} error={error} />
        <main className="app__content">
          <div className="stack">
            <GlobalWarnings health={health} error={error} />
            <Outlet context={{ health, healthError: error }} />
          </div>
        </main>
      </div>
    </div>
  );
}
