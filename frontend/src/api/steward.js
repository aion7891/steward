// One function per Steward API route. Pages import these instead of calling fetch,
// so every URL and request body lives in this single file.

import { request } from "./client.js";

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

export function sendChat(message) {
  return request("/steward/chat", { method: "POST", body: { message }, timeoutMs: CHAT_TIMEOUT_MS });
}
