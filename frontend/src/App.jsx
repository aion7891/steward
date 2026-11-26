// URL routes: every page renders inside the shared AppShell frame.
import { Navigate, Route, Routes } from "react-router-dom";

import AppShell from "./components/layout/AppShell.jsx";
import ChatPage from "./pages/ChatPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import ScanPage from "./pages/ScanPage.jsx";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/scan" element={<ScanPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}
