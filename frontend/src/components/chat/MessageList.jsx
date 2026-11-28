// The conversation: your questions as soft pills on the right, Steward's answers as plain text
// with the steps it took, scan results, and the files it really looked at.
import { BookOpen, Check, Copy, FileText, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import { toSourceChip } from "../../utils/chatStorage.js";
import { formatDuration } from "../../utils/format.js";
import Button from "../ui/Button.jsx";
import ApprovalCard from "./ApprovalCard.jsx";
import FolderCard from "./FolderCard.jsx";
import StepTrail from "./StepTrail.jsx";

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
    <button type="button" className="chat-icon-btn" onClick={copy} title="Copy answer" aria-label="Copy answer">
      {copied ? <Check size={14} /> : <Copy size={14} />}
    </button>
  );
}

// Files and knowledge notes the AI really looked at while answering (only shown when there are some)
function Sources({ message }) {
  const chips = (message.sources || []).map(toSourceChip);
  if (chips.length === 0) {
    return null;
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

function AssistantMessage({ message, onRetry, onDecide, onAsk, busy }) {
  const tone = TONES[message.status] || "ok";
  return (
    <article className={`answer answer--${tone}`}>
      <StepTrail steps={message.steps} durationSec={message.durationSec} />
      {tone === "approval" ? (
        <ApprovalCard message={message} busy={busy} onDecide={onDecide} />
      ) : (
        <div className="chat-markdown answer__text">
          <ReactMarkdown skipHtml components={SAFE_MARKDOWN}>{message.content}</ReactMarkdown>
        </div>
      )}
      {message.folder && <FolderCard folder={message.folder} onAsk={onAsk} busy={busy} />}
      {tone === "ok" && <Sources message={message} />}
      <div className="answer__meta">
        {!(message.steps && message.steps.length) && message.durationSec ? (
          <span>Answered in {formatDuration(message.durationSec)}</span>
        ) : null}
        {tone === "ok" && <CopyButton text={message.content} />}
        {tone === "error" && onRetry && (
          <Button size="sm" variant="secondary" icon={RotateCcw} onClick={onRetry}>Retry</Button>
        )}
      </div>
    </article>
  );
}

export default function MessageList({ messages, onRetry, onDecide, onAsk, busy, pendingSlot }) {
  const endRef = useRef(null);
  // Keep the newest message in view
  useEffect(() => {
    if (endRef.current && endRef.current.scrollIntoView) {
      endRef.current.scrollIntoView({ block: "end" });
    }
  }, [messages.length, pendingSlot]);

  return (
    <div className="thread" aria-live="polite">
      {messages.map((message, index) => message.role === "user" ? (
        <div key={message.id} className="question"><div className="question__pill">{message.content}</div></div>
      ) : (
        <AssistantMessage key={message.id} message={message} onDecide={onDecide} onAsk={onAsk} busy={busy}
          onRetry={index === messages.length - 1 ? onRetry : null} />
      ))}
      {pendingSlot}
      <div ref={endRef} />
    </div>
  );
}
