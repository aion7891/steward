// Left navigation: brand, the pages, recent chats, and a small footer. It can collapse to a narrow
// strip of icons (names show on hover); the choice is remembered per browser (see AppShell).
import { FileBarChart, FolderSearch, LayoutDashboard, MessageSquare, PanelLeftClose, PanelLeftOpen, Settings } from "lucide-react";
import { NavLink } from "react-router-dom";

import { useChat } from "../../chat/ChatProvider.jsx";
import RecentChats from "./RecentChats.jsx";

const LINKS = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/scan", label: "Scan a folder", icon: FolderSearch },
  { to: "/chat", label: "Chat", icon: MessageSquare },
  { to: "/reports", label: "Reports", icon: FileBarChart },
  { to: "/settings", label: "Settings", icon: Settings },
];

export default function Sidebar({ collapsed = false, onToggle }) {
  const chat = useChat();
  // The dot next to Chat: this chat or another one is still answering in the background
  const chatBusy = Boolean(chat && (chat.busy || chat.conversations.some((c) => c.running)));
  return (
    <aside className={`sidebar ${collapsed ? "sidebar--collapsed" : ""}`}>
      <div className="sidebar__brand">
        <img className="sidebar__logo" src="/favicon.svg" alt="" title="Steward" />
        <div className="sidebar__brand-text">
          <div className="sidebar__name">Steward</div>
          <div className="sidebar__tagline">Local file assistant</div>
        </div>
        {onToggle && (
          <button type="button" className="sidebar__toggle" onClick={onToggle} aria-expanded={!collapsed}
            title={collapsed ? "Expand the sidebar" : "Collapse the sidebar"}
            aria-label={collapsed ? "Expand the sidebar" : "Collapse the sidebar"}>
            {collapsed ? <PanelLeftOpen size={18} aria-hidden="true" /> : <PanelLeftClose size={18} aria-hidden="true" />}
          </button>
        )}
      </div>
      <nav className="sidebar__nav" aria-label="Main">
        {LINKS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            title={collapsed ? label : undefined}
            aria-label={label}
            className={({ isActive }) => `sidebar__link ${isActive ? "sidebar__link--active" : ""}`}
          >
            <Icon size={18} aria-hidden="true" />
            <span className="sidebar__label">{label}</span>
            {to === "/chat" && chatBusy && <span className="sidebar__dot" title="Steward is answering" aria-label="answering" />}
          </NavLink>
        ))}
      </nav>
      <RecentChats compact={collapsed} />
      <div className="sidebar__footer">Runs on this computer. Your files stay here.</div>
    </aside>
  );
}
