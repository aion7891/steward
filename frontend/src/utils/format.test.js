// Unit tests for the formatting helpers and the API error parser (run with `npm test`).
import { describe, expect, it } from "vitest";

import { errorMessage } from "../api/client.js";
import { isCloudModelName } from "../components/layout/AppShell.jsx";
import {
  baseName,
  formatBytes,
  formatDuration,
  formatNumber,
  formatRelativeTime,
  formatShortDate,
  shortPath,
} from "./format.js";

describe("formatBytes", () => {
  it("handles zero, bad input, bytes and larger units", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(-5)).toBe("0 B");
    expect(formatBytes("abc")).toBe("0 B");
    expect(formatBytes(765)).toBe("765 B");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.0 MB");
    expect(formatBytes(1536)).toBe("1.5 KB");
  });
});

describe("formatRelativeTime", () => {
  const now = Date.parse("2026-11-27T12:00:00Z");
  it("describes how long ago something happened", () => {
    expect(formatRelativeTime(null, now)).toBe("never");
    expect(formatRelativeTime("not a date", now)).toBe("unknown");
    expect(formatRelativeTime("2026-11-27T11:59:50Z", now)).toBe("just now");
    expect(formatRelativeTime("2026-11-27T11:55:00Z", now)).toBe("5 min ago");
    expect(formatRelativeTime("2026-11-27T09:00:00Z", now)).toBe("3 h ago");
    expect(formatRelativeTime("2026-11-26T12:00:00Z", now)).toBe("1 day ago");
    expect(formatRelativeTime("2026-11-20T12:00:00Z", now)).toBe("7 days ago");
  });
});

describe("small helpers", () => {
  it("formats numbers, durations, dates and paths", () => {
    expect(formatNumber(1234567)).toBe("1,234,567");
    expect(formatNumber(undefined)).toBe("0");
    expect(formatDuration(8)).toBe("8 s");
    expect(formatDuration(125)).toBe("2 min 5 s");
    expect(formatShortDate("2026-11-27")).toBe("27 Nov");
    expect(shortPath("/Users/me/Documents/Acme/invoice.pdf")).toBe("…/Documents/Acme/invoice.pdf");
    expect(shortPath("/a/b")).toBe("/a/b");
    expect(baseName("/a/b/c.txt")).toBe("c.txt");
  });
});

describe("errorMessage", () => {
  it("reads FastAPI string and validation details", () => {
    expect(errorMessage({ detail: "Folder not found: /x" }, 400)).toBe("Folder not found: /x");
    expect(errorMessage({ detail: [{ msg: "field required" }, { msg: "bad type" }] }, 422)).toBe(
      "field required; bad type",
    );
    expect(errorMessage({}, 404)).toBe("Not found.");
    expect(errorMessage(null, 500)).toBe("Request failed (HTTP 500).");
  });
});

describe("isCloudModelName", () => {
  it("spots Ollama cloud models", () => {
    expect(isCloudModelName("gpt-oss:20b-cloud")).toBe(true);
    expect(isCloudModelName("minimax-m2:cloud")).toBe(true);
    expect(isCloudModelName("gemma4")).toBe(false);
    expect(isCloudModelName(undefined)).toBe(false);
  });
});
