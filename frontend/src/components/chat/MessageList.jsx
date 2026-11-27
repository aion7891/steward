// The conversation: user questions on the right, Steward's answers (as Markdown) on the left.
import { BookOpen, Bot, Check, Copy, FileText, RotateCcw, User } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import { toSourceChip } from "../../utils/chatStorage.js";
import { formatDuration } from "../../utils/format.js";
import Button from "../ui/Button.jsx";
import ApprovalCard from "./ApprovalCard.jsx";

// Answers may quote document text. Links and images are shown as plain text so a
// document can never smuggle a clickable link or a remote image into the page.
const SAFE_MARKDOWN = {
  a: ({ children }) => <span className="chat-link">{children}</span>,
  img: ({ alt }) => <span>{alt ? `[image: ${alt}]` : "[image]"}</span>,
};

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }
  return (
    <button type="button" className="chat-icon-btn" onClick={copy} title="Copy answer">
      {copied ? <Check size={14} /> : <Copy size={14} />}
    </button>
  );
}

// Files and knowledge notes the AI really looked at while answering (or an honest "none")
function Sources({ message, tone }) {
  const chips = (message.sources || []).map(toSourceChip);
  if (tone !== "ok") {
    return null;
  }
  if (chips.length === 0) {
    return <div className="chat-sources faint">Answered without looking up your files.</div>;
  }
  return (
    <div className="chat-sources">
      <span className="faint">Looked at:</span>
      {chips.map((chip) => {
        const Icon = chip.kind === "note" ? BookOpen : FileText;
        return (
          <span key={`${chip.kind}-${chip.path}`} className={`chat-source chat-source--${chip.kind}`}
            title={`${chip.kind === "note" ? "Knowledge note" : "File"}: ${chip.path}`}>
            <Icon size={12} aria-hidden="true" /> {chip.label}
          </span>
        );
      })}
    </div>
  );
}

const TONES = { error: "error", paused: "paused", approval: "approval" };

function AssistantMessage({ message, onRetry, onDecide, busy }) {
  const tone = TONES[message.status] || "ok";
  return (
    <div className={`chat-msg chat-msg--assistant chat-msg--${tone}`}>
      <span className="chat-avatar chat-avatar--bot"><Bot size={16} aria-hidden="true" /></span>
      <div className="chat-bubble">
        {tone === "approval" ? (
          <ApprovalCard message={message} busy={busy} onDecide={onDecide} />
        ) : (
          <div className="chat-markdown">
            <ReactMarkdown skipHtml components={SAFE_MARKDOWN}>{message.content}</ReactMarkdown>
          </div>
        )}
        <Sources message={message} tone={tone} />
        <div className="chat-meta">
          {message.durationSec ? <span>Answered in {formatDuration(message.durationSec)}</span> : null}
          {tone === "ok" && <CopyButton text={message.content} />}
          {tone === "error" && onRetry && (
            <Button size="sm" variant="secondary" icon={RotateCcw} onClick={onRetry}>Retry</Button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function MessageList({ messages, onRetry, onDecide, busy, pendingSlot }) {
  const endRef = useRef(null);
  // Keep the newest message in view
  useEffect(() => {
    if (endRef.current && endRef.current.scrollIntoView) {
      endRef.current.scrollIntoView({ block: "end" });
    }
  }, [messages.length, pendingSlot]);

  return (
    <div className="chat-messages" aria-live="polite">
      {messages.map((message, index) => message.role === "user" ? (
        <div key={message.id} className="chat-msg chat-msg--user">
          <div className="chat-bubble">{message.content}</div>
          <span className="chat-avatar"><User size={16} aria-hidden="true" /></span>
        </div>
      ) : (
        <AssistantMessage key={message.id} message={message} onDecide={onDecide} busy={busy}
          onRetry={index === messages.length - 1 ? onRetry : null} />
      ))}
      {pendingSlot}
      <div ref={endRef} />
    </div>
  );
}
