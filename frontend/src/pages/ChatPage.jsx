// Chat: ask questions about your files; answers run on the server and show their steps live.
import { Bot, Check, Plus, X } from "lucide-react";
import { useEffect, useState } from "react";

import { useChat } from "../chat/ChatProvider.jsx";
import Composer from "../components/chat/Composer.jsx";
import MessageList from "../components/chat/MessageList.jsx";
import SuggestedPrompts from "../components/chat/SuggestedPrompts.jsx";
import PageHeader from "../components/layout/PageHeader.jsx";
import Button from "../components/ui/Button.jsx";
import Spinner from "../components/ui/Spinner.jsx";
import { stepLine } from "../utils/chatJobs.js";
import { formatDuration } from "../utils/format.js";
import "../styles/chat.css";

function StepIcon({ status }) {
  if (status === "done") return <Check size={13} className="chat-step__icon chat-step__icon--done" aria-label="done" />;
  if (status === "error") return <X size={13} className="chat-step__icon chat-step__icon--error" aria-label="failed" />;
  return <Spinner />;
}

// "Thinking…" plus every step so far: which helper works on what, and the outcome
function Working({ job }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const waiting = job.status === "queued";
  return (
    <div className="chat-msg chat-msg--assistant">
      <span className="chat-avatar chat-avatar--bot"><Bot size={16} aria-hidden="true" /></span>
      <div className="chat-bubble chat-thinking">
        <div><Spinner /> {waiting ? "Waiting for the previous answer…" : "Working…"} {formatDuration((now - job.startedAt) / 1000)}
          {job.failures > 2 && <span className="faint"> · reconnecting…</span>}</div>
        {job.steps.length > 0 && (
          <ol className="chat-steps">
            {job.steps.map((step) => (
              <li key={step.id} className={`chat-step chat-step--${step.status}`}>
                <StepIcon status={step.status} /> <span>{stepLine(step)}</span>
                {step.detail && <div className="chat-step__detail faint">{step.detail}</div>}
              </li>
            ))}
          </ol>
        )}
        {job.thinking && <div className="faint chat-steps__thinking">{job.thinking} is thinking…</div>}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const { messages, job, busy, ask, decide, retry, newChat } = useChat();
  return (
    <>
      <PageHeader
        title="Chat"
        subtitle="Ask about your files and documents. Everything stays on this computer with a local model."
        actions={messages.length > 0 && (
          <Button icon={Plus} variant="ghost" disabled={busy} onClick={newChat}>New chat</Button>
        )}
      />
      <section className="card chat-card">
        {messages.length === 0 && !busy ? (
          <SuggestedPrompts onPick={ask} />
        ) : (
          <MessageList messages={messages} onRetry={busy ? null : retry} onDecide={decide} busy={busy}
            pendingSlot={busy ? <Working job={job} /> : null} />
        )}
        <Composer onSend={ask} disabled={busy} />
      </section>
    </>
  );
}
