/**
 * The native splash dissolves for a fixed time after the root layout hides it. Entrance choreography on
 * the first screen waits out that dissolve, otherwise its opening stage plays underneath the splash and only
 * its tail is visible (it reads as a pop instead of a fade).
 *
 * No imports, so it can be unit-tested under plain Node.
 */
let dissolveEndsAt = 0;

/**
 * The native dissolve does not start when JS calls hide(): Android only clears a flag, and the exit animation
 * begins at the next native frame draw, then fades with an accelerating curve (mostly opaque for its first
 * half). Measured on the Android emulator, content under the splash stays hidden ~100 ms longer than the
 * configured duration. Too small a margin only means a slight cross-fade under the splash; too large, up to
 * this long of plain white page. Neither blocks input.
 */
export const SPLASH_START_LATENCY_MS = 100;

/** Call at the moment the splash is told to hide, with the dissolve duration it was configured with. */
export function splashHiding(dissolveMs: number, now: number = Date.now()) {
  dissolveEndsAt = now + dissolveMs + SPLASH_START_LATENCY_MS;
}

/** Milliseconds until the splash has fully dissolved; 0 once it has, or if it never ran. */
export function splashRemaining(now: number = Date.now()) {
  return Math.max(0, dissolveEndsAt - now);
}
