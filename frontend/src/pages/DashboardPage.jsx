// Dashboard: today's numbers, daily scan chart, the to-do list and suggestions.
import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import { getDashboard } from "../api/steward.js";
import { CategoryBreakdown, Patterns, RecentScans } from "../components/dashboard/Breakdown.jsx";
import DailyChart from "../components/dashboard/DailyChart.jsx";
import RecentActions from "../components/dashboard/RecentActions.jsx";
import StatusCards from "../components/dashboard/StatusCards.jsx";
import Suggestions from "../components/dashboard/Suggestions.jsx";
import TodoList from "../components/dashboard/TodoList.jsx";
import PageHeader from "../components/layout/PageHeader.jsx";
import Alert from "../components/ui/Alert.jsx";
import Button from "../components/ui/Button.jsx";
import { Loading } from "../components/ui/Spinner.jsx";
import { useApi } from "../hooks/useApi.js";
import "../styles/dashboard.css";

const DAY_OPTIONS = [7, 14, 30];
const AUTO_REFRESH_MS = 60000;

function DaysSwitch({ days, onChange }) {
  return (
    <div className="segmented" role="group" aria-label="Days of history">
      {DAY_OPTIONS.map((option) => (
        <button
          key={option}
          type="button"
          className={`segmented__item ${option === days ? "segmented__item--active" : ""}`}
          onClick={() => onChange(option)}
        >
          {option} days
        </button>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const [days, setDays] = useState(14);
  const [refreshKey, setRefreshKey] = useState(0);
  const { data, error, loading, reload } = useApi(() => getDashboard(days), [days]);

  // Keep the numbers fresh while the page is open
  useEffect(() => {
    const timer = setInterval(reload, AUTO_REFRESH_MS);
    return () => clearInterval(timer);
  }, [reload]);

  function handleChanged() {
    reload();
    setRefreshKey((key) => key + 1);
  }

  const header = (
    <PageHeader
      title="Dashboard"
      subtitle="Today's scans and what needs your attention."
      actions={
        <>
          <DaysSwitch days={days} onChange={setDays} />
          <Button icon={RefreshCw} loading={loading && Boolean(data)} onClick={handleChanged}>
            Refresh
          </Button>
        </>
      }
    />
  );

  if (!data) {
    return (
      <>
        {header}
        {error ? <Alert tone="danger" title="Could not load the dashboard" error={error} /> : <Loading label="Loading dashboard…" />}
      </>
    );
  }

  const dryRun = Boolean(data.system && data.system.dry_run);
  return (
    <>
      {header}
      {error && <Alert tone="warning" title="Showing the last loaded numbers" error={error} />}
      <StatusCards status={data.status} />
      <div className="grid dash-grid--main">
        <TodoList todo={data.todo} waiting={data.approved_waiting} dryRun={dryRun} onChanged={handleChanged} />
        <Suggestions suggestions={data.suggestions} />
      </div>
      <div className="grid grid--two">
        <DailyChart daily={data.daily} />
        <CategoryBreakdown categories={data.categories} />
      </div>
      <div className="grid grid--two">
        <RecentScans scans={data.recent_scans} />
        <div className="stack">
          <RecentActions refreshKey={refreshKey} onChanged={handleChanged} />
          <Patterns patterns={data.patterns} />
        </div>
      </div>
    </>
  );
}
