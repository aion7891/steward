// Small fetch wrapper used by every API call.
// It adds timeouts and turns FastAPI errors into one readable message,
// so pages can simply show `error.message` to the user.

const DEFAULT_TIMEOUT_MS = 30000;
const API_BASE = import.meta.env?.VITE_API_BASE || "";

/** Full URL for an API path, for plain links such as file downloads. */
export function apiUrl(path) {
  return `${API_BASE}${path}`;
}

/** An error with a user-friendly message and the HTTP status (0 = network problem). */
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/**
 * Turn a FastAPI error body into one sentence.
 * FastAPI sends {"detail": "text"} or, for validation errors, {"detail": [{msg: "..."}]}.
 */
export function errorMessage(body, status) {
  const detail = body && body.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((item) => item.msg || String(item)).join("; ");
  }
  if (status === 404) {
    return "Not found.";
  }
  return `Request failed (HTTP ${status}).`;
}

async function readJson(response) {
  const text = await response.text();
  if (!text) {
    return {};
  }
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text.slice(0, 200) };
  }
}

/**
 * Send one request to the Steward API and return the parsed JSON.
 *
 * Args:
 *   path: API path such as "/steward/dashboard".
 *   options.method: HTTP method (default GET).
 *   options.body: object sent as JSON.
 *   options.timeoutMs: give up after this many milliseconds.
 */
export async function request(path, { method = "GET", body, timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const data = await readJson(response);
    if (!response.ok) {
      throw new ApiError(errorMessage(data, response.status), response.status);
    }
    return data;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    if (error.name === "AbortError") {
      throw new ApiError("Steward took too long to answer. It may still be busy; try again shortly.", 0);
    }
    throw new ApiError("Cannot reach the Steward API. Is it running?", 0);
  } finally {
    clearTimeout(timer);
  }
}
