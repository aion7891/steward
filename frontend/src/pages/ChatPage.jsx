// Chat: ask questions about your files; answers cite the files or knowledge notes they used.
import { Bot, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { sendChat } from "../api/steward.js";
import Composer from "../components/chat/Composer.jsx";
import MessageList from "../components/chat/MessageList.jsx";
import SuggestedPrompts from "../components/chat/SuggestedPrompts.jsx";
import PageHeader from "../components/layout/PageHeader.jsx";
import Button from "../components/ui/Button.jsx";
import Spinner from "../components/ui/Spinner.jsx";
import { loadMessages, replyToMessage, saveMessages } from "../utils/chatStorage.js";
import { formatDuration } from "../utils/format.js";
import "../styles/chat.css";

function Thinking({ startedAt }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  return (
    <div className="chat-msg chat-msg--assistant">
      <span className="chat-avatar chat-avatar--bot"><Bot size={16} aria-hidden="true" /></span>
      <div className="chat-bubble chat-thinking">
        <Spinner /> Thinking… {formatDuration((now - startedAt) / 1000)}
        <span className="faint"> · local models usually answer in 20–60 s</span>
      </div>
    </div>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState(() => loadMessages());
  const [pendingSince, setPendingSince] = useState(null);

  useEffect(() => {
    saveMessages(messages);
  }, [messages]);

  async function ask(text) {
    const startedAt = Date.now();
    setMessages((list) => [...list, { id: `u-${startedAt}`, role: "user", content: text, createdAt: new Date().toISOString() }]);
    setPendingSince(startedAt);
    let response;
    try {
      response = await sendChat(text);
    } catch (error) {
      response = { status: "error", reply: error.message };
    }
    setMessages((list) => [...list, replyToMessage(response, (Date.now() - startedAt) / 1000)]);
    setPendingSince(null);
  }

  function retry() {
    // Ask the last question again (the failed answer is removed first)
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (lastUser) {
      setMessages((list) => list.slice(0, list.lastIndexOf(lastUser)));
      ask(lastUser.content);
    }
  }

  const busy = pendingSince !== null;
  return (
    <>
      <PageHeader
        title="Chat"
        subtitle="Ask about your files and documents. Everything stays on this computer with a local model."
        actions={messages.length > 0 && (
          <Button icon={Trash2} variant="ghost" disabled={busy} onClick={() => setMessages([])}>Clear chat</Button>
        )}
      />
      <section className="card chat-card">
        {messages.length === 0 && !busy ? (
          <SuggestedPrompts onPick={ask} />
        ) : (
          <MessageList messages={messages} onRetry={busy ? null : retry}
            pendingSlot={busy ? <Thinking startedAt={pendingSince} /> : null} />
        )}
        <Composer onSend={ask} disabled={busy} />
      </section>
    </>
  );
}
