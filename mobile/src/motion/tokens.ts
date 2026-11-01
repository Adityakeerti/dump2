/**
 * Motion tokens and policy: the only durations, curves and distances the app animates with.
 *
 * Principles (see docs/motion.md):
 * - Motion answers a user action or explains a change. Nothing moves on its own or loops (one approved exception:
 *   the onboarding Screen 2 hero's idle, `avatarIdle`).
 * - Feedback starts on touch-down; exits are instant; no animation ever gates input.
 * - Only opacity and transform are animated, on the native driver, so a busy JS thread cannot drop frames.
 * - With the OS reduce-motion setting on, nothing slides, scales or flies; short cross-fades remain.
 * - Emergency surfaces (SOS, crash countdown, cancel) use none of this: no entrance, no delay, no scale.
 *
 * Kept free of react-native imports so the policy can be unit-tested under plain Node.
 */

export const duration = {
  /** Touch-down response; short enough to read as immediate. */
  pressIn: 80,
  /** Release back to rest. */
  pressOut: 160,
  /** Small in-place state changes: tab pill, page dots, segmented thumb, cross-fades. */
  fast: 150,
  /** Content arriving after a screen is already visible. */
  base: 220,
  /** Map camera moves (recentre, jump to a search result). */
  map: 650,
} as const;

/** Cubic-bezier control points. `enter`: decelerating ease-out; `move`: symmetric ease-in-out. */
export const curve = {
  enter: [0.2, 0, 0, 1],
  move: [0.4, 0, 0.2, 1],
} as const;

export const distance = {
  /** How far arriving content travels into place, in dp. */
  enter: 8,
} as const;

export const scale = {
  /** Pressed size for buttons, cards, chips and floating buttons. */
  press: 0.97,
  /** Starting width fraction of the active tab pill as it grows into place. */
  pill: 0.6,
} as const;

export const opacity = {
  /** Icon-only buttons and text links while pressed. */
  dim: 0.5,
  /** Scale feedback replaced by a light dim when reduce motion is on. */
  reducedPress: 0.8,
} as const;

export const stagger = {
  step: 35,
  /** Items past this index appear with the last staggered one, so a long list never trickles in. */
  maxItems: 6,
} as const;

/**
 * The one choreographed sequence in the app: the first onboarding frame, shown once per install.
 * Windows are ms from the screen mounting. It never gates input: the slide can be swiped and the next
 * button pressed from the first frame, and any interaction completes the sequence instantly.
 */
export const intro = {
  /** Stage 1: the arch backdrop settles in behind the artwork (the white page itself is never animated). */
  backdrop: { delay: 0, duration: 300 },
  /** Stage 2: the emblem artwork (lotus, lions and its baked-in caption). */
  artwork: { delay: 300, duration: 700, fromScale: 0.92 },
  /** Stage 3: the "Saarthi 26" wordmark rises the standard enter distance. */
  title: { delay: 1000, duration: 500 },
  /** Stage 4: page dots and the next button. */
  controls: { delay: 1500, duration: 300, fromScale: 0.92 },
} as const;

export type IntroStage = { delay: number; duration: number; fromScale: number; fromOffset: number };

/** Intro stages for the reduce-motion preference: reduced = everything cross-fades together, nothing moves. */
export function introFor(reduced: boolean): Record<keyof typeof intro, IntroStage> {
  const stage = (s: { delay: number; duration: number; fromScale?: number }, offset = 0): IntroStage =>
    reduced
      ? { delay: 0, duration: duration.fast, fromScale: 1, fromOffset: 0 }
      : { delay: s.delay, duration: s.duration, fromScale: s.fromScale ?? 1, fromOffset: offset };
  return {
    backdrop: stage(intro.backdrop),
    artwork: stage(intro.artwork),
    title: stage(intro.title, distance.enter),
    controls: stage(intro.controls),
  };
}


/**
 * Onboarding Screen 2 ("Avatar Platform") is only ever reached by paging, so its motion is tied to the scroll
 * position rather than a clock: the swipe, or the Next button's scroll, *is* the animation. Each layer travels at
 * a slightly different speed from the page and fades over its own stretch of page travel, so the art assembles
 * back-to-front as the page arrives and clears front-to-back as it leaves for Screen 3. Every layer is exactly at
 * rest whenever the page is settled: nothing plays after the finger lifts, nothing replays, nothing gates input.
 *
 * - `shift`: extra travel at one full page of offset, as a fraction of the page width. Positive moves faster
 *   than the page (reads as in front of it), negative slower (behind it).
 * - `visible` / `hidden`: page offset (0 = settled, 1 = a whole page away) at which the layer is fully opaque /
 *   fully transparent. Smaller `hidden` = arrives later; that ordering is the stagger.
 */
export const avatarDepth = {
  /** Faded neighbour faces inside the arch: the far layer, arrives first. */
  ghosts: { shift: -0.05, visible: 0.4, hidden: 0.9 },
  /** The figure: the subject, settles into the arch window. */
  figure: { shift: 0.1, visible: 0.25, hidden: 0.8 },
  /** "Avatar Platform". */
  title: { shift: 0.05, visible: 0.15, hidden: 0.65 },
  /** The cow perched on the arch shoulder: the nearest layer, lands last. */
  cow: { shift: 0.16, visible: 0.05, hidden: 0.55 },
} as const;

export type DepthLayer = { shift: number; visible: number; hidden: number };

/** Screen 2 depth for the reduce-motion preference: null = layers sit still and page with the screen. */
export function avatarDepthFor(reduced: boolean): Record<keyof typeof avatarDepth, DepthLayer> | null {
  return reduced ? null : avatarDepth;
}

/**
 * Screen 2's one-time entrance, layered on the scroll-linked depth above. Plays once per launch, starting the
 * moment the user commits to Screen 2 (Next tapped, or the page dragged `triggerAt` of the way over), so it
 * runs alongside the page's arrival rather than after it. Any further swipe or tap settles it instantly; the
 * page dots and next button are persistent controls and never re-enter. Windows are ms from the trigger.
 */
export const avatarIntro = {
  /** The figure grows into place from its bottom-right corner, where it meets the arch walls, rising `fromOffset` dp. */
  figure: { delay: 0, duration: 700, fromScale: 0.95, fromOffset: 6 },
  /** The two faint faces, one after the other. */
  faces: { delay: 150, duration: 450, step: 80 },
  /** The cow settles onto the arch shoulder. */
  cow: { delay: 250, duration: 500, fromScale: 0.9 },
  /** "Avatar Platform" rises the standard enter distance. */
  title: { delay: 450, duration: 450 },
  /** Fraction of a page the drag towards Screen 2 must cover before the entrance starts. */
  triggerAt: 0.3,
} as const;

/**
 * Screen 2 idle: the app's one deliberate exception to "nothing moves on its own" (approved for this onboarding
 * hero, 2026-10-31). The figure is a single flat image, so all of it is whole-figure motion: uniform scale and
 * vertical drift only, never independent limbs or a non-uniform stretch. Supporting art moves far less, so the
 * figure stays the focus. Runs only while Screen 2 is the settled page, starts from rest at zero velocity when the
 * entrance completes, eases back to rest (`settle`) as soon as the user swipes or taps, and is off under reduce
 * motion. Amplitudes in dp (scale: added fraction); periods are a full cycle in ms, deliberately unrelated so the
 * layers never fall into a visible lockstep.
 */
export const avatarIdle = {
  /** Breathing: a barely-there uniform swell from the base of the figure. */
  breathe: { amount: 0.01, period: 4200 },
  /** Floating: a slow rise and fall of the whole figure. */
  float: { amount: 3, period: 5600 },
  /** The cow: half the figure's float, its own rhythm. */
  cow: { amount: 1.5, period: 4800, offset: 700 },
  /** The faint faces: a third of the figure's float, slowest of all. */
  faces: { amount: 1, period: 7000, offset: 1400 },
  /** Easing back to rest when the user moves on. */
  settle: 300,
} as const;

/** Screen 2 idle for the reduce-motion preference: null = still. */
export function avatarIdleFor(reduced: boolean): typeof avatarIdle | null {
  return reduced ? null : avatarIdle;
}

/** Screen 2 entrance for the reduce-motion preference: null = no entrance, content is simply there. */
export function avatarIntroFor(reduced: boolean): typeof avatarIntro | null {
  return reduced ? null : avatarIntro;
}

/**
 * Screen 3 ("Ready to explore ?") one-time entrance: same pattern as Screen 2's. Starts the moment the user commits
 * to Screen 3 (Next on Screen 2, or the page dragged `triggerAt` of the way over), plays once per launch, any further
 * swipe or tap settles it instantly. The arch arrives with the page and the dots/next button are persistent
 * controls, so neither re-enters. No idle motion. Windows are ms from the trigger.
 */
export const gridIntro = {
  /** The large avatar: the subject, scales up into place. */
  hero: { delay: 0, duration: 600, fromScale: 0.94 },
  /** The five small avatars, top-right column first, then the bottom row left to right. */
  faces: { delay: 200, duration: 400, step: 60, fromScale: 0.9 },
  /** "Ready to explore ?" rises the standard enter distance. */
  title: { delay: 500, duration: 450 },
  triggerAt: 0.3,
} as const;

/** Screen 3 entrance for the reduce-motion preference: null = no entrance, content is simply there. */
export function gridIntroFor(reduced: boolean): typeof gridIntro | null {
  return reduced ? null : gridIntro;
}

/**
 * Welcome ("Lets goo .") kite. Arrives with a small lift and turn, floats while the screen is showing, and takes
 * off towards the top-right when the user presses Login: the Login screen cross-fades in while the kite is still
 * leaving. The kite is one flat image (its tail leaves are baked in), so it only ever moves as a whole. The float
 * is an explicitly requested idle (2026-10-31): it runs only while Welcome is focused, and never under reduce motion.
 * Angles in degrees, distances in dp, times in ms.
 */
export const kite = {
  /** Kite, arch panel and title on arrival (ms from the screen appearing). */
  enter: { duration: 400, fromScale: 0.9, fromOffset: 16, fromRotate: -6, panel: 300, titleDelay: 150, title: 300 },
  /** Idle: a slow rise and fall, and a slower sway as if leaning into the wind. */
  float: { amount: 4, period: 3200, tilt: 2, tiltPeriod: 4400 },
  /** Takeoff: accelerating up and to the right, turning, shrinking with distance, fading only at the very end. */
  flight: {
    duration: 750,
    rotateTo: 14,
    scaleTo: 0.55,
    /** Fraction of the flight after which the kite starts to fade. */
    fadeFrom: 0.7,
    /** Login starts cross-fading in this long after takeoff, while the kite is still on screen. */
    navigateAt: 500,
    /** The title clears as the kite leaves; the panel lingers until Login has covered it, so nothing flashes blank. */
    title: 200,
    panelDelay: 250,
    panel: 600,
    /** Wind trails: two quick arcs left behind at the start of the takeoff. */
    trail: 450,
  },
  /** Reduce motion: no flight; the kite fades for this long while Login is already on its way. */
  reducedExit: 150,
} as const;


/** Spinners stay hidden this long, so fast responses never flash a loading state. */
export const loadingDelay = 300;

export const staggerDelay = (index: number): number =>
  Math.max(0, Math.min(Math.floor(index), stagger.maxItems)) * stagger.step;

/** Resolved motion values for the current reduce-motion preference. */
export function motionFor(reduced: boolean) {
  return {
    enterOffset: reduced ? 0 : distance.enter,
    enterDuration: reduced ? duration.fast : duration.base,
    pressScale: reduced ? 1 : scale.press,
    pressOpacity: reduced ? opacity.reducedPress : 1,
    pillFrom: reduced ? 1 : scale.pill,
    mapDuration: reduced ? 0 : duration.map,
    staggerDelay: (index: number) => (reduced ? 0 : staggerDelay(index)),
    stackAnimation: reduced ? ("fade" as const) : ("slide_from_right" as const),
  };
}

export type Motion = ReturnType<typeof motionFor>;
