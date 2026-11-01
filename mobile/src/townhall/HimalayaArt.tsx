import { useEffect, useMemo, useRef } from "react";
import { Animated, Easing, StyleSheet, View } from "react-native";
import Svg, { ClipPath, Defs, Ellipse, G, LinearGradient, Path, Rect, Stop } from "react-native-svg";
import { useReducedMotion } from "../motion";

const W = 400;
const H = 520;

/** Deterministic pseudo-random (same mountains on every render and device). */
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

/**
 * Jagged ridge line through the given control points, roughened by midpoint displacement:
 * reads as real rock rather than triangles.
 */
function ridge(points: [number, number][], depth: number, rough: number, seed: number): [number, number][] {
  const rand = rng(seed);
  let pts = points;
  let amp = rough;
  for (let d = 0; d < depth; d++) {
    const next: [number, number][] = [];
    for (let i = 0; i < pts.length - 1; i++) {
      const [x1, y1] = pts[i];
      const [x2, y2] = pts[i + 1];
      next.push([x1, y1], [(x1 + x2) / 2, (y1 + y2) / 2 + (rand() - 0.5) * amp]);
    }
    next.push(pts[pts.length - 1]);
    pts = next;
    amp *= 0.55;
  }
  return pts;
}

const line = (pts: [number, number][]) => pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
const closeDown = (pts: [number, number][], bottom: number) => `${line(pts)} L${W} ${bottom} L0 ${bottom} Z`;

/**
 * Daylight Himalaya over the Doon valley for the Townhall card: blue sky, a snow massif with rock
 * showing below the snowline, Shivalik ridges, a lake with the peaks' reflection, drifting clouds.
 * Drawn as vectors, so it is crisp everywhere and needs no licensed photo.
 */
export function HimalayaArt({ width, height }: { width: number; height: number }) {
  const reduced = useReducedMotion();
  const drift = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (reduced) return;
    const a = Animated.loop(Animated.timing(drift, { toValue: 1, duration: 32000, easing: Easing.linear, useNativeDriver: true }));
    a.start();
    return () => a.stop();
  }, [reduced, drift]);

  const shapes = useMemo(() => {
    const far = ridge([[0, 250], [70, 205], [140, 232], [215, 190], [290, 226], [360, 200], [400, 222]], 6, 34, 7);
    const massif = ridge([[0, 300], [40, 262], [95, 228], [150, 190], [205, 150], [248, 118], [280, 142], [318, 176], [350, 168], [400, 214]], 7, 48, 21);
    // Snowline: a ragged edge well below the summit.
    const snow = ridge([[0, 286], [80, 252], [150, 236], [210, 222], [262, 214], [310, 236], [360, 240], [400, 262]], 6, 40, 33);
    const shivalik = ridge([[0, 352], [90, 318], [170, 340], [250, 314], [330, 336], [400, 318]], 5, 20, 45);
    const shore = ridge([[0, 392], [120, 380], [240, 388], [400, 378]], 4, 10, 52);
    return { far, massif, snow, shivalik, shore };
  }, []);

  const lakeTop = 396;

  return (
    <View style={{ width, height, overflow: "hidden" }}>
      <Svg width={width} height={height} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid slice">
        <Defs>
          <LinearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor="#4F86C6" />
            <Stop offset="0.6" stopColor="#8DB7E2" />
            <Stop offset="1" stopColor="#C9DDF0" />
          </LinearGradient>
          <LinearGradient id="rock" x1="0" y1="0" x2="1" y2="1">
            <Stop offset="0" stopColor="#4C6C9C" />
            <Stop offset="1" stopColor="#23395E" />
          </LinearGradient>
          <LinearGradient id="snow" x1="0" y1="0" x2="1" y2="1">
            <Stop offset="0" stopColor="#FFFFFF" />
            <Stop offset="0.55" stopColor="#E3ECF7" />
            <Stop offset="1" stopColor="#9FB7D6" />
          </LinearGradient>
          <LinearGradient id="hill" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor="#3A5A55" />
            <Stop offset="1" stopColor="#1F322F" />
          </LinearGradient>
          <LinearGradient id="lake" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor="#3F6FA5" />
            <Stop offset="1" stopColor="#1C3557" />
          </LinearGradient>
          <ClipPath id="massifClip">
            <Path d={closeDown(shapes.massif, lakeTop)} />
          </ClipPath>
        </Defs>

        <Rect x="0" y="0" width={W} height={H} fill="url(#sky)" />
        <Path d={closeDown(shapes.far, lakeTop)} fill="#A9C0DD" opacity={0.85} />
        <Path d={closeDown(shapes.far, lakeTop)} fill="#FFFFFF" opacity={0.25} />

        {/* Massif: rock, then snow above the snowline (clipped to the mountain) */}
        <Path d={closeDown(shapes.massif, lakeTop)} fill="url(#rock)" />
        <G clipPath="url(#massifClip)">
          <Path d={`M0 0 L${W} 0 ${[...shapes.snow].reverse().map(([x, y]) => `L${x.toFixed(1)} ${y.toFixed(1)}`).join(" ")} Z`} fill="url(#snow)" />
        </G>
        <Path d={closeDown(shapes.shivalik, lakeTop)} fill="url(#hill)" />
        <Path d={closeDown(shapes.shore, lakeTop + 4)} fill="#1B2B28" />

        {/* Lake + mirrored peaks */}
        <Rect x="0" y={lakeTop} width={W} height={H - lakeTop} fill="url(#lake)" />
        <G opacity={0.28} transform={`translate(0 ${lakeTop * 2}) scale(1 -1)`}>
          <Path d={closeDown(shapes.massif, lakeTop)} fill="#DCE7F5" />
        </G>
        {Array.from({ length: 9 }, (_, i) => (
          <Rect key={i} x={20 + i * 42} y={lakeTop + 14 + (i % 3) * 22} width={26 + (i % 4) * 8} height={1.4} fill="#FFFFFF" opacity={0.35} />
        ))}
      </Svg>

      {/* Drifting clouds */}
      <Animated.View
        pointerEvents="none"
        style={[StyleSheet.absoluteFill, { transform: [{ translateX: drift.interpolate({ inputRange: [0, 1], outputRange: [-width * 0.5, width * 1.05] }) }] }]}
      >
        <Svg width={width * 0.5} height={height * 0.12} style={{ position: "absolute", top: height * 0.1 }} viewBox="0 0 200 50">
          <Ellipse cx="60" cy="30" rx="55" ry="14" fill="#FFFFFF" opacity={0.75} />
          <Ellipse cx="105" cy="22" rx="40" ry="16" fill="#FFFFFF" opacity={0.85} />
          <Ellipse cx="145" cy="31" rx="45" ry="11" fill="#FFFFFF" opacity={0.7} />
        </Svg>
      </Animated.View>
      <Animated.View
        pointerEvents="none"
        style={[StyleSheet.absoluteFill, { transform: [{ translateX: drift.interpolate({ inputRange: [0, 1], outputRange: [width * 0.6, -width * 0.6] }) }] }]}
      >
        <Svg width={width * 0.35} height={height * 0.08} style={{ position: "absolute", top: height * 0.24 }} viewBox="0 0 200 50">
          <Ellipse cx="70" cy="28" rx="60" ry="12" fill="#FFFFFF" opacity={0.55} />
          <Ellipse cx="125" cy="24" rx="45" ry="13" fill="#FFFFFF" opacity={0.6} />
        </Svg>
      </Animated.View>
    </View>
  );
}
