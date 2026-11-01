import { useMemo } from "react";
import { Animated, Easing, LayoutAnimation } from "react-native";
import { isReducedMotion, useReducedMotion } from "./reducedMotion";
import { curve, duration, motionFor } from "./tokens";

export * from "./tokens";
export { isReducedMotion, useReducedMotion } from "./reducedMotion";

export const easing = {
  enter: Easing.bezier(...curve.enter),
  move: Easing.bezier(...curve.move),
};

/** Motion values resolved for the user's reduce-motion setting. */
export function useMotion() {
  const reduced = useReducedMotion();
  return useMemo(() => ({ reduced, ...motionFor(reduced) }), [reduced]);
}

/** Native-driver timing on the shared curves. Only opacity and transform may be driven this way. */
export const timing = (
  value: Animated.Value,
  toValue: number,
  opts: { duration: number; delay?: number; curve?: keyof typeof easing },
) =>
  Animated.timing(value, {
    toValue,
    duration: opts.duration,
    delay: opts.delay ?? 0,
    easing: easing[opts.curve ?? "enter"],
    useNativeDriver: true,
  });

/**
 * Call right before a state change that adds or removes rows, so neighbours glide into place
 * instead of jumping. No-op under reduce motion.
 */
export function animateNextLayout() {
  if (isReducedMotion()) return;
  LayoutAnimation.configureNext({
    duration: duration.base,
    create: { type: LayoutAnimation.Types.easeInEaseOut, property: LayoutAnimation.Properties.opacity },
    update: { type: LayoutAnimation.Types.easeInEaseOut },
    delete: { type: LayoutAnimation.Types.easeInEaseOut, property: LayoutAnimation.Properties.opacity },
  });
}
