// Plain helpers for Settings → Data & cleanup (kept separate so they are easy to test).

export const CONFIRM_WORD = "DELETE";

// What can be cleared; the recycle bin has no backup (it would be the recycle bin itself)
export const TARGETS = [
  { key: "chats", title: "Chats", noun: "chat", backup: true,
    explain: "Your conversations, and the AI's memory of them." },
  { key: "knowledge", title: "Knowledge notes", noun: "note", backup: true,
    explain: "Everything Steward learned about your files, folders, projects and topics (OKF notes)." },
  { key: "topics", title: "Topics only", noun: "topic note", backup: true,
    explain: "Only the topic notes; the other knowledge notes stay." },
  { key: "recycle", title: "Recycle bin", noun: "item", backup: false,
    explain: "Files Steward moved to its recycle bin. Emptying it deletes them for good, and Undo stops working for them." },
];

/** "3 chats", "1 note": a count with the right plural. */
export function plural(count, noun) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

/** How many there are of one target, from the /steward/data summary. */
export function countOf(summary, key) {
  return (summary && summary[key] && summary[key].count) || 0;
}

/** The question shown before clearing ("clear" keeps a backup, "hard" deletes for good). */
export function confirmText(target, mode, count) {
  const what = plural(count, target.noun);
  if (mode === "clear") {
    return `Clear ${what}? A backup is kept, so you can restore them below.`;
  }
  return `Delete ${what} for good? There is no backup and no undo.`;
}

/** A permanent delete needs the word DELETE typed exactly; a clear with backup does not. */
export function canConfirm(mode, typed) {
  return mode === "clear" || String(typed || "").trim() === CONFIRM_WORD;
}
