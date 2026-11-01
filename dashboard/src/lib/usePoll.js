import { useEffect, useRef, useState } from "react";

// Poll an async loader; keeps the last good data and exposes the latest error.
export function usePoll(loader, intervalMs, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const saved = useRef(loader);
  saved.current = loader;
  useEffect(() => {
    let alive = true;
    let timer;
    const tick = async () => {
      try {
        const d = await saved.current();
        if (alive) { setData(d); setError(null); }
      } catch (e) {
        if (alive) setError(e.message || String(e));
      }
      if (alive) timer = setTimeout(tick, intervalMs);
    };
    tick();
    return () => { alive = false; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, ...deps]);
  return { data, error };
}
