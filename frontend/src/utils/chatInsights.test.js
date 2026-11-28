import { describe, expect, it } from "vitest";

import { activitySteps, helpersOf, latestFolder, pendingApprovals, stepSummary, suggestionPrompt } from "./chatInsights.js";

const STEPS = [
  { kind: "handoff", agent: "Scanner", status: "done" },
  { kind: "tool", agent: "Scanner", status: "done" },
  { kind: "handoff", agent: "Organizer", status: "done" },
  { kind: "tool", agent: "Organizer", status: "error" },
];

describe("step summaries", () => {
  it("names each helper once and counts tool steps and problems", () => {
    expect(helpersOf([...STEPS, { agent: "Steward" }])).toEqual(["Scanner", "Organizer"]);
    expect(stepSummary(STEPS, 9.4)).toBe("Worked 9 s · Scanner, Organizer · 2 steps · 1 problem");
    expect(stepSummary([STEPS[1]], 125)).toBe("Worked 2 min · Scanner · 1 step");
    expect(stepSummary([], null)).toBe("0 steps");
    expect(stepSummary([STEPS[2]], 7)).toBe("Worked 7 s · Organizer");  // a hand-over only: no "0 steps"
  });
});

describe("conversation helpers", () => {
  const messages = [
    { role: "assistant", folder: { name: "old" }, steps: [STEPS[1]] },
    { role: "assistant", status: "approval", decision: null },
    { role: "assistant", status: "approval", decision: "approved" },
    { role: "assistant", folder: { name: "docs" } },
  ];

  it("finds the newest folder card and the open approvals", () => {
    expect(latestFolder(messages).name).toBe("docs");
    expect(latestFolder([])).toBeNull();
    expect(pendingApprovals(messages)).toHaveLength(1);
  });

  it("shows the running answer's steps first, else the last answer's", () => {
    expect(activitySteps(messages, { steps: STEPS })).toHaveLength(4);
    expect(activitySteps(messages, null)).toEqual([STEPS[1]]);
    expect(activitySteps([], null)).toEqual([]);
  });
});

describe("suggestionPrompt", () => {
  const folder = { path: "/Users/you/Downloads/docs" };

  it("names the exact files so the AI can act on them", () => {
    expect(suggestionPrompt({ kind: "archive_stale", paths: ["/a/old.csv", "/a/b.txt"] }, folder))
      .toBe("Archive these old files: /a/old.csv, /a/b.txt");
    expect(suggestionPrompt({ kind: "deduplicate", paths: ["/a/copy.txt"] }, folder)).toContain("duplicate copies");
    expect(suggestionPrompt({ kind: "group_folder", paths: ["/a/mixed"] }, folder)).toBe("Organize the folder /a/mixed by file type");
    expect(suggestionPrompt({ kind: "other", title: "Do it", paths: [] }, folder)).toBe("Do it in /Users/you/Downloads/docs");
  });
});
