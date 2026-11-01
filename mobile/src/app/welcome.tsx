import { Image } from "expo-image";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useEffect, useMemo, useRef } from "react";
import { Animated, Easing, StyleSheet, useWindowDimensions, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import Svg, { Path } from "react-native-svg";
import { Button } from "../components/Button";
import { images } from "../content/onboarding";
import { duration, isReducedMotion, kite, timing, useReducedMotion } from "../motion";
import { splashRemaining } from "../motion/splash";
import { colors, fonts } from "../theme";

/** Sine in-out: the float leaves and turns at zero velocity, so it never jolts. */
const wave = Easing.inOut(Easing.sin);
const native = { useNativeDriver: true } as const;

/**
 * Welcome's kite (timings in motion/tokens `kite`): arrives, floats while the screen is focused, and takes off when
 * Login is pressed. Login is pushed part-way through the flight with a cross-fade, so it appears while the kite is
 * still leaving. All opacity/transform on the native driver; loops and timers are torn down on blur and unmount.
 */
function useKite(width: number, height: number) {
  const reduced = useReducedMotion();
  const v = useRef({
    enter: new Animated.Value(0),
    floatY: new Animated.Value(0),
    tilt: new Animated.Value(0),
    flight: new Animated.Value(0),
    flightX: new Animated.Value(0),
    flightY: new Animated.Value(0),
    away: new Animated.Value(0),
    trail: new Animated.Value(0),
  }).current;
  const entered = useRef(false);
  const focused = useRef(false);
  const leaving = useRef(false);
  const navigated = useRef(false);
  const floatLoop = useRef<Animated.CompositeAnimation | null>(null);
  const flightAnim = useRef<Animated.CompositeAnimation | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const startFloat = useCallback(() => {
    if (!entered.current || !focused.current || leaving.current || floatLoop.current || isReducedMotion()) return;
    const swing = (value: Animated.Value, period: number) =>
      Animated.loop(
        Animated.sequence([
          Animated.timing(value, { toValue: 1, duration: period / 2, easing: wave, ...native }),
          Animated.timing(value, { toValue: 0, duration: period / 2, easing: wave, ...native }),
        ]),
      );
    floatLoop.current = Animated.parallel([swing(v.floatY, kite.float.period), swing(v.tilt, kite.float.tiltPeriod)], {
      stopTogether: false,
    });
    floatLoop.current.start();
  }, [v]);

  const stopFloat = useCallback(() => {
    floatLoop.current?.stop();
    floatLoop.current = null;
    timing(v.floatY, 0, { duration: duration.fast, curve: "move" }).start();
    timing(v.tilt, 0, { duration: duration.fast, curve: "move" }).start();
  }, [v]);

  // Arrival. On a cold start the native splash is still dissolving over this screen: wait it out.
  useEffect(() => {
    const reducedAtStart = isReducedMotion();
    const anim = timing(v.enter, 1, {
      duration: reducedAtStart ? duration.fast : kite.enter.duration,
      delay: reducedAtStart ? 0 : splashRemaining(),
    });
    anim.start(() => {
      entered.current = true;
      startFloat();
    });
    const pending = timers.current;
    return () => {
      anim.stop();
      floatLoop.current?.stop();
      flightAnim.current?.stop();
      pending.forEach(clearTimeout);
    };
  }, [v, startFloat]);

  /**
   * Coming back to Welcome (Back from Login): put the kite back at rest. Done on focus rather than on a timer,
   * because a native flight still running when Login covered the screen can finish late and would overwrite an
   * earlier reset. Stopping it first syncs its value, so the reset sticks.
   */
  const restore = useCallback(() => {
    if (!leaving.current) return;
    flightAnim.current?.stop();
    flightAnim.current = null;
    for (const key of ["flight", "flightX", "flightY", "away", "trail"] as const) v[key].stopAnimation();
    for (const key of ["flight", "flightX", "flightY", "away", "trail"] as const) v[key].setValue(0);
    leaving.current = false;
    navigated.current = false;
  }, [v]);

  // Float only while Welcome is the focused screen; coming back from Login finds the kite at rest and floating again.
  useFocusEffect(
    useCallback(() => {
      focused.current = true;
      restore();
      startFloat();
      return () => {
        focused.current = false;
        stopFloat();
      };
    }, [restore, startFloat, stopFloat]),
  );

  useEffect(() => {
    if (reduced) stopFloat();
  }, [reduced, stopFloat]);

  const goToLogin = useCallback(() => {
    if (navigated.current) return;
    navigated.current = true;
    router.push({ pathname: "/login", params: { via: "kite" } });
  }, []);


  const takeOff = useCallback(() => {
    // A second press mid-flight means "go now": skip the rest of the wait, never push twice.
    if (leaving.current) return goToLogin();
    leaving.current = true;
    floatLoop.current?.stop();
    floatLoop.current = null;
    const f = kite.flight;
    if (isReducedMotion()) {
      flightAnim.current = timing(v.away, 1, { duration: kite.reducedExit, curve: "move" });
      flightAnim.current.start();
      goToLogin();
      return;
    }
    flightAnim.current = Animated.parallel([
      Animated.timing(v.flight, { toValue: 1, duration: f.duration, easing: Easing.in(Easing.quad), ...native }),
      // Lifts first, then sweeps right: y picks up early, x accelerates later, so the path curves out of the corner.
      Animated.timing(v.flightY, { toValue: 1, duration: f.duration, easing: Easing.bezier(0.3, 0, 0.7, 0.6), ...native }),
      Animated.timing(v.flightX, { toValue: 1, duration: f.duration, easing: Easing.in(Easing.quad), ...native }),
      timing(v.away, 1, { duration: f.panel, delay: f.panelDelay, curve: "move" }),
      timing(v.trail, 1, { duration: f.trail, curve: "move" }),
    ]);
    flightAnim.current.start();
    timers.current.push(setTimeout(goToLogin, f.navigateAt));
  }, [v, goToLogin]);

  const styles = useMemo(() => {
    function lerp(value: Animated.Value, from: number, to: number): Animated.AnimatedInterpolation<number>;
    function lerp(value: Animated.Value, from: string, to: string): Animated.AnimatedInterpolation<string>;
    function lerp(value: Animated.Value, from: number | string, to: number | string) {
      return value.interpolate({ inputRange: [0, 1], outputRange: [from, to] as never });
    }
    const e = kite.enter;
    const f = kite.flight;
    const titleOut = v.away.interpolate({ inputRange: [0, f.title / f.panel, 1], outputRange: [1, 0, 0] });
    return {
      flight: reduced
        ? { opacity: lerp(v.away, 1, 0) }
        : {
            opacity: v.flight.interpolate({ inputRange: [0, f.fadeFrom, 1], outputRange: [1, 1, 0] }),
            transform: [
              { translateX: lerp(v.flightX, 0, width * 0.9) },
              { translateY: lerp(v.flightY, 0, -height * 0.7) },
              { rotate: lerp(v.flight, "0deg", `${f.rotateTo}deg`) },
              { scale: lerp(v.flight, 1, f.scaleTo) },
            ],
          },
      enter: reduced
        ? { opacity: v.enter }
        : {
            opacity: v.enter,
            transform: [
              { translateY: lerp(v.enter, e.fromOffset, 0) },
              { rotate: lerp(v.enter, `${e.fromRotate}deg`, "0deg") },
              { scale: lerp(v.enter, e.fromScale, 1) },
            ],
          },
      float: {
        transform: [{ translateY: lerp(v.floatY, 0, -kite.float.amount) }, { rotate: lerp(v.tilt, "0deg", `${kite.float.tilt}deg`) }],
      },
      panelIn: { opacity: v.enter.interpolate({ inputRange: [0, e.panel / e.duration, 1], outputRange: [0, 1, 1] }) },
      panelOut: { opacity: lerp(v.away, 1, 0) },
      titleIn: {
        opacity: v.enter.interpolate({ inputRange: [0, e.titleDelay / e.duration, 1], outputRange: [0, 0, 1] }),
      },
      titleOut: { opacity: titleOut },
      trail: {
        opacity: v.trail.interpolate({ inputRange: [0, 0.3, 1], outputRange: [0, 0.7, 0] }),
        transform: [{ translateX: lerp(v.trail, 0, -24) }, { translateY: lerp(v.trail, 0, 16) }],
      },
    };
  }, [v, reduced, width, height]);

  return { styles, takeOff, isLeaving: () => leaving.current };
}

export default function Welcome() {
  const { width, height } = useWindowDimensions();
  const archW = width * 0.82;
  const archH = archW * (570 / 375);
  const k = useKite(width, height);
  const kiteW = archW * 0.62;
  const kiteH = archW * 0.78;
  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.center}>
        <View style={{ width: archW, height: archH, alignItems: "center", justifyContent: "center" }}>
          <Animated.View style={[StyleSheet.absoluteFill, k.styles.panelIn]}>
            <Animated.View style={[StyleSheet.absoluteFill, k.styles.panelOut]}>
              <Image source={images.archGreen} style={StyleSheet.absoluteFill} contentFit="fill" />
            </Animated.View>
          </Animated.View>
          <View style={{ width: kiteW, height: kiteH }}>
            {/* Wind trails left behind at takeoff (vector strokes, no new artwork). */}
            <Animated.View pointerEvents="none" style={[styles.trails, { width: kiteW * 0.7, height: kiteH * 0.4 }, k.styles.trail]}>
              <Svg width="100%" height="100%" viewBox="0 0 100 50" preserveAspectRatio="none">
                <Path d="M2 34 Q 40 4 98 14" stroke={colors.textMuted} strokeOpacity={0.45} strokeWidth={1.6} strokeLinecap="round" fill="none" />
                <Path d="M14 48 Q 50 22 92 30" stroke={colors.textMuted} strokeOpacity={0.3} strokeWidth={1.4} strokeLinecap="round" fill="none" />
              </Svg>
            </Animated.View>
            <Animated.View style={[StyleSheet.absoluteFill, k.styles.flight]}>
              <Animated.View style={[StyleSheet.absoluteFill, k.styles.enter]}>
                <Animated.View style={[StyleSheet.absoluteFill, k.styles.float]}>
                  <Image source={images.kite} style={StyleSheet.absoluteFill} contentFit="contain" />
                </Animated.View>
              </Animated.View>
            </Animated.View>
          </View>
          <Animated.View style={k.styles.titleIn}>
            <Animated.Text style={[styles.title, k.styles.titleOut]}>Lets goo .</Animated.Text>
          </Animated.View>
        </View>
      </View>
      <View style={styles.actions}>
        {/* Ignored while the kite is taking off, so Login and Sign Up can never both be pushed. */}
        <Button title="Sign Up" onPress={() => !k.isLeaving() && router.push("/signup")} style={styles.btn} compact />
        <Button title="Login" variant="outline" onPress={k.takeOff} style={styles.btn} compact />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: fonts.display, fontSize: 30, color: colors.text, marginTop: 8 },
  trails: { position: "absolute", left: "-30%", bottom: "8%" },
  actions: { flexDirection: "row", gap: 16, paddingHorizontal: 28, paddingBottom: 28 },
  btn: { flex: 1 },
});
