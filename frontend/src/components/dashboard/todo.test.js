// Tests for the messages shown after approving, rejecting or running an action.
import { describe, expect, it } from "vitest";

import { describeResult } from "./TodoList.jsx";

describe("describeResult", () => {
  it("explains dry-run previews, success and rejection", () => {
    expect(describeResult({ status: "dry_run" })).toMatchObject({ tone: "info" });
    expect(describeResult({ status: "dry_run" }).text).toContain("no file was changed");
    expect(describeResult({ status: "done" })).toMatchObject({ tone: "success" });
    expect(describeResult({ status: "rejected" })).toMatchObject({ tone: "info" });
  });

  it("shows the API message for failures and a fallback when there is none", () => {
    expect(describeResult({ status: "blocked", message: "Blocked protected path: /x" })).toEqual({
      tone: "danger",
      text: "Blocked protected path: /x",
    });
    expect(describeResult(null).tone).toBe("danger");
    expect(describeResult({ status: "error" }).text).toBe("The action could not be completed.");
  });
});
