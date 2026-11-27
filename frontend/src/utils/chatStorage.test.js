// Tests for saving and loading the chat history.
import { describe, expect, it } from "vitest";

import {
  isPausedReply, loadMessages, loadSessionId, MAX_MESSAGES, newSessionId, replyToMessage, saveMessages,
  toSourceChip, trimMessages,
} from "./chatStorage.js";

function fakeStorage(initial = {}) {
  const data = { ...initial };
  return {
    getItem: (key) => (key in data ? data[key] : null),
    setItem: (key, value) => {
      data[key] = value;
    },
    data,
  };
}

const msg = (i, role = "user") => ({ id: String(i), role, content: `message ${i}` });

describe("chat storage", () => {
  it("round-trips messages and keeps only the newest ones", () => {
    const storage = fakeStorage();
    const many = Array.from({ length: MAX_MESSAGES + 5 }, (_, i) => msg(i));
    saveMessages(many, storage);
    const loaded = loadMessages(storage);
    expect(loaded).toHaveLength(MAX_MESSAGES);
    expect(loaded[0].content).toBe("message 5");
  });

  it("returns an empty list for missing, broken or blocked storage", () => {
    expect(loadMessages(fakeStorage())).toEqual([]);
    expect(loadMessages(fakeStorage({ "steward.chat.v1": "{not json" }))).toEqual([]);
    expect(loadMessages(null)).toEqual([]);
    expect(() => saveMessages([msg(1)], null)).not.toThrow();
  });

  it("drops malformed messages", () => {
    const stored = JSON.stringify([msg(1), { role: "robot", content: "x" }, { role: "user" }, null]);
    expect(loadMessages(fakeStorage({ "steward.chat.v1": stored }))).toEqual([msg(1)]);
  });

  it("survives a storage that throws on write", () => {
    const throwing = { getItem: () => null, setItem: () => { throw new Error("quota"); } };
    expect(() => saveMessages([msg(1)], throwing)).not.toThrow();
    expect(trimMessages("not a list")).toEqual([]);
  });
});

describe("replyToMessage", () => {
  it("keeps a normal answer with its sources", () => {
    const m = replyToMessage({ status: "ok", reply: "4,800 USD", sources: ["files/invoice.md"] }, 21);
    expect(m).toMatchObject({ role: "assistant", status: "ok", content: "4,800 USD", sources: ["files/invoice.md"], durationSec: 21 });
  });

  it("turns API errors and paused runs into clear messages", () => {
    expect(replyToMessage({ status: "error", reply: "Model unavailable: timeout" }, 3)).toMatchObject({
      status: "error", content: "Model unavailable: timeout",
    });
    const paused = replyToMessage({ status: "ok", reply: "Team run paused. delete_files requires confirmation", sources: ["x"] }, 9);
    expect(paused.status).toBe("paused");
    expect(paused.content).toContain("needs your approval");
    expect(paused.sources).toEqual([]);
    expect(replyToMessage(null, 1).status).toBe("error");
    expect(replyToMessage({ status: "paused", reply: "anything" }, 2).status).toBe("paused");
  });
});

describe("approvals and sessions", () => {
  it("turns an approval reply into an undecided approval card", () => {
    const steps = [{ tool: "delete_files", summary: "Move 1 file(s) to Steward's recycle bin", names: ["a.tmp"] }];
    const m = replyToMessage({ status: "approval", reply: "needs approval", run_id: "run-1", approvals: steps }, 4);
    expect(m).toMatchObject({ status: "approval", runId: "run-1", approvals: steps, decision: null, sources: [] });
  });

  it("keeps one conversation id until a new one is started", () => {
    const storage = fakeStorage();
    const first = loadSessionId(storage);
    expect(first).toMatch(/^web-/);
    expect(loadSessionId(storage)).toBe(first);
    const second = newSessionId(storage);
    expect(second).not.toBe(first);
    expect(loadSessionId(storage)).toBe(second);
    expect(loadSessionId(null)).toMatch(/^web-/);  // blocked storage still gives an id
  });
});

describe("toSourceChip", () => {
  it("accepts new source objects and old plain-string sources", () => {
    expect(toSourceChip({ kind: "file", label: "invoice.pdf", path: "/d/invoice.pdf" })).toEqual({
      kind: "file", label: "invoice.pdf", path: "/d/invoice.pdf",
    });
    expect(toSourceChip({ kind: "note", label: "acme", path: "projects/acme.md" }).kind).toBe("note");
    expect(toSourceChip("files/invoice-q3-9ea16736.md")).toEqual({
      kind: "note", label: "invoice-q3", path: "files/invoice-q3-9ea16736.md",
    });
    expect(toSourceChip("budget.xlsx")).toEqual({ kind: "file", label: "budget.xlsx", path: "budget.xlsx" });
  });
});

describe("isPausedReply", () => {
  it("detects the agent waiting for an approval", () => {
    expect(isPausedReply("Team run paused. The following require input:")).toBe(true);
    expect(isPausedReply("- OrganizerAgent: delete_files requires confirmation")).toBe(true);
    expect(isPausedReply("The amount due is 4,800 USD.")).toBe(false);
    expect(isPausedReply(undefined)).toBe(false);
  });
});
