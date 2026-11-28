// Plain helpers for Settings → Data & cleanup (kept separate so they are easy to test).

export const CONFIRM_WORD = "DELETE";

// What can be cleared. Items without a backup are always deleted for good (type DELETE): the recycle
// bin (its backup would be the recycle bin itself) and records Steward rebuilds by scanning or generating.
export const TARGETS = [
  { key: "chats", title: "Chats", noun: "chat", backup: true,
    explain: "Your conversations, and the AI's memory of them." },
  { key: "knowledge", title: "Knowledge notes", noun: "note", backup: true,
    explain: "Everything Steward learned about your files, folders, projects and topics, including the Work habits on the Dashboard (OKF notes)." },
  { key: "topics", title: "Topics only", noun: "topic note", backup: true,
    explain: "Only the topic notes; the other knowledge notes stay." },
  { key: "index", title: "Scan history & file index", noun: "indexed file", backup: false, hardLabel: "Delete for good",
    explain: "What Steward knows about your files and its past scans: the Dashboard numbers, chart, suggestions and recent scans. The next scan builds it again." },
  { key: "actions", title: "To-do & action history", noun: "action", backup: false, hardLabel: "Delete for good",
    explain: "Suggestions waiting for your decision and the list of past changes. Undo stops working for past changes; files already in the recycle bin or archives stay there." },
  { key: "search", title: "Document search index", noun: "searchable document", backup: false, hardLabel: "Delete for good",
    explain: "Lets the chat answer questions about what your documents say. Scan a folder with \u201cAlso make documents searchable in Chat\u201d to build it again." },
  { key: "reports", title: "Reports", noun: "report", backup: false, hardLabel: "Delete for good",
    explain: "Generated reports and their files. New ones are still made every Sunday or with Generate now." },
  { key: "recycle", title: "Recycle bin", noun: "item", backup: false, hardLabel: "Empty for good",
    explain: "Files Steward moved to its recycle bin. Emptying it deletes them for good, and Undo stops working for them." },
];

/** "3 chats", "1 note": a count with the right plural. */
export function plural(count, noun) {
  return `${Number(count).toLocaleString("en-US")} ${noun}${count === 1 ? "" : "s"}`;
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
