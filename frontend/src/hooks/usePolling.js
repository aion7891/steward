// Call an async function every few seconds while `enabled` is true.
import { useEffect, useRef, useState } from "react";

/**
 * Poll a loader on an interval.
 *
 * Args:
 *   loader: async function to call, e.g. getHealth.
 *   intervalMs: time between calls in milliseconds.
 *   enabled: set to false to stop polling (for example when a job has finished).
 *
 * Returns { data, error }.
 */
export function usePolling(loader, intervalMs, enabled = true) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }
    let stopped = false;
    let timer = null;

    async function tick() {
      try {
        const result = await loaderRef.current();
        if (!stopped) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        if (!stopped) {
          setError(err);
        }
      }
      // Schedule the next call only after this one finished (no overlapping requests)
      if (!stopped) {
        timer = setTimeout(tick, intervalMs);
      }
    }

    tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [intervalMs, enabled]);

  return { data, error };
}
