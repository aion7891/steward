// Keep the chat history in the browser so it survives a page refresh.
// Storage can be unavailable (private windows, blocked site data), so every access is guarded.

const STORAGE_KEY = "steward.chat.v1";
const SESSION_KEY = "steward.chat.session.v1";
export const MAX_MESSAGES = 50;

/** Return localStorage, or null when the browser blocks it. */
function defaultStorage() {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}

/** Keep only the newest `max` messages. */
export function trimMessages(messages, max = MAX_MESSAGES) {
  return Array.isArray(messages) ? messages.slice(-max) : [];
}

/** Load saved messages; returns [] when nothing is saved or the data is broken. */
export function loadMessages(storage = defaultStorage()) {
  if (!storage) {
    return [];
  }
  try {
    const parsed = JSON.parse(storage.getItem(STORAGE_KEY) || "[]");
    // Only keep well-formed messages, so old or hand-edited data can't break the page
    return trimMessages(parsed.filter((m) => m && typeof m.content === "string" && ["user", "assistant"].includes(m.role)));
  } catch {
    return [];
  }
}

/** Save messages (newest MAX_MESSAGES only). Silently does nothing if storage is blocked. */
export function saveMessages(messages, storage = defaultStorage()) {
  if (!storage) {
    return;
  }
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(trimMessages(messages)));
  } catch {
    // Quota exceeded or blocked: the chat still works, it just won't be remembered
  }
}

/** Start a new conversation id (also used after "Clear chat"). */
export function newSessionId(storage = defaultStorage()) {
  const random = typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const id = `web-${random}`;
  try {
    if (storage) storage.setItem(SESSION_KEY, id);
  } catch {
    // Blocked storage: the id still works for this page view
  }
  return id;
}

/** Remember which conversation is open (used when opening a saved chat). */
export function saveSessionId(id, storage = defaultStorage()) {
  try {
    if (storage) storage.setItem(SESSION_KEY, id);
  } catch {
    // Blocked storage: the id still works for this page view
  }
  return id;
}

/** The current conversation id, created on first use. */
export function loadSessionId(storage = defaultStorage()) {
  try {
    const saved = storage && storage.getItem(SESSION_KEY);
    if (saved) return saved;
  } catch {
    // fall through to a fresh id
  }
  return newSessionId(storage);
}

/**
 * Turn one source from the API into {kind, label, path}.
 * Older saved chats stored sources as plain strings, so those are still accepted.
 */
export function toSourceChip(source) {
  if (source && typeof source === "object") {
    return { kind: source.kind === "note" ? "note" : "file", label: source.label || source.path, path: source.path || "" };
  }
  const text = String(source || "");
  const isNote = text.endsWith(".md");
  const name = text.split("/").pop();
  return { kind: isNote ? "note" : "file", label: isNote ? name.slice(0, -3).replace(/-[0-9a-f]{8}$/, "") : name, path: text };
}

/** True when the agent stopped to wait for an approval that chat can't give yet (review issue #2). */
export function isPausedReply(text) {
  return /run paused|requires confirmation/i.test(String(text || ""));
}

// Fallback for older API versions that only said "paused" without an approval card
const PAUSED_TEXT =
  "**This action needs your approval.** Ask again to get an approval card here, " +
  "or create proposals with **Scan a folder** and approve them in the **Dashboard** to-do list.";

/**
 * Turn a /steward/chat response into a message for the conversation.
 *
 * Args:
 *   response: {status, reply, sources} from the API.
 *   durationSec: how long the answer took.
 */
export function replyToMessage(response, durationSec) {
  const base = { id: `a-${Date.now()}`, role: "assistant", durationSec, createdAt: new Date().toISOString() };
  const reply = String((response && response.reply) || "");
  if (!response || response.status === "error") {
    return { ...base, status: "error", content: reply || "Steward could not answer.", sources: [] };
  }
  if (response.status === "approval") {
    // Shown as an approval card; `decision` is filled in once the user clicks
    return { ...base, status: "approval", content: reply, sources: [], runId: response.run_id,
      approvals: response.approvals || [], decision: null };
  }
  if (response.status === "paused" || isPausedReply(reply)) {
    return { ...base, status: "paused", content: PAUSED_TEXT, sources: [] };
  }
  return { ...base, status: "ok", content: reply || "_(empty answer)_", sources: response.sources || [] };
}
