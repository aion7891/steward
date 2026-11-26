// Dashboard page (placeholder): filled in Phase 4 with stats, chart and to-do list.
import { LayoutDashboard } from "lucide-react";

import PageHeader from "../components/layout/PageHeader.jsx";
import Card from "../components/ui/Card.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";

export default function DashboardPage() {
  return (
    <>
      <PageHeader title="Dashboard" subtitle="Today's scans and what needs your attention." />
      <Card>
        <EmptyState icon={LayoutDashboard} title="Coming in the next phase">
          Daily scan stats, the to-do list and suggestions will appear here.
        </EmptyState>
      </Card>
    </>
  );
}
