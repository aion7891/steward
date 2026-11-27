// Tests for the scan step indicator logic.
import { describe, expect, it } from "vitest";

import { stepsFor } from "./ScanProgress.jsx";

const states = (job) => stepsFor(job).map((step) => `${step.key}:${step.state}`);

describe("stepsFor", () => {
  it("shows only the steps the user asked for", () => {
    const job = { status: "running", step: "scanning", options: { create_proposals: false, index_for_chat: false } };
    expect(stepsFor(job).map((s) => s.key)).toEqual(["scanning", "analyzing", "done"]);
  });

  it("marks earlier steps done and the current step active", () => {
    const job = { status: "running", step: "analyzing", options: { create_proposals: true, index_for_chat: true } };
    expect(states(job)).toEqual([
      "scanning:done", "indexing:done", "analyzing:active", "proposing:waiting", "done:waiting",
    ]);
  });

  it("marks everything done when the job has finished", () => {
    const job = { status: "done", step: "done", options: { create_proposals: true } };
    expect(stepsFor(job).every((s) => s.state === "done")).toBe(true);
  });

  it("keeps all steps waiting while the job is queued", () => {
    const job = { status: "queued", step: "queued", options: {} };
    expect(stepsFor(job).every((s) => s.state === "waiting")).toBe(true);
  });
});
