// Chat page (placeholder): filled in Phase 6 with the conversation view.
import { MessageSquare } from "lucide-react";

import PageHeader from "../components/layout/PageHeader.jsx";
import Card from "../components/ui/Card.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";

export default function ChatPage() {
  return (
    <>
      <PageHeader title="Chat" subtitle="Ask about your files and documents." />
      <Card>
        <EmptyState icon={MessageSquare} title="Coming soon">
          Ask questions like “How much is due on the Acme invoice?” and see the source files.
        </EmptyState>
      </Card>
    </>
  );
}
