import * as Location from "expo-location";
import { useCallback, useEffect, useState } from "react";

export interface LatLng {
  latitude: number;
  longitude: number;
}

type Status = "pending" | "granted" | "denied" | "unavailable";

const FIX_TIMEOUT_MS = 12000;

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return Promise.race([p, new Promise<T>((_, reject) => setTimeout(() => reject(new Error("timeout")), ms))]);
}

/** Foreground location with graceful fallback: callers use the map's default centre when null. */
export function useUserLocation() {
  const [coords, setCoords] = useState<LatLng | null>(null);
  const [status, setStatus] = useState<Status>("pending");

  const refresh = useCallback(async () => {
    try {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (perm.status !== "granted") {
        setStatus("denied");
        return null;
      }
      const last = await Location.getLastKnownPositionAsync();
      const lastCoords = last ? { latitude: last.coords.latitude, longitude: last.coords.longitude } : null;
      if (lastCoords) setCoords(lastCoords);
      try {
        // A fresh fix can hang indoors / with GPS off; fall back to the last known position.
        const pos = await withTimeout(
          Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }),
          FIX_TIMEOUT_MS,
        );
        const next = { latitude: pos.coords.latitude, longitude: pos.coords.longitude };
        setCoords(next);
        setStatus("granted");
        return next;
      } catch {
        setStatus(lastCoords ? "granted" : "unavailable");
        return lastCoords;
      }
    } catch {
      setStatus("unavailable");
      return null;
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { coords, status, refresh };
}
