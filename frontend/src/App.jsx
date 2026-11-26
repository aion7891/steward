// URL routes: every page renders inside the shared AppShell frame.
// Pages are loaded on demand, so the chart library is only downloaded for the dashboard.
import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import AppShell from "./components/layout/AppShell.jsx";
import { Loading } from "./components/ui/Spinner.jsx";

const DashboardPage = lazy(() => import("./pages/DashboardPage.jsx"));
const ScanPage = lazy(() => import("./pages/ScanPage.jsx"));
const ChatPage = lazy(() => import("./pages/ChatPage.jsx"));

function Page({ children }) {
  return <Suspense fallback={<Loading label="Loading page…" />}>{children}</Suspense>;
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Page><DashboardPage /></Page>} />
        <Route path="/scan" element={<Page><ScanPage /></Page>} />
        <Route path="/chat" element={<Page><ChatPage /></Page>} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}
