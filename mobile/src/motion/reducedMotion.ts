import { useSyncExternalStore } from "react";
import { AccessibilityInfo } from "react-native";

// One app-wide subscription to the OS setting (iOS Reduce Motion; Android "Remove animations").
let reduced = false;
const listeners = new Set<() => void>();

const set = (value: boolean) => {
  if (value === reduced) return;
  reduced = value;
  listeners.forEach((l) => l());
};

AccessibilityInfo.isReduceMotionEnabled()
  .then(set)
  .catch(() => {});
AccessibilityInfo.addEventListener("reduceMotionChanged", set);

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

/** Current reduce-motion preference, for code outside React (camera moves, layout transitions). */
export const isReducedMotion = () => reduced;

/** Re-renders when the user toggles reduce motion in system settings. */
export const useReducedMotion = () => useSyncExternalStore(subscribe, isReducedMotion);
