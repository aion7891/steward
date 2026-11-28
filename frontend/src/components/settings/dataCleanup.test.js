import { describe, expect, it } from "vitest";

import { canConfirm, confirmText, countOf, plural, TARGETS } from "./dataCleanup.js";

const chats = TARGETS.find((t) => t.key === "chats");

describe("data cleanup helpers", () => {
  it("counts with the right plural", () => {
    expect(plural(1, "chat")).toBe("1 chat");
    expect(plural(3, "topic note")).toBe("3 topic notes");
    expect(countOf({ chats: { count: 4 } }, "chats")).toBe(4);
    expect(countOf(null, "topics")).toBe(0);
  });

  it("asks differently for a clear and a permanent delete", () => {
    expect(confirmText(chats, "clear", 2)).toBe("Clear 2 chats? A backup is kept, so you can restore them below.");
    expect(confirmText(chats, "hard", 1)).toBe("Delete 1 chat for good? There is no backup and no undo.");
  });

  it("needs DELETE typed exactly for a permanent delete", () => {
    expect(canConfirm("clear", "")).toBe(true);
    expect(canConfirm("hard", "delete")).toBe(false);
    expect(canConfirm("hard", " DELETE ")).toBe(true);
    expect(TARGETS.find((t) => t.key === "recycle").backup).toBe(false);
  });
});
