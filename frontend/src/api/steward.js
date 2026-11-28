// One function per Steward API route. Pages import these instead of calling fetch,
// so every URL and request body lives in this single file.

import { apiUrl, request } from "./client.js";

// Chat answers from a local model can take 20-60 s, so chat gets a long timeout.
const CHAT_TIMEOUT_MS = 180000;

export function getHealth() {
  return request("/steward/health", { timeoutMs: 10000 });
}

export function getDashboard(days = 14) {
  // Send the browser's offset from UTC so "today" and the chart days match the user's clock
  const tzOffset = new Date().getTimezoneOffset();
  return request(`/steward/dashboard?days=${encodeURIComponent(days)}&tz_offset=${tzOffset}`);
}

export function getFolderRoots() {
  return request("/steward/folders/roots");
}

export function startFolderScan({ path, createProposals = true, indexForChat = false }) {
  return request("/steward/folders/scan", {
    method: "POST",
    body: { path, create_proposals: createProposals, index_for_chat: indexForChat },
  });
}

export function getFolderScan(jobId) {
  return request(`/steward/folders/scan/${encodeURIComponent(jobId)}`);
}

export function listFolderScans(limit = 10) {
  return request(`/steward/folders/scans?limit=${encodeURIComponent(limit)}`);
}

/** Approve a proposed action and run it (dry-run setting from config unless given). */
export function approveAction(actionId, dryRun) {
  const body = { execute: true };
  if (dryRun !== undefined) {
    body.dry_run = dryRun;
  }
  return request(`/steward/actions/${actionId}/approve`, { method: "POST", body });
}

export function rejectAction(actionId, reason = "Rejected in the web UI") {
  return request(`/steward/actions/${actionId}/reject`, { method: "POST", body: { reason } });
}

/** Run an action that is already approved (for example one approved during dry-run). */
export function executeAction(actionId, dryRun) {
  const body = dryRun === undefined ? {} : { dry_run: dryRun };
  return request(`/steward/actions/${actionId}/execute`, { method: "POST", body });
}

export function undoAction(actionId) {
  return request(`/steward/actions/${actionId}/undo`, { method: "POST" });
}

export function listActions(status, limit = 50) {
  const query = status ? `?status=${encodeURIComponent(status)}&limit=${limit}` : `?limit=${limit}`;
  return request(`/steward/actions${query}`);
}

/** Ask a question inside one conversation (sessionId keeps the AI's memory per chat). */
export function sendChat(message, sessionId) {
  return request("/steward/chat", {
    method: "POST",
    body: { message, session_id: sessionId },
    timeoutMs: CHAT_TIMEOUT_MS,
  });
}

/** Approve or reject the file changes a paused chat answer is waiting for. */
export function decideChat(runId, approve) {
  return request(`/steward/chat/${encodeURIComponent(runId)}/decision`, {
    method: "POST",
    body: { approve: Boolean(approve) },
    timeoutMs: CHAT_TIMEOUT_MS,
  });
}

/** Ask a question as a background job; poll it with getChatJob (survives leaving the page). */
export function startChatJob(message, sessionId) {
  return request("/steward/chat/jobs", { method: "POST", body: { message, session_id: sessionId } });
}

/** Approve or reject an approval card as a background job. */
export function decideChatJob(runId, approve, sessionId) {
  return request("/steward/chat/decisions", {
    method: "POST",
    body: { run_id: runId, approve: Boolean(approve), session_id: sessionId },
  });
}

/** One chat job: its status, live steps and (when done) the answer. */
export function getChatJob(jobId) {
  return request(`/steward/chat/jobs/${encodeURIComponent(jobId)}`, { timeoutMs: 10000 });
}

/** Stop a running chat answer; changes already made stay (and can be undone). */
export function stopChatJob(jobId) {
  return request(`/steward/chat/jobs/${encodeURIComponent(jobId)}/stop`, { method: "POST", timeoutMs: 10000 });
}

/** Saved conversations, newest first. */
export function listConversations(limit = 30) {
  return request(`/steward/chat/conversations?limit=${limit}`);
}

/** One saved conversation's messages, plus its running job (if any). */
export function getConversation(sessionId) {
  return request(`/steward/chat/conversations/${encodeURIComponent(sessionId)}`);
}

/** Fresh stats and suggestions for a folder (after files were changed). */
export function getFolderCard(path) {
  return request(`/steward/chat/folder?path=${encodeURIComponent(path)}`);
}

export function deleteConversation(sessionId) {
  return request(`/steward/chat/conversations/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
}

export function getSettings() {
  return request("/steward/settings");
}

/** Save some settings, e.g. { dry_run: false } or { watched_folders: [...] }. */
export function saveSettings(changes) {
  return request("/steward/settings", { method: "PUT", body: changes, timeoutMs: 60000 });
}

/** Installed Ollama models and whether each can use tools. */
export function getModels() {
  return request("/steward/models");
}

/** Reports newest first; each has formats.markdown / formats.html with an id. */
export function getReportLibrary() {
  return request("/steward/reports/library");
}

export function generateReport(period = "weekly") {
  return request("/steward/reports/generate", { method: "POST", body: { period }, timeoutMs: 120000 });
}

export function getReport(reportId) {
  return request(`/steward/reports/${encodeURIComponent(reportId)}`);
}

/** Link that downloads one report file. */
export function reportDownloadUrl(reportId) {
  return apiUrl(`/steward/reports/${encodeURIComponent(reportId)}/download`);
}
