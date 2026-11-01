import { Image } from "expo-image";
import { router } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Animated,
  Easing,
  FlatList,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  PixelRatio,
  Pressable,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useAuth } from "../auth/AuthContext";
import { NextArrow } from "../components/NextArrow";
import { PageDots } from "../components/PageDots";
import { images, type Slide, slides } from "../content/onboarding";
import {
  avatarDepthFor,
  avatarIdle,
  avatarIdleFor,
  avatarIntro,
  avatarIntroFor,
  type DepthLayer,
  distance,
  gridIntro,
  gridIntroFor,
  introFor,
  isReducedMotion,
  timing,
  useReducedMotion,
} from "../motion";
import { splashRemaining } from "../motion/splash";
import { colors, fonts } from "../theme";

type IntroStyles = ReturnType<typeof useIntro>["styles"];

/** Once per app launch: re-mounting onboarding in the same session (or any re-render) shows it settled. */
let introPlayed = false;
/** Upper bound on waiting for the emblem to decode before the sequence starts anyway. */
const ARTWORK_WAIT_MS = 250;

/**
 * Frame 1 opening sequence (backdrop, emblem, wordmark, controls; timings in motion/tokens `intro`).
 * Opacity and transform only, on the native driver. Never blocks input: `finish()` snaps everything
 * to rest and is called on the first swipe or tap.
 */
function useIntro() {
  const play = useRef(!introPlayed).current;
  const reduced = useReducedMotion();
  const v = useRef({
    backdrop: new Animated.Value(play ? 0 : 1),
    artwork: new Animated.Value(play ? 0 : 1),
    title: new Animated.Value(play ? 0 : 1),
    controls: new Animated.Value(play ? 0 : 1),
  }).current;
  const anim = useRef<Animated.CompositeAnimation | null>(null);
  const done = useRef(!play);
  // Movement is fixed when the sequence starts, so a reduce-motion change mid-way cannot make content jump.
  const [stages] = useState(() => introFor(isReducedMotion()));

  const finish = useCallback(() => {
    if (done.current) return;
    done.current = true;
    anim.current?.stop();
    v.backdrop.setValue(1);
    v.artwork.setValue(1);
    v.title.setValue(1);
    v.controls.setValue(1);
  }, [v]);

  const start = useCallback(() => {
    if (done.current || anim.current) return;
    introPlayed = true;
    // On a cold start the native splash is still dissolving over this screen: begin once it has cleared so
    // the backdrop stage is actually seen. Under reduce motion nothing waits.
    const lead = isReducedMotion() ? 0 : splashRemaining();
    anim.current = Animated.parallel(
      (["backdrop", "artwork", "title", "controls"] as const).map((k) =>
        // The backdrop is an in-place dissolve: the symmetric `move` curve spreads it over its full 300 ms.
        // (The front-loaded `enter` curve finishes 90% of a fade in about half its time, so the arch read as a pop.)
        timing(v[k], 1, {
          duration: stages[k].duration,
          delay: lead + stages[k].delay,
          curve: k === "backdrop" ? "move" : "enter",
        }),
      ),
    );
    anim.current.start(({ finished }) => {
      if (finished) done.current = true;
    });
  }, [v, stages]);

  useEffect(() => {
    if (!play) return;
    const fallback = setTimeout(start, ARTWORK_WAIT_MS);
    return () => {
      clearTimeout(fallback);
      anim.current?.stop();
    };
    // Mount-only by design.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Turning reduce motion on while the sequence is running settles it immediately. If it was already on
  // when the screen opened, `stages` is the reduced cross-fade and must be allowed to run.
  const startedReduced = useRef(isReducedMotion()).current;
  useEffect(() => {
    if (reduced && !startedReduced) finish();
  }, [reduced, startedReduced, finish]);

  const styles = useMemo(() => {
    const rise = (value: Animated.Value, offset: number) =>
      value.interpolate({ inputRange: [0, 1], outputRange: [offset, 0] });
    const scaleFrom = (value: Animated.Value, s: number) =>
      value.interpolate({ inputRange: [0, 1], outputRange: [s, 1] });
    return {
      backdrop: { opacity: v.backdrop },
      artwork: { opacity: v.artwork, transform: [{ scale: scaleFrom(v.artwork, stages.artwork.fromScale) }] },
      title: { opacity: v.title, transform: [{ translateY: rise(v.title, stages.title.fromOffset) }] },
      dots: { opacity: v.controls },
      arrow: { opacity: v.controls, transform: [{ scale: scaleFrom(v.controls, stages.controls.fromScale) }] },
    };
  }, [v, stages]);

  return { styles, start, finish };
}

export default function Onboarding() {
  const { width } = useWindowDimensions();
  const list = useRef<FlatList<Slide>>(null);
  const [index, setIndex] = useState(0);
  const { completeOnboarding } = useAuth();
  const intro = useIntro();
  const idle = useAvatarIdle();
  const screen2 = useAvatarIntro(idle.hold);
  const screen3 = useGridIntro();
  // Horizontal scroll offset on the native thread: drives Screen 2's depth layers in step with the page.
  const scrollX = useRef(new Animated.Value(0)).current;
  const onScrollX = useMemo(
    () =>
      Animated.event([{ nativeEvent: { contentOffset: { x: scrollX } } }], {
        useNativeDriver: true,
        // Screen 2's entrance starts once the page is committed to arriving (drag or fling), so it plays as it lands.
        listener: (e: NativeSyntheticEvent<NativeScrollEvent>) => {
          const x = e.nativeEvent.contentOffset.x;
          if (x >= (AVATAR_PAGE - 1 + avatarIntro.triggerAt) * width) screen2.start();
          if (x >= (GRID_PAGE - 1 + gridIntro.triggerAt) * width) screen3.start();
        },
      }),
    [scrollX, width, screen2.start, screen3.start],
  );
  const [listHeight, setListHeight] = useState<number>();

  const finish = async () => {
    await completeOnboarding();
    router.replace("/welcome");
  };

  const next = async () => {
    intro.finish();
    screen2.finish();
    if (index + 1 === AVATAR_PAGE) screen2.start();
    idle.want(index + 1 === AVATAR_PAGE);
    screen3.finish();
    if (index + 1 === GRID_PAGE) screen3.start();
    if (index < slides.length - 1) {
      // Update now: momentum-end events don't fire for programmatic scrolls on iOS, and the dots
      // should move with the tap rather than after the slide settles.
      setIndex(index + 1);
      list.current?.scrollToIndex({ index: index + 1, animated: !isReducedMotion() });
    } else {
      await finish();
    }
  };

  const onScroll = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const page = Math.round(e.nativeEvent.contentOffset.x / width);
    setIndex(page);
    idle.want(page === AVATAR_PAGE);
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
      <View style={styles.header}>
        <View style={{ flex: 1 }} />
        <Pressable onPress={finish} hitSlop={10} style={styles.skipBtn}>
          <Text style={styles.skipText}>Skip</Text>
        </Pressable>
      </View>
      <Animated.FlatList
        ref={list}
        data={slides}
        keyExtractor={(s) => s.key}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onScroll={onScrollX}
        scrollEventThrottle={16}
        onLayout={(e) => setListHeight(e.nativeEvent.layout.height)}
        extraData={listHeight}
        onMomentumScrollEnd={onScroll}
        // A swipe means the user is moving on: settle the intro instead of animating under their finger.
        onScrollBeginDrag={() => {
          intro.finish();
          screen2.finish();
          idle.want(false);
          screen3.finish();
        }}
        renderItem={({ item, index: i }) =>
          item.variant === "grid" ? (
            <GridSlide slide={item} width={width} entrance={screen3.values} />
          ) : item.variant === "avatar" ? (
            <AvatarSlide slide={item} width={width} height={listHeight} scrollX={scrollX} page={i} entrance={screen2.values} idle={idle.values} />
          ) : (
            <SlideView
              slide={item}
              width={width}
              intro={i === 0 ? intro.styles : undefined}
              onArtworkLoad={i === 0 ? intro.start : undefined}
            />
          )
        }
      />
      <View style={styles.footer}>
        <Animated.View style={intro.styles.dots}>
          <PageDots count={slides.length} index={index} />
        </Animated.View>
        {/* Pressable from the first frame, even while still fading in. */}
        <Animated.View style={intro.styles.arrow}>
          <NextArrow onPress={next} label={index === slides.length - 1 ? "Get started" : "Next slide"} />
        </Animated.View>
      </View>
    </SafeAreaView>
  );
}

function SlideView({
  slide,
  width,
  intro,
  onArtworkLoad,
}: {
  slide: Slide;
  width: number;
  /** Frame 1 only: entrance styles. Wrappers keep each element's own size, so nothing shifts. */
  intro?: IntroStyles;
  onArtworkLoad?: () => void;
}) {
  const archW = width * 0.82;
  const archH = archW * (570 / 375);
  return (
    <View style={[styles.slide, { width }]}>
      <View style={{ width: archW, height: archH }}>
        <Animated.View style={[StyleSheet.absoluteFill, intro?.backdrop]}>
          <Image source={slide.arch} style={StyleSheet.absoluteFill} contentFit="fill" />
        </Animated.View>
        {slide.variant === "emblem" && (
          <View style={styles.emblemWrap}>
            <Animated.View style={intro?.artwork}>
              <Image
                source={images.emblem}
                style={{ width: archW * 0.9, height: archW * 0.95 }}
                contentFit="contain"
                onLoad={onArtworkLoad}
              />
            </Animated.View>
            <Animated.Text style={[styles.emblemTitle, intro?.title]}>{slide.title}</Animated.Text>
          </View>
        )}
      </View>
    </View>
  );
}

/** Screen 2's position in the pager. */
const AVATAR_PAGE = slides.findIndex((s) => s.variant === "avatar");
/** Once per app launch, like Frame 1: coming back to Screen 2 shows it settled. */
let avatarIntroPlayed = false;

/**
 * Screen 2's one-time entrance (timings in motion/tokens `avatarIntro`), layered under the scroll-linked depth.
 * `start()` is called when the user commits to Screen 2; `finish()` (any later swipe or tap) snaps it to rest.
 * Opacity and transform only, on the native driver; the pager and next button stay live throughout.
 */
function useAvatarIntro(onRunning: (running: boolean) => void) {
  const play = useRef(!avatarIntroPlayed && !isReducedMotion()).current;
  const values = useRef({
    figure: new Animated.Value(play ? 0 : 1),
    face0: new Animated.Value(play ? 0 : 1),
    face1: new Animated.Value(play ? 0 : 1),
    cow: new Animated.Value(play ? 0 : 1),
    title: new Animated.Value(play ? 0 : 1),
  }).current;
  const anim = useRef<Animated.CompositeAnimation | null>(null);
  const state = useRef<"waiting" | "running" | "done">(play ? "waiting" : "done");

  const settle = useCallback(() => {
    state.current = "done";
    anim.current?.stop();
    anim.current = null;
    Object.values(values).forEach((v) => v.setValue(1));
    onRunning(false);
  }, [values, onRunning]);

  const start = useCallback(() => {
    if (state.current !== "waiting") return;
    avatarIntroPlayed = true;
    const t = avatarIntroFor(isReducedMotion());
    if (!t) return settle();
    state.current = "running";
    onRunning(true);
    anim.current = Animated.parallel([
      timing(values.figure, 1, t.figure),
      timing(values.face0, 1, { delay: t.faces.delay, duration: t.faces.duration }),
      timing(values.face1, 1, { delay: t.faces.delay + t.faces.step, duration: t.faces.duration }),
      timing(values.cow, 1, t.cow),
      timing(values.title, 1, t.title),
    ]);
    anim.current.start(({ finished }) => {
      if (!finished) return;
      state.current = "done";
      // The idle takes over from rest, so the figure flows from settling straight into breathing.
      onRunning(false);
    });
  }, [values, settle, onRunning]);

  /** Settles a running entrance. One that hasn't started is left to play when Screen 2 arrives. */
  const finish = useCallback(() => {
    if (state.current === "running") settle();
  }, [settle]);

  useEffect(() => () => anim.current?.stop(), []);
  // Reduce motion switched on part-way through: settle at once.
  const reduced = useReducedMotion();
  useEffect(() => {
    if (reduced) finish();
  }, [reduced, finish]);

  return { values, start, finish };
}

type AvatarEntrance = ReturnType<typeof useAvatarIntro>["values"];

/** Sine in-out: each half-cycle leaves and arrives at zero velocity, so the idle starts and turns without a jolt. */
const wave = Easing.inOut(Easing.sin);

/**
 * Screen 2's idle (motion/tokens `avatarIdle`): breathing and floating for the figure, much smaller drifts for the
 * cow and faces. Every value rests at 0 = the settled layout. Runs only while the user `want`s it (Screen 2 is the
 * settled page) and the entrance isn't `hold`ing it; otherwise eases back to rest. Native driver, cleaned up on unmount.
 */
function useAvatarIdle() {
  const values = useRef({
    breathe: new Animated.Value(0),
    float: new Animated.Value(0),
    cow: new Animated.Value(0),
    faces: new Animated.Value(0),
  }).current;
  const loops = useRef<Animated.CompositeAnimation | null>(null);
  const wanted = useRef(false);
  const held = useRef(false);

  const run = useCallback(() => {
    if (!wanted.current || held.current || loops.current) return;
    const t = avatarIdleFor(isReducedMotion());
    if (!t) return;
    const cycle = (v: Animated.Value, period: number, offset = 0) =>
      Animated.sequence([
        Animated.delay(offset),
        Animated.loop(
          Animated.sequence([
            Animated.timing(v, { toValue: 1, duration: period / 2, easing: wave, useNativeDriver: true }),
            Animated.timing(v, { toValue: 0, duration: period / 2, easing: wave, useNativeDriver: true }),
          ]),
        ),
      ]);
    loops.current = Animated.parallel(
      [
        cycle(values.breathe, t.breathe.period),
        cycle(values.float, t.float.period),
        cycle(values.cow, t.cow.period, t.cow.offset),
        cycle(values.faces, t.faces.period, t.faces.offset),
      ],
      { stopTogether: false },
    );
    loops.current.start();
  }, [values]);

  const rest = useCallback(() => {
    loops.current?.stop();
    loops.current = null;
    for (const v of Object.values(values)) timing(v, 0, { duration: avatarIdle.settle, curve: "move" }).start();
  }, [values]);

  /** Screen 2 is (true) or is no longer (false) the settled page. */
  const want = useCallback(
    (on: boolean) => {
      wanted.current = on;
      if (on) run();
      else rest();
    },
    [run, rest],
  );

  /** The entrance is running: the idle waits for it, then starts from rest. */
  const hold = useCallback(
    (running: boolean) => {
      held.current = running;
      if (!running) run();
    },
    [run],
  );

  useEffect(() => () => loops.current?.stop(), []);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (reduced) rest();
  }, [reduced, rest]);

  return { values, want, hold };
}

type AvatarIdleValues = ReturnType<typeof useAvatarIdle>["values"];

/** Screen 3's position in the pager. */
const GRID_PAGE = slides.findIndex((s) => s.variant === "grid");
/** Once per app launch, like Frames 1 and 2. */
let gridIntroPlayed = false;
/** The five small avatars on Screen 3. */
const GRID_FACES = images.faces.length;

/**
 * Screen 3's one-time entrance (timings in motion/tokens `gridIntro`): `start()` when the user commits to Screen 3,
 * `finish()` (any later swipe or tap) snaps it to rest. Opacity and transform only, on the native driver; nothing
 * loops, and the pager and next button stay live throughout.
 */
function useGridIntro() {
  const play = useRef(!gridIntroPlayed && !isReducedMotion()).current;
  const values = useRef({
    hero: new Animated.Value(play ? 0 : 1),
    faces: Array.from({ length: GRID_FACES }, () => new Animated.Value(play ? 0 : 1)),
    title: new Animated.Value(play ? 0 : 1),
  }).current;
  const anim = useRef<Animated.CompositeAnimation | null>(null);
  const state = useRef<"waiting" | "running" | "done">(play ? "waiting" : "done");
  const all = useCallback(() => [values.hero, ...values.faces, values.title], [values]);

  const settle = useCallback(() => {
    state.current = "done";
    anim.current?.stop();
    anim.current = null;
    for (const v of all()) v.setValue(1);
  }, [all]);

  const start = useCallback(() => {
    if (state.current !== "waiting") return;
    gridIntroPlayed = true;
    const t = gridIntroFor(isReducedMotion());
    if (!t) return settle();
    state.current = "running";
    anim.current = Animated.parallel([
      timing(values.hero, 1, t.hero),
      ...values.faces.map((v, i) => timing(v, 1, { delay: t.faces.delay + i * t.faces.step, duration: t.faces.duration })),
      timing(values.title, 1, t.title),
    ]);
    anim.current.start(({ finished }) => {
      if (finished) state.current = "done";
    });
  }, [values, settle]);

  const finish = useCallback(() => {
    if (state.current === "running") settle();
  }, [settle]);

  useEffect(() => () => anim.current?.stop(), []);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (reduced) finish();
  }, [reduced, finish]);

  return { values, start, finish };
}

type GridEntrance = ReturnType<typeof useGridIntro>["values"];

/** Screen 3, "Ready to explore ?". Layout unchanged from the original slide; each element gets an entrance wrapper. */
function GridSlide({ slide, width, entrance }: { slide: Slide; width: number; entrance: GridEntrance }) {
  const archW = width * 0.82;
  const archH = archW * (570 / 375);
  const enter = useMemo(() => {
    const pop = (v: Animated.Value, s: number) => ({
      opacity: v,
      transform: [{ scale: v.interpolate({ inputRange: [0, 1], outputRange: [s, 1] }) }],
    });
    return {
      hero: pop(entrance.hero, gridIntro.hero.fromScale),
      faces: entrance.faces.map((v) => pop(v, gridIntro.faces.fromScale)),
      title: {
        opacity: entrance.title,
        transform: [{ translateY: entrance.title.interpolate({ inputRange: [0, 1], outputRange: [distance.enter, 0] }) }],
      },
    };
  }, [entrance]);

  return (
    <View style={[styles.slide, { width }]}>
      <View style={{ width: archW, height: archH }}>
        <Image source={slide.arch} style={StyleSheet.absoluteFill} contentFit="fill" />
        <View style={styles.grid}>
          <View style={styles.gridTop}>
            <Animated.View style={enter.hero}>
              <Image source={images.faceBoy} style={{ width: archW * 0.5, height: archW * 0.5, borderRadius: archW * 0.25, backgroundColor: "#E2A4F0" }} contentFit="cover" />
            </Animated.View>
            <View style={{ gap: 10 }}>
              {images.faces.slice(0, 2).map((f: number, i: number) => (
                <Animated.View key={i} style={enter.faces[i]}>
                  <Image source={f} style={{ width: archW * 0.22, height: archW * 0.22 }} contentFit="contain" />
                </Animated.View>
              ))}
            </View>
          </View>
          <View style={styles.gridRow}>
            {images.faces.slice(2).map((f: number, i: number) => (
              <Animated.View key={i} style={enter.faces[i + 2]}>
                <Image source={f} style={{ width: archW * 0.24, height: archW * 0.24 }} contentFit="contain" />
              </Animated.View>
            ))}
          </View>
        </View>
      </View>
      <Animated.Text style={[styles.title, enter.title]}>{slide.title}</Animated.Text>
    </View>
  );
}

/** The arch artwork is 375 × 570 px; its straight walls run from row 90 to row 472. */
const ARCH = { w: 375, h: 570, wallBottom: 473 };
/** Vertical space Screen 2 keeps under the arch for its title: margin + one 30 pt DM Serif line + breathing room. */
const titleBlock = (fontScale: number) => 20 + 42 * fontScale + 12;
const TITLE_MAX_FONT_SCALE = 1.3;

/**
 * Screen 2, "Avatar Platform". Layout is in arch-artwork units (`u` dp per artwork pixel), so the composition holds
 * on every screen width. The figure's flat-cropped right and bottom edges sit exactly on the arch's right wall and
 * the line where the walls end, so the arch reads as a window the figure stands in (as in the mockup).
 *
 * Motion: each layer is an outer view following the scroll (motion/tokens `avatarDepth`) around an inner view
 * carrying the one-time entrance (`avatarIntro`); nested opacity and transforms compose on the native side.
 */
function AvatarSlide({
  slide,
  width,
  height,
  scrollX,
  page,
  entrance,
  idle,
}: {
  slide: Slide;
  width: number;
  /** Height of the pager, once measured. */
  height?: number;
  scrollX: Animated.Value;
  page: number;
  entrance: AvatarEntrance;
  idle: AvatarIdleValues;
}) {
  const reduced = useReducedMotion();
  const fontScale = Math.min(PixelRatio.getFontScale(), TITLE_MAX_FONT_SCALE);
  // Same arch size as Frame 1 wherever it fits, so it never changes size mid-swipe on ordinary phones. On short or
  // wide screens it shrinks just enough for the title to stay clear of the page dots and next button.
  const fitW = height ? ((height - styles.slide.paddingTop - titleBlock(fontScale)) * ARCH.w) / ARCH.h : Infinity;
  const archW = Math.min(width * 0.82, fitW);
  const u = archW / ARCH.w;

  const depth = useMemo(() => {
    const layers = avatarDepthFor(reduced);
    if (!layers) return null;
    // p = page offset from settled (-1: Screen 1 is showing, +1: Screen 3 is showing), as a scroll position.
    const at = (p: number) => (page + p) * width;
    const style = (l: DepthLayer) => ({
      opacity: scrollX.interpolate({
        inputRange: [at(-1), at(-l.hidden), at(-l.visible), at(l.visible), at(l.hidden), at(1)],
        outputRange: [0, 0, 1, 1, 0, 0],
        extrapolate: "clamp",
      }),
      transform: [
        {
          translateX: scrollX.interpolate({
            inputRange: [at(-1), at(0), at(1)],
            outputRange: [l.shift * width, 0, -l.shift * width],
            extrapolate: "clamp",
          }),
        },
      ],
    });
    return { ghosts: style(layers.ghosts), figure: style(layers.figure), title: style(layers.title), cow: style(layers.cow) };
  }, [reduced, scrollX, page, width]);

  const enter = useMemo(() => {
    const from = (v: Animated.Value, start: number) => v.interpolate({ inputRange: [0, 1], outputRange: [start, 1] });
    const rise = (v: Animated.Value) => v.interpolate({ inputRange: [0, 1], outputRange: [distance.enter, 0] });
    return {
      // Grows from the corner where it meets the walls: the cut edges stay on the arch, the head rises gently.
      figure: {
        opacity: entrance.figure,
        transform: [
          { translateY: entrance.figure.interpolate({ inputRange: [0, 1], outputRange: [avatarIntro.figure.fromOffset, 0] }) },
          { scale: from(entrance.figure, avatarIntro.figure.fromScale) },
        ],
        transformOrigin: "right bottom",
      },
      face0: { opacity: entrance.face0 },
      face1: { opacity: entrance.face1 },
      cow: { opacity: entrance.cow, transform: [{ scale: from(entrance.cow, avatarIntro.cow.fromScale) }] },
      title: { opacity: entrance.title, transform: [{ translateY: rise(entrance.title) }] },
    };
  }, [entrance]);

  const still = useMemo(() => {
    const drift = (v: Animated.Value, dp: number) => v.interpolate({ inputRange: [0, 1], outputRange: [0, dp] });
    const { breathe, float, cow, faces } = avatarIdle;
    return {
      // Swells from the base, where the figure is cut at the wall line; any growth past the walls is clipped.
      figure: {
        transform: [
          { translateY: drift(idle.float, -float.amount) },
          { scale: idle.breathe.interpolate({ inputRange: [0, 1], outputRange: [1, 1 + breathe.amount] }) },
        ],
        transformOrigin: "center bottom",
      },
      cow: { transform: [{ translateY: drift(idle.cow, -cow.amount) }] },
      // The two faces drift in opposite directions, so the background never moves as one block.
      face0: { transform: [{ translateY: drift(idle.faces, -faces.amount) }] },
      face1: { transform: [{ translateY: drift(idle.faces, faces.amount) }] },
    };
  }, [idle]);

  return (
    <View style={[styles.slide, { width }]}>
      <View style={{ width: archW, height: ARCH.h * u }}>
        <Image source={slide.arch} style={StyleSheet.absoluteFill} contentFit="fill" />
        {/* Clipped at the walls, so the figure and faces slide behind the arch's edge rather than over the page. */}
        <View style={[styles.archWindow, { height: ARCH.wallBottom * u }]}>
          <Animated.View style={[StyleSheet.absoluteFill, depth?.ghosts]}>
            <Animated.View style={[styles.ghostBox, { left: -8 * u, top: 150 * u, width: 135 * u, height: 135 * u }, enter.face0]}>
              <Animated.View style={[StyleSheet.absoluteFill, still.face0]}>
                <Image source={images.faceSikh} style={styles.ghostImage} />
              </Animated.View>
            </Animated.View>
            <Animated.View style={[styles.ghostBox, { left: 270 * u, top: 88 * u, width: 150 * u, height: 150 * u }, enter.face1]}>
              <Animated.View style={[StyleSheet.absoluteFill, still.face1]}>
                <Image source={images.faceHijab} style={styles.ghostImage} />
              </Animated.View>
            </Animated.View>
          </Animated.View>
          <Animated.View style={[styles.figure, { width: 330 * u, height: 470 * u }, depth?.figure]}>
            <Animated.View style={[StyleSheet.absoluteFill, enter.figure]}>
              <Animated.View style={[StyleSheet.absoluteFill, still.figure]}>
                <Image source={images.sikhMan} style={StyleSheet.absoluteFill} contentFit="contain" />
              </Animated.View>
            </Animated.View>
          </Animated.View>
        </View>
        <Animated.View style={[styles.cow, { left: -50 * u, top: -15 * u, width: 190 * u, height: 171 * u }, depth?.cow]}>
          <Animated.View style={[StyleSheet.absoluteFill, enter.cow]}>
            <Animated.View style={[StyleSheet.absoluteFill, still.cow]}>
              <Image source={images.cow} style={StyleSheet.absoluteFill} contentFit="contain" />
            </Animated.View>
          </Animated.View>
        </Animated.View>
      </View>
      <Animated.View style={enter.title}>
        <Animated.Text
          style={[styles.title, depth?.title]}
          numberOfLines={1}
          adjustsFontSizeToFit
          minimumFontScale={0.8}
          maxFontSizeMultiplier={TITLE_MAX_FONT_SCALE}
        >
          {slide.title}
        </Animated.Text>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "flex-end",
    paddingHorizontal: 24,
    paddingTop: 12,
  },
  skipBtn: {
    paddingVertical: 6,
    paddingHorizontal: 12,
  },
  skipText: {
    fontFamily: fonts.medium,
    fontSize: 14,
    color: colors.textMuted,
  },
  slide: { alignItems: "center", paddingTop: 12 },
  emblemWrap: { flex: 1, alignItems: "center", justifyContent: "center", paddingTop: 12 },
  emblemTitle: { fontFamily: fonts.display, fontSize: 26, color: colors.text, marginTop: -8 },
  ghostBox: { position: "absolute" },
  /** Faint: on the image, so the entrance fade on its wrapper multiplies with it instead of replacing it. */
  ghostImage: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0, opacity: 0.35 },
  archWindow: { position: "absolute", top: 0, left: 0, right: 0, overflow: "hidden" },
  figure: { position: "absolute", right: 0, bottom: 0 },
  cow: { position: "absolute" },
  title: { fontFamily: fonts.display, fontSize: 30, color: colors.text, marginTop: 20 },
  grid: { flex: 1, justifyContent: "center", paddingHorizontal: 18, gap: 14 },
  gridTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  gridRow: { flexDirection: "row", justifyContent: "space-between" },
  footer: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: 28, paddingBottom: 20 },
});
