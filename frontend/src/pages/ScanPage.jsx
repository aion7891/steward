// Scan-a-folder page (placeholder): filled in Phase 5 with the form, progress and results.
import { FolderSearch } from "lucide-react";

import PageHeader from "../components/layout/PageHeader.jsx";
import Card from "../components/ui/Card.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";

export default function ScanPage() {
  return (
    <>
      <PageHeader title="Scan a folder" subtitle="Pick a folder; Steward scans it and suggests what to do." />
      <Card>
        <EmptyState icon={FolderSearch} title="Coming soon">
          Enter a folder path, watch the scan progress and review the suggestions.
        </EmptyState>
      </Card>
    </>
  );
}
