// Load data once (and on demand) with loading and error state.
import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Call an async function when the component mounts (and when deps change).
 *
 * Args:
 *   loader: async function returning the data, e.g. () => getDashboard(14).
 *   deps: values that should trigger a reload when they change.
 *
 * Returns { data, error, loading, reload }.
 */
export function useApi(loader, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const latest = useRef(0);

  const reload = useCallback(async () => {
    // Only the newest request may update state (avoids races when deps change fast)
    const requestId = latest.current + 1;
    latest.current = requestId;
    setLoading(true);
    try {
      const result = await loader();
      if (latest.current === requestId) {
        setData(result);
        setError(null);
      }
    } catch (err) {
      if (latest.current === requestId) {
        setError(err);
      }
    } finally {
      if (latest.current === requestId) {
        setLoading(false);
      }
    }
    // `deps` is chosen by the caller on purpose: reload only when those values change
  }, deps);

  useEffect(() => {
    reload();
  }, [reload]);

  return { data, error, loading, reload };
}
