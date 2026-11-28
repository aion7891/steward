// Small per-browser layout choices (sidebar collapsed, To-do folded). Browser storage can be missing
// or blocked (private windows), so every read and write falls back quietly to the default.
export const SIDEBAR_KEY = "steward.sidebar.collapsed.v1";
export const TODO_KEY = "steward.dashboard.todo.open.v1";

/** Read a remembered true/false choice, or `fallback` when there is none. */
export function loadFlag(key, fallback) {
  try {
    const value = window.localStorage.getItem(key);
    return value === null ? fallback : value === "1";
  } catch {
    return fallback;
  }
}

/** Remember a true/false choice for this browser (ignored when storage is unavailable). */
export function saveFlag(key, value) {
  try {
    window.localStorage.setItem(key, value ? "1" : "0");
  } catch {
    // storage blocked: the choice simply isn't remembered
  }
  return value;
}
