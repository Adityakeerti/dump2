import { useCallback, useEffect, useState } from "react";
import { errorMessage } from "../api/client";
import { geoApi } from "../api/endpoints";
import type { MapConfig } from "../api/types";

let cached: MapConfig | null = null;

/** Map defaults (style URL, default centre, geofence radius) served by core. */
export function useMapConfig() {
  const [config, setConfig] = useState<MapConfig | null>(cached);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      cached = await geoApi.config();
      setConfig(cached);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    if (!cached) void load();
  }, [load]);

  return { config, error, reload: load };
}
