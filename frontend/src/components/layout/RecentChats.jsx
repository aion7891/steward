// "Recent chats" in the sidebar: start a new chat or reopen a saved one.
import { MessageCircle, SquarePen } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useChat } from "../../chat/ChatProvider.jsx";

const SHOWN = 8;

export default function RecentChats() {
  const chat = useChat();
  const navigate = useNavigate();
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

  return (
    <div className="recent-chats">
      <button type="button" className="recent-chats__new" onClick={startNew} disabled={chat.busy}>
        <SquarePen size={15} aria-hidden="true" /> New chat
      </button>
      {chat.conversations.length > 0 && <div className="recent-chats__label">Recent chats</div>}
      <ul className="recent-chats__list">
        {chat.conversations.slice(0, SHOWN).map((item) => (
          <li key={item.id}>
            <button type="button" title={item.title} disabled={chat.busy && item.id !== chat.sessionId}
              className={`recent-chats__item ${item.id === chat.sessionId ? "recent-chats__item--active" : ""}`}
              onClick={() => open(item.id)}>
              <MessageCircle size={13} aria-hidden="true" />
              <span className="recent-chats__title">{item.title}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
