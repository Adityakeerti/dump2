# CitySense motion standard

Applies to every CitySense client: the citizen mobile app (implemented in `mobile/src/motion/`) and the
operator dashboard (to be built; follow the web mapping below).

**Golden rule:** people should feel that the app is smooth, not notice that it animates. If an animation
makes an interaction slower, distracting or less clear, remove it. CitySense is a public-safety tool:
clarity, responsiveness, accessibility and reliability come before visual effect.

## Rules

1. **Motion has a reason.** It answers a touch, shows where something came from, or eases in content
   that arrived late. Nothing moves on its own: no idle loops, pulsing indicators, bouncing or spinning
   decoration. (System loading spinners are the one moving element, and they appear only after 300 ms.)
2. **Feedback is immediate.** Every control reacts on touch-down (80 ms), and every press shows
   feedback for at least 130 ms so even quick taps are visible.
3. **Nothing waits for an animation.** Actions fire immediately; content is interactive from its first
   frame; exits are instant. Animations are interruptible.
4. **One set of timings and curves** (below). No ad-hoc durations.
5. **Performance first.** Animate only opacity and transform, off the main/JS thread (native driver on
   mobile; `transform`/`opacity` with CSS on web). No layout animation of large regions.
6. **Respect reduce motion.** With the OS setting on: no sliding, scaling, zooming or camera flights;
   short cross-fades remain; screen pushes become fades.
7. **No flicker, no layout jumps.** Don't flash empty or loading states before data arrives; keep stale
   results visible while refreshing; let neighbours glide when rows are added or removed.
8. **Emergency surfaces are exempt from motion.** SOS, crash-detection countdowns, cancel/abort and
   dispatch controls render instantly: no entrance animation, no stagger, no delay, no scale feedback
   (`Tap feedback="none"` with an instant pressed colour). The countdown is visible on the first frame.

## Tokens

| Token | Value | Use |
|---|---|---|
| `pressIn` | 80 ms | touch-down response |
| `pressOut` | 160 ms | release back to rest |
| `fast` | 150 ms | in-place state changes: tab pill, segmented thumb, page dots, tab cross-fade |
| `base` | 220 ms | content arriving after a screen is visible; splash fade |
| `map` | 650 ms | map camera moves (0 under reduce motion) |
| curve `enter` | `cubic-bezier(0.2, 0, 0, 1)` | things appearing or responding to touch |
| curve `move` | `cubic-bezier(0.4, 0, 0.2, 1)` | things changing state in place |
| enter distance | 8 dp/px | arriving content rises (menus hanging from a bar drop) |
| press scale | 0.97 | buttons, cards, chips, floating buttons |
| dim | 50 % opacity | icon-only buttons, text links |
| highlight | `rgba(15,23,42,0.06)` | full-width rows, tab items |
| stagger | 35 ms × index, capped at 6 | first appearance of a list only |
| loading delay | 300 ms | before any spinner is shown |

Springs are not used: every response here is short enough that a well-chosen ease-out reads as
physical, and it never overshoots.

## Mobile implementation (`mobile/src/motion/`)

- `tokens.ts`: the values above plus the reduce-motion policy (`motionFor`), unit-tested by `npm test`.
- `reducedMotion.ts`: one app-wide subscription to the OS setting; `useReducedMotion()` / `isReducedMotion()`.
- `Tap`: the only pressable; `feedback="scale" | "highlight" | "dim" | "none"`.
- `FadeIn`: mount-only entrance with optional stagger; `animate={false}` renders in place;
  `useFirstBatch()` limits list entrances to the first batch so scrolling never trickles rows in.
- `animateNextLayout()`: smooth row insert/remove; no-op under reduce motion.
- Navigation: native stack slide (fade under reduce motion); 150 ms cross-fade between tabs except the
  map tab, whose GL surface ignores view opacity on Android and would flicker.

## Dashboard (web) mapping

- Define the tokens once as CSS custom properties (`--motion-fast: 150ms; --ease-enter: cubic-bezier(0.2,0,0,1)` …)
  and use them in every transition.
- Wrap all movement in `@media (prefers-reduced-motion: no-preference)`; under `reduce`, keep opacity
  transitions at `--motion-fast` and drop transforms.
- Press feedback: `:active` (scale 0.97 or tint) with `--motion-press-in`; hover tints only on
  pointer devices (`@media (hover: hover)`).
- Incident drawers and approval panels slide 8–16 px with `--motion-base`; the map stays put.
- Live incident lists: new rows fade in at the top; existing rows never re-animate on refresh.
- Alerts that need operator action (new critical incident, approval required) appear instantly and
  stay visible; draw attention with colour and position, never with looping motion.
