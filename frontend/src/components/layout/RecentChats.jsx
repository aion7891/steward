// "Recent chats" in the sidebar: start a new chat, reopen or delete a saved one. Chats keep
// answering in the background; a pulsing dot shows which ones are still working.
import { MessageCircle, SquarePen, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useChat } from "../../chat/ChatProvider.jsx";

const SHOWN = 8;

export default function RecentChats({ compact = false }) {
  const chat = useChat();
  const navigate = useNavigate();
  const [error, setError] = useState(null);
  if (!chat) {
    return null;
  }

  function open(id) {
    if (id !== chat.sessionId) chat.openChat(id);
    navigate("/chat");
  }

  function startNew() {
    chat.newChat();
    navigate("/chat");
  }

  async function remove(item) {
    if (!window.confirm(`Delete the chat "${item.title}"?\n\nIts messages and the AI's memory of it are deleted for good.`)) {
      return;
    }
    try {
      setError(null);
      await chat.deleteChat(item.id);
    } catch (err) {
      setError(err.message);  // for example: still answering
    }
  }

  // Collapsed sidebar: only a "New chat" icon
  if (compact) {
    return (
      <div className="recent-chats recent-chats--compact">
        <button type="button" className="recent-chats__new" onClick={startNew} title="New chat" aria-label="New chat">
          <SquarePen size={18} aria-hidden="true" />
        </button>
      </div>
    );
  }

  return (
    <div className="recent-chats">
      <button type="button" className="recent-chats__new" onClick={startNew}>
        <SquarePen size={15} aria-hidden="true" /> New chat
      </button>
      {chat.conversations.length > 0 && <div className="recent-chats__label">Recent chats</div>}
      {error && <div className="recent-chats__error" role="alert">{error}</div>}
      <ul className="recent-chats__list">
        {chat.conversations.slice(0, SHOWN).map((item) => {
          const working = item.running || (item.id === chat.sessionId && chat.busy);
          return (
            <li key={item.id} className="recent-chats__row">
              <button type="button" title={item.title} onClick={() => open(item.id)}
                className={`recent-chats__item ${item.id === chat.sessionId ? "recent-chats__item--active" : ""}`}>
                <MessageCircle size={13} aria-hidden="true" />
                <span className="recent-chats__title">{item.title}</span>
                {working && <span className="sidebar__dot" title="Still working" aria-label="Still working" />}
              </button>
              <button type="button" className="recent-chats__delete" onClick={() => remove(item)} disabled={working}
                title={working ? "Wait for the answer (or press Stop) to delete this chat" : "Delete chat"}
                aria-label={`Delete chat ${item.title}`}>
                <Trash2 size={13} aria-hidden="true" />
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
