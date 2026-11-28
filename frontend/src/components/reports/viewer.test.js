// Tests for choosing which copy of a report to show.
import { describe, expect, it } from "vitest";

import { pickFormat } from "./ReportViewer.jsx";

describe("pickFormat", () => {
  it("prefers HTML, falls back to Markdown, and handles missing files", () => {
    const both = { formats: { markdown: { id: 1, available: true }, html: { id: 2, available: true } } };
    expect(pickFormat(both)).toEqual({ format: "html", id: 2 });
    const htmlGone = { formats: { markdown: { id: 1, available: true }, html: { id: 2, available: false } } };
    expect(pickFormat(htmlGone)).toEqual({ format: "markdown", id: 1 });
    expect(pickFormat({ formats: { markdown: { id: 1, available: false } } })).toBeNull();
    expect(pickFormat(null)).toBeNull();
  });
});
