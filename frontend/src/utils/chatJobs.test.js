import { describe, expect, it } from "vitest";

import {
  interruptedMessage, jobResultToMessage, jobState, markTypedDecision, serverMessagesToChat, stepLine,
} from "./chatJobs.js";

const STEPS = [{ id: 1, agent: "Scanner", title: "Scanning /Users/you/Desktop/docs", status: "done", progress: null }];

describe("jobState", () => {
  it("keeps the live parts of a job and its start time", () => {
    const state = jobState({ id: "j1", status: "running", created_at: "2026-11-28T10:00:00Z", steps: STEPS, thinking: "Scanner" });
    expect(state).toMatchObject({ id: "j1", status: "running", thinking: "Scanner", failures: 0 });
    expect(state.startedAt).toBe(Date.parse("2026-11-28T10:00:00Z"));
    expect(jobState({ id: "j2" }).steps).toEqual([]);
  });
});

describe("jobResultToMessage", () => {
  it("adds steps and the duration to the answer", () => {
    const message = jobResultToMessage({ status: "ok", reply: "Found 4 files", sources: [], steps: STEPS, duration_sec: 9.5 });
    expect(message).toMatchObject({ role: "assistant", status: "ok", content: "Found 4 files", durationSec: 9.5 });
    expect(message.steps).toHaveLength(1);
    expect(message.folder).toBeNull();
    expect(jobResultToMessage({ status: "ok", reply: "x", folder: { name: "docs" } }).folder.name).toBe("docs");
  });

  it("keeps approval cards", () => {
    const message = jobResultToMessage({ status: "approval", reply: "needs approval", run_id: "r1", approvals: [{ summary: "x" }] });
    expect(message).toMatchObject({ status: "approval", runId: "r1", decision: null });
  });
});

describe("serverMessagesToChat", () => {
  it("restores questions, answers and decisions saved on the server", () => {
    const saved = [
      { id: 1, role: "user", content: "delete it", data: {}, created_at: "t1" },
      { id: 2, role: "assistant", content: "needs approval", created_at: "t2",
        data: { status: "approval", run_id: "r1", approvals: [], decision: "approved", steps: STEPS } },
    ];
    const [question, answer] = serverMessagesToChat(saved);
    expect(question).toEqual({ id: "s-1", createdAt: "t1", role: "user", content: "delete it" });
    expect(answer).toMatchObject({ id: "s-2", status: "approval", runId: "r1", decision: "approved" });
    expect(answer.steps).toHaveLength(1);
    expect(serverMessagesToChat(undefined)).toEqual([]);
  });
});

describe("small helpers", () => {
  it("describes a step and an interrupted answer", () => {
    expect(stepLine({ ...STEPS[0], progress: { done: 3, total: 4 } })).toBe("Scanner · Scanning /Users/you/Desktop/docs (3/4)");
    expect(stepLine({ kind: "handoff", agent: "Chat", title: "Handing over to Chat" })).toBe("Handing over to Chat");
    expect(interruptedMessage().status).toBe("error");
  });
});

describe("stopping and typed decisions", () => {
  it("shows a stopped answer as stopped, and remembers a stop request", () => {
    expect(jobResultToMessage({ status: "stopped", reply: "Stopped. Steward did not finish this answer." }))
      .toMatchObject({ status: "stopped", content: "Stopped. Steward did not finish this answer." });
    expect(jobState({ id: "j1", stopping: true }).stopping).toBe(true);
    expect(jobState({ id: "j2" }).stopping).toBe(false);
  });

  it("marks the card a typed 'no' rejected, and nothing else", () => {
    const list = [{ id: "a", runId: "r1", decision: null }, { id: "b", runId: "r2", decision: null }];
    const marked = markTypedDecision(list, { decided_run_id: "r1" });
    expect(marked.map((m) => m.decision)).toEqual(["rejected", null]);
    expect(markTypedDecision(list, { status: "ok" })).toBe(list);
  });
});
