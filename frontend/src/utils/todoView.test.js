import { describe, expect, it } from "vitest";

import { todoSummary, visibleTodo } from "./todoView.js";

const items = Array.from({ length: 340 }, (_, i) => ({ id: i }));

describe("To-do card helpers", () => {
  it("shows the first 10, or all when asked", () => {
    expect(visibleTodo(items, false)).toHaveLength(10);
    expect(visibleTodo(items, true)).toHaveLength(340);
    expect(visibleTodo(items.slice(0, 3), false)).toHaveLength(3);
    expect(visibleTodo(items, false, null)).toHaveLength(340);  // no limit (Scan page)
    expect(visibleTodo(undefined, false)).toEqual([]);
  });

  it("summarises the folded card", () => {
    expect(todoSummary(items, [])).toBe("Folded · click Show to see the list");
    expect(todoSummary(items, [{ id: 1 }, { id: 2 }])).toBe("Folded · 2 approved, waiting to run");
    expect(todoSummary([], [])).toBe("Nothing waiting for your decision");
  });
});
