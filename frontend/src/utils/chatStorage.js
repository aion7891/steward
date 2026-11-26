// Keep the chat history in the browser so it survives a page refresh.
// Storage can be unavailable (private windows, blocked site data), so every access is guarded.

const STORAGE_KEY = "steward.chat.v1";
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

/** True when the agent stopped to wait for an approval that chat can't give yet (review issue #2). */
export function isPausedReply(text) {
  return /run paused|requires confirmation/i.test(String(text || ""));
}

const PAUSED_TEXT =
  "**This action needs your approval**, which isn't supported from chat yet. " +
  "Use **Scan a folder** to create proposals, then approve them in the **Dashboard** to-do list.";

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
  if (response.status === "paused" || isPausedReply(reply)) {
    return { ...base, status: "paused", content: PAUSED_TEXT, sources: [] };
  }
  return { ...base, status: "ok", content: reply || "_(empty answer)_", sources: response.sources || [] };
}
