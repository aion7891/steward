// Formatting helpers that turn raw API values into friendly text.

const UNITS = ["B", "KB", "MB", "GB", "TB"];

/** 0 -> "0 B", 765 -> "765 B", 3145728 -> "3.0 MB". */
export function formatBytes(bytes) {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value <= 0) {
    return "0 B";
  }
  const exponent = Math.min(Math.floor(Math.log(value) / Math.log(1024)), UNITS.length - 1);
  const scaled = value / 1024 ** exponent;
  return exponent === 0 ? `${Math.round(scaled)} B` : `${scaled.toFixed(1)} ${UNITS[exponent]}`;
}

/** 1234567 -> "1,234,567". */
export function formatNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("en-US") : "0";
}

/** ISO time -> "just now", "5 min ago", "3 h ago", "2 days ago", or "never". */
export function formatRelativeTime(iso, now = Date.now()) {
  if (!iso) {
    return "never";
  }
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) {
    return "unknown";
  }
  const seconds = Math.max(0, Math.round((now - then) / 1000));
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  const days = Math.round(seconds / 86400);
  return days === 1 ? "1 day ago" : `${days} days ago`;
}

/** ISO time -> "27 Nov 2026, 14:05" in the browser's local time. */
export function formatDateTime(iso) {
  if (!iso) {
    return "—";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return date.toLocaleString("en-GB", {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

/** "2026-11-27" -> "27 Nov" (chart axis labels). */
export function formatShortDate(day) {
  const date = new Date(`${day}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) {
    return String(day || "");
  }
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

/** Seconds -> "8 s" or "2 min 5 s". */
export function formatDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  if (total < 60) {
    return `${total} s`;
  }
  return `${Math.floor(total / 60)} min ${total % 60} s`;
}

/** Long paths -> ".../Documents/Acme/invoice.pdf" (keeps the last `keep` parts). */
export function shortPath(path, keep = 3) {
  const text = String(path || "");
  const parts = text.split("/").filter(Boolean);
  if (parts.length <= keep) {
    return text;
  }
  return `…/${parts.slice(-keep).join("/")}`;
}

/** The last part of a path: "/a/b/c.txt" -> "c.txt". */
export function baseName(path) {
  const parts = String(path || "").split("/").filter(Boolean);
  return parts.length ? parts[parts.length - 1] : String(path || "");
}
