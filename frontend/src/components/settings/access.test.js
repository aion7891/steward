import { describe, expect, it } from "vitest";

import { accessBadge, readOnlySwitches } from "./access.js";

describe("accessBadge", () => {
  it("shows writable folders in green", () => {
    expect(accessBadge({ available: true, writable: true })).toMatchObject({ tone: "success", label: "writable" });
  });

  it("explains how to make a read-only Docker folder writable", () => {
    const badge = accessBadge({ available: true, writable: false, access_var: "STEWARD_DESKTOP_ACCESS" });
    expect(badge.label).toBe("read-only");
    expect(badge.title).toContain("STEWARD_DESKTOP_ACCESS=rw");
  });

  it("shows nothing for missing folders", () => {
    expect(accessBadge({ available: false, writable: false })).toBeNull();
    expect(accessBadge(undefined)).toBeNull();
  });
});

describe("readOnlySwitches", () => {
  it("lists each switch once, only for folders that exist and are read-only", () => {
    const folders = [
      { available: true, writable: false, access_var: "STEWARD_DESKTOP_ACCESS" },
      { available: true, writable: false, access_var: "STEWARD_DESKTOP_ACCESS" },
      { available: true, writable: true, access_var: "STEWARD_DOCUMENTS_ACCESS" },
      { available: false, writable: false, access_var: "STEWARD_EXTRA_ACCESS" },
      { available: true, writable: false, access_var: null },
    ];
    expect(readOnlySwitches(folders)).toEqual(["STEWARD_DESKTOP_ACCESS"]);
    expect(readOnlySwitches(null)).toEqual([]);
  });
});
