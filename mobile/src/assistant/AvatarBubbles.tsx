import { Ionicons } from "@expo/vector-icons";
import { useEffect, useRef, useState } from "react";
import { Animated, Easing, StyleSheet, Text, View } from "react-native";
import { useReducedMotion } from "../motion";
import { colors, fonts } from "../theme";

export type BubbleMode = "idle" | "thinking" | "speaking" | "listening";

const native = { useNativeDriver: true } as const;

/**
 * Comic-style bubbles that float beside the main avatar so it feels alive:
 * idle -> rotating short lines, thinking -> thought bubble with bouncing dots,
 * speaking -> speech bubble with sound bars, listening -> pulsing mic.
 * Position it absolutely next to the avatar; it never takes touches.
 */
export function AvatarBubbles({
  mode,
  phrases = [],
  interval = 3800,
  initialDelay = 600,
  dark = false,
}: {
  mode: BubbleMode;
  phrases?: string[];
  interval?: number;
  initialDelay?: number;
  /** Light text on a navy bubble (for light backgrounds use the default white bubble). */
  dark?: boolean;
}) {
  const reduced = useReducedMotion();
  const pop = useRef(new Animated.Value(0)).current;
  const [index, setIndex] = useState(0);
  // Restart the idle cycle only when the words change, not when a parent re-creates the array.
  const phraseKey = phrases.join("\u0001");
  const count = phrases.length;

  // Pop in on every mode change.
  useEffect(() => {
    if (mode === "idle") return;
    pop.setValue(reduced ? 1 : 0);
    if (!reduced) Animated.spring(pop, { toValue: 1, friction: 6, tension: 120, ...native }).start();
  }, [mode, reduced, pop]);

  // Idle: cycle through phrases — pop in, hold, fade out, pause.
  useEffect(() => {
    if (mode !== "idle" || count === 0) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const show = (i: number, delay: number) => {
      timer = setTimeout(() => {
        if (cancelled) return;
        setIndex(i);
        if (reduced) {
          pop.setValue(1);
          show((i + 1) % count, interval);
          return;
        }
        pop.setValue(0);
        Animated.sequence([
          Animated.spring(pop, { toValue: 1, friction: 6, tension: 110, ...native }),
          Animated.delay(interval * 0.6),
          Animated.timing(pop, { toValue: 0, duration: 260, easing: Easing.in(Easing.quad), ...native }),
        ]).start(({ finished }) => finished && !cancelled && show((i + 1) % count, interval * 0.35));
      }, delay);
    };
    show(0, initialDelay);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      pop.stopAnimation();
    };
  }, [mode, phraseKey, count, interval, initialDelay, reduced, pop]);

  const appear = {
    opacity: pop,
    transform: [
      { translateY: pop.interpolate({ inputRange: [0, 1], outputRange: [8, 0] }) },
      { scale: pop.interpolate({ inputRange: [0, 1], outputRange: [0.6, 1] }) },
    ],
  };
  const bubbleStyle = [styles.bubble, dark && styles.bubbleDark];

  if (mode === "thinking") {
    return (
      <Animated.View pointerEvents="none" style={[styles.wrap, appear]}>
        <View style={[styles.bubble, styles.thought, dark && styles.bubbleDark]}>
          <BouncingDots color={dark ? "#fff" : colors.navy} />
        </View>
        {/* Thought trail: two shrinking circles back towards the avatar. */}
        <View style={[styles.trailBig, dark && styles.bubbleDark]} />
        <View style={[styles.trailSmall, dark && styles.bubbleDark]} />
      </Animated.View>
    );
  }
  if (mode === "speaking") {
    return (
      <Animated.View pointerEvents="none" style={[styles.wrap, appear]}>
        <View style={[bubbleStyle, styles.row]}>
          <SoundBars color={dark ? "#fff" : colors.primary} />
        </View>
        <View style={[styles.tail, dark && styles.tailDark]} />
      </Animated.View>
    );
  }
  if (mode === "listening") {
    return (
      <Animated.View pointerEvents="none" style={[styles.wrap, appear]}>
        <View style={[bubbleStyle, styles.row]}>
          <PulsingIcon name="mic" color={colors.danger} />
          <Text style={[styles.text, dark && styles.textDark]}>Listening</Text>
        </View>
        <View style={[styles.tail, dark && styles.tailDark]} />
      </Animated.View>
    );
  }
  if (!phrases.length) return null;
  return (
    <Animated.View pointerEvents="none" style={[styles.wrap, appear]}>
      <View style={bubbleStyle}>
        <Text style={[styles.text, dark && styles.textDark]} numberOfLines={1}>
          {phrases[index % phrases.length]}
        </Text>
      </View>
      <View style={[styles.tail, dark && styles.tailDark]} />
    </Animated.View>
  );
}

function BouncingDots({ color }: { color: string }) {
  const reduced = useReducedMotion();
  const dots = useRef([0, 1, 2].map(() => new Animated.Value(0))).current;
  useEffect(() => {
    if (reduced) return;
    const loops = dots.map((d, i) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(i * 140),
          Animated.timing(d, { toValue: 1, duration: 280, easing: Easing.out(Easing.quad), ...native }),
          Animated.timing(d, { toValue: 0, duration: 280, easing: Easing.in(Easing.quad), ...native }),
          Animated.delay((2 - i) * 140 + 200),
        ]),
      ),
    );
    loops.forEach((l) => l.start());
    return () => loops.forEach((l) => l.stop());
  }, [reduced, dots]);
  return (
    <View style={styles.row}>
      {dots.map((d, i) => (
        <Animated.View
          key={i}
          style={[styles.dot, { backgroundColor: color, transform: [{ translateY: d.interpolate({ inputRange: [0, 1], outputRange: [0, -4] }) }] }]}
        />
      ))}
    </View>
  );
}

function SoundBars({ color }: { color: string }) {
  const reduced = useReducedMotion();
  const bars = useRef([0, 1, 2, 3].map(() => new Animated.Value(0.4))).current;
  useEffect(() => {
    if (reduced) return;
    const loops = bars.map((b, i) =>
      Animated.loop(
        Animated.sequence([
          Animated.timing(b, { toValue: 1, duration: 220 + i * 60, easing: Easing.inOut(Easing.sin), ...native }),
          Animated.timing(b, { toValue: 0.35, duration: 240 + i * 50, easing: Easing.inOut(Easing.sin), ...native }),
        ]),
      ),
    );
    loops.forEach((l) => l.start());
    return () => loops.forEach((l) => l.stop());
  }, [reduced, bars]);
  return (
    <View style={[styles.row, { height: 14, gap: 3 }]}>
      {bars.map((b, i) => (
        <Animated.View key={i} style={[styles.bar, { backgroundColor: color, transform: [{ scaleY: b }] }]} />
      ))}
    </View>
  );
}

function PulsingIcon({ name, color }: { name: keyof typeof Ionicons.glyphMap; color: string }) {
  const reduced = useReducedMotion();
  const p = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (reduced) return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(p, { toValue: 1, duration: 500, ...native }),
        Animated.timing(p, { toValue: 0, duration: 500, ...native }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [reduced, p]);
  return (
    <Animated.View style={{ transform: [{ scale: p.interpolate({ inputRange: [0, 1], outputRange: [0.9, 1.2] }) }] }}>
      <Ionicons name={name} size={12} color={color} />
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: "flex-start" },
  bubble: {
    backgroundColor: "#fff",
    borderRadius: 12,
    paddingHorizontal: 9,
    paddingVertical: 5,
    elevation: 4,
    shadowColor: "#000",
    shadowOpacity: 0.16,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
    maxWidth: 190,
  },
  bubbleDark: { backgroundColor: colors.navy },
  thought: { borderRadius: 14, paddingHorizontal: 10, paddingVertical: 7 },
  row: { flexDirection: "row", alignItems: "center", gap: 4 },
  text: { fontFamily: fonts.semibold, fontSize: 11, color: colors.navy },
  textDark: { color: "#fff" },
  tail: {
    marginLeft: 10,
    width: 0,
    height: 0,
    borderLeftWidth: 5,
    borderRightWidth: 5,
    borderTopWidth: 7,
    borderLeftColor: "transparent",
    borderRightColor: "transparent",
    borderTopColor: "#fff",
  },
  tailDark: { borderTopColor: colors.navy },
  trailBig: { marginLeft: 8, marginTop: 2, width: 8, height: 8, borderRadius: 4, backgroundColor: "#fff", elevation: 3 },
  trailSmall: { marginLeft: 4, marginTop: 2, width: 5, height: 5, borderRadius: 2.5, backgroundColor: "#fff", elevation: 3 },
  dot: { width: 5, height: 5, borderRadius: 2.5 },
  bar: { width: 3, height: 14, borderRadius: 1.5 },
});
