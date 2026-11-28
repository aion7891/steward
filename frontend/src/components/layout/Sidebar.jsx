// Left navigation: brand, the pages, and a small footer.
import { FileBarChart, FolderSearch, LayoutDashboard, MessageSquare, Settings } from "lucide-react";
import { NavLink } from "react-router-dom";

import { useChat } from "../../chat/ChatProvider.jsx";

const LINKS = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/scan", label: "Scan a folder", icon: FolderSearch },
  { to: "/chat", label: "Chat", icon: MessageSquare },
  { to: "/reports", label: "Reports", icon: FileBarChart },
  { to: "/settings", label: "Settings", icon: Settings },
];

export default function Sidebar() {
  const chat = useChat();
  const chatBusy = Boolean(chat && chat.busy);
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <img className="sidebar__logo" src="/favicon.svg" alt="" />
        <div>
          <div className="sidebar__name">Steward</div>
          <div className="sidebar__tagline">Local file assistant</div>
        </div>
      </div>
      <nav className="sidebar__nav" aria-label="Main">
        {LINKS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => `sidebar__link ${isActive ? "sidebar__link--active" : ""}`}
          >
            <Icon size={18} aria-hidden="true" />
            <span className="sidebar__label">{label}</span>
            {to === "/chat" && chatBusy && <span className="sidebar__dot" title="Steward is answering" aria-label="answering" />}
          </NavLink>
        ))}
      </nav>
      <div className="sidebar__footer">Runs on this computer. Your files stay here.</div>
    </aside>
  );
}
