// Chat: a clean conversation in the middle and live workspace cards on the right.
// Answers run on the server, so they keep going while you look at other pages.
import { PanelRightOpen, SquarePen } from "lucide-react";
import { useEffect, useState } from "react";

import { useChat } from "../chat/ChatProvider.jsx";
import ChatHome from "../components/chat/ChatHome.jsx";
import ChatPanel from "../components/chat/ChatPanel.jsx";
import Composer from "../components/chat/Composer.jsx";
import MessageList from "../components/chat/MessageList.jsx";
import { StepList } from "../components/chat/StepTrail.jsx";
import Spinner from "../components/ui/Spinner.jsx";
import { formatDuration } from "../utils/format.js";
import "../styles/chat.css";
import "../styles/chat-panel.css";

const PANEL_KEY = "steward.chat.panel.v1";

// Open by default on wide screens; on narrow ones the panel covers the chat, so it starts closed
function loadPanelOpen() {
  const wide = typeof window !== "undefined" && window.innerWidth > 1100;
  try {
    const saved = window.localStorage.getItem(PANEL_KEY);
    return saved ? saved === "open" && wide : wide;
  } catch {
    return wide;
  }
}

// While Steward works: elapsed time, every step so far, and who is thinking
function Working({ job }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  return (
    <article className="answer answer--working" aria-label="Steward is working">
      <div className="working__head">
        <Spinner /> {job.status === "queued" ? "Waiting for the previous answer…" : "Working…"}
        <span className="faint">{formatDuration((now - job.startedAt) / 1000)}</span>
        {job.failures > 2 && <span className="faint">· reconnecting…</span>}
      </div>
      {job.steps.length > 0 && <StepList steps={job.steps} />}
      {job.thinking && <div className="working__thinking">{job.thinking} is thinking…</div>}
    </article>
  );
}

export default function ChatPage() {
  const { messages, job, busy, conversations, sessionId, ask, decide, retry, newChat } = useChat();
  const [panelOpen, setPanelOpen] = useState(loadPanelOpen);
  const empty = messages.length === 0 && !busy;
  const current = conversations.find((c) => c.id === sessionId);

  function togglePanel(open) {
    setPanelOpen(open);
    try {
      window.localStorage.setItem(PANEL_KEY, open ? "open" : "closed");
    } catch {
      // the choice just isn't remembered
    }
  }

  return (
    <div className={`chat-layout ${panelOpen ? "chat-layout--panel" : ""}`}>
      <section className="chat-main">
        <header className="chat-main__bar">
          <h1 className="chat-main__title">{empty ? "Chat" : (current && current.title) || "Chat"}</h1>
          <div className="row">
            {!empty && (
              <button type="button" className="chat-icon-btn" onClick={newChat} disabled={busy} title="New chat" aria-label="New chat">
                <SquarePen size={16} />
              </button>
            )}
            {!panelOpen && (
              <button type="button" className="chat-icon-btn" onClick={() => togglePanel(true)} title="Show workspace" aria-label="Show workspace">
                <PanelRightOpen size={16} />
              </button>
            )}
          </div>
        </header>
        {empty ? (
          <ChatHome onSend={ask} disabled={busy} />
        ) : (
          <>
            <div className="chat-main__scroll">
              <MessageList messages={messages} onRetry={busy ? null : retry} onDecide={decide} onAsk={ask}
                busy={busy} pendingSlot={busy ? <Working job={job} /> : null} />
            </div>
            <div className="chat-main__dock"><Composer onSend={ask} disabled={busy} /></div>
          </>
        )}
      </section>
      {panelOpen && <ChatPanel messages={messages} job={job} busy={busy} onAsk={ask} onClose={() => togglePanel(false)} />}
    </div>
  );
}
