import { useEffect, useMemo, useRef } from "react";
import { Animated, Easing, StyleSheet, View } from "react-native";
import Svg, { Defs, LinearGradient, Path, Stop } from "react-native-svg";
import { useReducedMotion } from "../motion";

/** Wave layers in the app palette: maroon primary, accent blue, rose. */
const LAYERS = [
  { from: "#9A2143", to: "#E85A6B", wavelength: 0.62, amp: 0.2, base: 0.58, speed: 2600, opacity: 0.55 },
  { from: "#3B82F6", to: "#1D2B4F", wavelength: 0.9, amp: 0.16, base: 0.64, speed: 3800, opacity: 0.45 },
  { from: "#F6C3CA", to: "#9A2143", wavelength: 0.45, amp: 0.12, base: 0.7, speed: 1900, opacity: 0.5 },
];

/** Filled sine wave, two wavelengths wider than the box so a horizontal scroll loops seamlessly. */
function wavePath(width: number, height: number, wavelength: number, amp: number, base: number) {
  const total = width + wavelength * 2;
  const pts: string[] = [];
  for (let x = 0; x <= total; x += 4) {
    pts.push(`${x.toFixed(1)},${(base + amp * Math.sin((2 * Math.PI * x) / wavelength)).toFixed(1)}`);
  }
  return `M0,${height} L${pts.join(" L")} L${total},${height} Z`;
}

/**
 * Fluid waves filling a rounded rectangle while the assistant listens (height follows the voice level)
 * or thinks (slow, low swell). Native-driver transforms only; a still wave under reduce motion.
 */
export function Waves({
  width,
  height,
  level,
  mode,
  radius = 18,
}: {
  width: number;
  height: number;
  /** 0..1 input level (from useVoice); omitted = steady swell. */
  level?: Animated.Value;
  mode: "listening" | "thinking";
  radius?: number;
}) {
  const reduced = useReducedMotion();
  const scroll = useRef(LAYERS.map(() => new Animated.Value(0))).current;
  const swell = useRef(new Animated.Value(0)).current;

  const layers = useMemo(
    () =>
      LAYERS.map((l) => {
        const wl = Math.max(40, width * l.wavelength);
        return { ...l, wl, d: wavePath(width, height, wl, height * l.amp, height * l.base), w: width + wl * 2 };
      }),
    [width, height],
  );

  useEffect(() => {
    if (reduced || width <= 0) return;
    const slow = mode === "thinking" ? 2.2 : 1;
    const loops = [
      ...layers.map((l, i) =>
        Animated.loop(
          Animated.timing(scroll[i], { toValue: 1, duration: l.speed * slow, easing: Easing.linear, useNativeDriver: true }),
        ),
      ),
      Animated.loop(
        Animated.sequence([
          Animated.timing(swell, { toValue: 1, duration: 900 * slow, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
          Animated.timing(swell, { toValue: 0, duration: 900 * slow, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
        ]),
      ),
    ];
    loops.forEach((l) => l.start());
    return () => {
      loops.forEach((l) => l.stop());
      scroll.forEach((v) => v.setValue(0));
    };
  }, [reduced, mode, layers, scroll, swell, width]);

  // Wave height: steady swell, plus the live voice level while listening.
  const lift =
    mode === "listening" && level
      ? Animated.add(swell.interpolate({ inputRange: [0, 1], outputRange: [0.55, 0.7] }), Animated.multiply(level, 0.75))
      : swell.interpolate({ inputRange: [0, 1], outputRange: [0.35, 0.5] });

  return (
    <View pointerEvents="none" style={[StyleSheet.absoluteFill, { borderRadius: radius, overflow: "hidden" }]}>
      {layers.map((l, i) => (
        <Animated.View
          key={i}
          style={{
            position: "absolute",
            left: 0,
            bottom: 0,
            width: l.w,
            height,
            opacity: l.opacity,
            transform: [
              // Alternate directions so the layers cross like moving water.
              { translateX: scroll[i].interpolate({ inputRange: [0, 1], outputRange: i % 2 ? [-l.wl, 0] : [0, -l.wl] }) },
              { translateY: height / 2 },
              { scaleY: lift },
              { translateY: -height / 2 },
            ],
          }}
        >
          <Svg width={l.w} height={height}>
            <Defs>
              <LinearGradient id={`w${i}`} x1="0" y1="0" x2="1" y2="1">
                <Stop offset="0" stopColor={l.from} />
                <Stop offset="1" stopColor={l.to} />
              </LinearGradient>
            </Defs>
            <Path d={l.d} fill={`url(#w${i})`} />
          </Svg>
        </Animated.View>
      ))}
    </View>
  );
}
