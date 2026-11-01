import { type ReactNode, useEffect, useMemo, useRef } from "react";
import { Animated, type StyleProp, type ViewStyle } from "react-native";
import { timing, useMotion } from "./index";

/**
 * Fades content in as it mounts, rising into place (or dropping, for menus hanging from a bar).
 * Runs once per mount: re-renders and data refreshes of an already visible item never replay it.
 * Children are interactive from the first frame.
 *
 * For content that arrives after a screen is visible (lists, results, errors), not for whole
 * screens: those already get the native navigation transition.
 */
export function FadeIn({
  children,
  index = 0,
  delay = 0,
  from = "below",
  animate = true,
  style,
}: {
  children: ReactNode;
  /** Position in a list; adds a capped stagger. */
  index?: number;
  /** Extra wait before appearing (e.g. the loading-spinner threshold). */
  delay?: number;
  /** `none`: opacity only, for large regions that shouldn't move. */
  from?: "below" | "above" | "none";
  /** Read once at mount; false renders the content in place with no animation. */
  animate?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const { enterOffset, enterDuration, staggerDelay } = useMotion();
  const animated = useRef(animate).current;
  const progress = useRef(new Animated.Value(animated ? 0 : 1)).current;
  // Offset is fixed at mount so a reduce-motion toggle mid-animation cannot make content jump.
  const offset = useRef(from === "none" ? 0 : (from === "above" ? -1 : 1) * enterOffset).current;
  const motionStyle = useMemo(
    () => ({
      opacity: progress,
      transform: animated && offset ? [{ translateY: progress.interpolate({ inputRange: [0, 1], outputRange: [offset, 0] }) }] : [],
    }),
    [progress, offset, animated],
  );

  useEffect(() => {
    if (!animated) return;
    const anim = timing(progress, 1, { duration: enterDuration, delay: delay + staggerDelay(index) });
    anim.start();
    return () => anim.stop();
    // Mount-only by design.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Animated.View style={[style, motionStyle]}>
      {children}
    </Animated.View>
  );
}

/**
 * For virtualized lists: rows that mount with the first batch of data ease in; rows mounted later
 * by scrolling appear in place, so scrolling never shows content trickling in.
 * Usage: `const firstBatch = useFirstBatch(data != null)` then `<FadeIn animate={firstBatch()} …>`.
 */
export function useFirstBatch(ready: boolean, windowMs = 400) {
  const until = useRef<number | null>(null);
  if (ready && until.current === null) until.current = Date.now() + windowMs;
  return () => until.current !== null && Date.now() < until.current;
}
