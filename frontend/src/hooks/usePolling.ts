import { useEffect, useRef, useState } from "react";

/**
 * Polls `fetcher` every `intervalMs` while `enabled`. Mirrors the Streamlit
 * app's st.fragment(run_every=...) auto-refresh (Fase 9 ND-06) -- polling
 * chosen deliberately over SSE for the first pass (see ARCHITECTURE.md);
 * never blocks the UI thread the way the pre-Fase-9 time.sleep() did.
 */
export function usePolling<T>(fetcher: () => Promise<T>, intervalMs: number, enabled = true) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  // Lets a caller force an immediate refresh right after an action it knows
  // changed the server state, instead of waiting up to `intervalMs` for the
  // next scheduled tick to notice (see ReaderHomePage's launch button).
  const tickRef = useRef<() => Promise<void>>(async () => {});

  useEffect(() => {
    if (!enabled) {
      setIsLoading(false);
      return;
    }
    let cancelled = false;

    async function tick() {
      try {
        const result = await fetcherRef.current();
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err : new Error("Unknown error"));
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }
    tickRef.current = tick;

    void tick();
    const id = window.setInterval(() => void tick(), intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [intervalMs, enabled]);

  return { data, error, isLoading, refetch: () => tickRef.current() };
}
