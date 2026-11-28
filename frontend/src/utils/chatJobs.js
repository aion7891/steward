// Helpers for chat jobs: turn server answers and saved conversations into chat messages.
import { replyToMessage } from "./chatStorage.js";

export const POLL_MS = 1000;

/** The live state of a running job, as kept by the chat provider. */
export function jobState(job) {
  const started = Date.parse(job && job.created_at);
  return {
    id: job.id,
    startedAt: Number.isNaN(started) ? Date.now() : started,
    status: job.status,
    steps: job.steps || [],
    thinking: job.thinking || null,
    failures: 0,
  };
}

/** Turn a finished job's result into an assistant message (with its steps and duration). */
export function jobResultToMessage(result) {
  const data = result || { status: "error", reply: "Steward could not answer." };
  return { ...replyToMessage(data, data.duration_sec), steps: data.steps || [], folder: data.folder || null };
}

/** Turn messages saved on the server into chat messages (stable ids, original times). */
export function serverMessagesToChat(messages) {
  return (messages || []).map((m) => {
    const base = { id: `s-${m.id}`, createdAt: m.created_at };
    if (m.role === "user") {
      return { ...base, role: "user", content: m.content };
    }
    const data = m.data || {};
    const message = jobResultToMessage({ reply: m.content, ...data });
    return { ...message, ...base, decision: data.decision || message.decision || null };
  });
}

/** The message shown when a running answer was lost (for example after a restart). */
export function interruptedMessage(detail) {
  return {
    id: `a-${Date.now()}`,
    role: "assistant",
    status: "error",
    content: detail || "This answer was interrupted. Please ask again.",
    sources: [],
    createdAt: new Date().toISOString(),
  };
}

/** One line for a step: "Scanner · Scanning ~/Desktop/docs (3/4)", or just "Handing over to Scanner". */
export function stepLine(step) {
  if (step.kind === "handoff") {
    return step.title;
  }
  const progress = step.progress ? ` (${step.progress.done}/${step.progress.total})` : "";
  return `${step.agent} · ${step.title}${progress}`;
}
