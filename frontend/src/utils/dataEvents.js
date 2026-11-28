// A tiny page-wide signal: "Steward's data changed" (for example after Delete everything), so parts
// that poll slowly, like the "to review" badge in the top bar, can refresh at once.
const EVENT = "steward:data-changed";

/** Tell the rest of the page that Steward's data changed. */
export function announceDataChanged() {
  window.dispatchEvent(new Event(EVENT));
}

/** Call handler whenever the data changed; returns a function that stops listening. */
export function onDataChanged(handler) {
  window.addEventListener(EVENT, handler);
  return () => window.removeEventListener(EVENT, handler);
}
