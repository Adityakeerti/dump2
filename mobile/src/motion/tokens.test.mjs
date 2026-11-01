// Motion policy tests. Run: npm test (node --test, no extra dependencies).
import assert from "node:assert/strict";
import { test } from "node:test";
import { kite, gridIntro, gridIntroFor, avatarDepth, avatarDepthFor, avatarIdle, avatarIdleFor, avatarIntro, avatarIntroFor, distance, duration, introFor, loadingDelay, motionFor, scale, stagger, staggerDelay } from "./tokens.ts";

test("touch feedback reads as immediate", () => {
  assert.ok(duration.pressIn <= 100, "press-in must land within ~6 frames");
  assert.ok(duration.pressOut <= 200);
});

test("no content animation is long enough to feel like waiting", () => {
  for (const [name, ms] of Object.entries(duration)) {
    if (name === "map") continue; // camera flights travel distance; still well under a second
    assert.ok(ms <= 250, `${name} is ${ms}ms`);
  }
  assert.ok(duration.map < 1000);
});

test("stagger is capped so long lists never trickle in", () => {
  assert.equal(staggerDelay(0), 0);
  assert.equal(staggerDelay(1), stagger.step);
  assert.equal(staggerDelay(500), stagger.maxItems * stagger.step);
  assert.equal(staggerDelay(-3), 0);
  assert.ok(stagger.maxItems * stagger.step + duration.base <= 450, "last staggered item settles in under half a second");
});

test("press scale is subtle", () => {
  assert.ok(scale.press >= 0.95 && scale.press < 1);
});

test("reduce motion removes movement but keeps short fades", () => {
  const m = motionFor(true);
  assert.equal(m.enterOffset, 0);
  assert.equal(m.pressScale, 1);
  assert.equal(m.pillFrom, 1);
  assert.equal(m.mapDuration, 0);
  assert.equal(m.staggerDelay(5), 0);
  assert.equal(m.stackAnimation, "fade");
  assert.ok(m.enterDuration > 0 && m.enterDuration <= duration.fast);
  assert.ok(m.pressOpacity < 1, "pressed controls still respond visibly");
});

test("default motion keeps native slide navigation", () => {
  const m = motionFor(false);
  assert.equal(m.stackAnimation, "slide_from_right");
  assert.ok(m.enterOffset > 0 && m.enterOffset <= 12);
  assert.equal(m.pressOpacity, 1);
});

test("spinners wait before appearing so fast loads do not flash", () => {
  assert.ok(loadingDelay >= 200 && loadingDelay <= 500);
});

test("onboarding intro runs its four stages in order and is fully settled by 1.8 s", () => {
  const s = introFor(false);
  const order = [s.backdrop, s.artwork, s.title, s.controls];
  for (let i = 1; i < order.length; i++) {
    assert.ok(order[i].delay >= order[i - 1].delay, "stages start in sequence");
  }
  assert.equal(s.artwork.delay, 300);
  assert.equal(s.title.delay, 1000);
  assert.equal(s.controls.delay, 1500);
  const end = Math.max(...order.map((x) => x.delay + x.duration));
  assert.ok(end <= 1800, `intro ends at ${end}ms`);
});

test("onboarding intro motion stays subtle", () => {
  const s = introFor(false);
  for (const [name, st] of Object.entries(s)) {
    assert.ok(st.fromScale >= 0.9 && st.fromScale <= 1, `${name} scales from ${st.fromScale}`);
    assert.ok(Math.abs(st.fromOffset) <= 12, `${name} travels ${st.fromOffset}`);
  }
  assert.equal(s.title.fromOffset, distance.enter, "the wordmark rises the standard enter distance");
  assert.equal(s.backdrop.fromScale, 1, "the backdrop only fades");
});

test("reduce motion collapses the intro to one short cross-fade with no movement or waiting", () => {
  for (const [name, st] of Object.entries(introFor(true))) {
    assert.equal(st.delay, 0, `${name} must not wait`);
    assert.equal(st.fromScale, 1, `${name} must not scale`);
    assert.equal(st.fromOffset, 0, `${name} must not move`);
    assert.ok(st.duration > 0 && st.duration <= duration.fast);
  }
});

test("first-screen choreography waits out the splash dissolve, and never longer", async () => {
  const { splashHiding, splashRemaining, SPLASH_START_LATENCY_MS } = await import("./splash.ts");
  const total = duration.base + SPLASH_START_LATENCY_MS;
  assert.equal(splashRemaining(1_000), 0, "no wait when the splash never ran");
  splashHiding(duration.base, 5_000);
  assert.equal(splashRemaining(5_000), total);
  assert.equal(splashRemaining(5_000 + 100), total - 100);
  assert.equal(splashRemaining(5_000 + total + 1), 0, "no wait once the dissolve has ended");
  assert.ok(total <= 400, "never holds the first screen back noticeably");
});


test("Screen 2 depth: every layer settles exactly when the page does, with subtle travel", () => {
  for (const [name, l] of Object.entries(avatarDepth)) {
    assert.ok(Math.abs(l.shift) <= 0.2, `${name} travels ${l.shift} of a page beyond the page itself`);
    assert.ok(l.visible >= 0 && l.visible < l.hidden && l.hidden <= 1, `${name} fade window ${l.visible}..${l.hidden}`);
    assert.ok(l.hidden - l.visible >= 0.4, `${name} fades over enough travel not to pop`);
  }
});

test("Screen 2 depth assembles back-to-front: far layers appear first, the title and cow last", () => {
  const { ghosts, figure, title, cow } = avatarDepth;
  const order = [ghosts, figure, title, cow];
  for (let i = 1; i < order.length; i++) {
    assert.ok(order[i].hidden < order[i - 1].hidden, "each layer starts appearing later than the one behind it");
    assert.ok(order[i].visible < order[i - 1].visible, "and is fully in later");
  }
  assert.ok(ghosts.shift < 0 && figure.shift > 0 && cow.shift > figure.shift, "nearer layers move faster");
});

test("reduce motion: Screen 2 layers page with the screen, no parallax or fades", () => {
  assert.equal(avatarDepthFor(true), null);
  assert.equal(avatarDepthFor(false), avatarDepth);
});

test("Screen 2 entrance: avatar first, then faces and cow, title last, all settled within a second", () => {
  const { figure, faces, cow, title } = avatarIntro;
  assert.ok(figure.delay <= faces.delay && faces.delay <= cow.delay && cow.delay <= title.delay, "stages start in order");
  const ends = [figure.delay + figure.duration, faces.delay + faces.step + faces.duration, cow.delay + cow.duration, title.delay + title.duration];
  assert.ok(Math.max(...ends) <= 1000, `entrance ends at ${Math.max(...ends)}ms`);
  assert.ok(figure.fromScale >= 0.9 && figure.fromScale < 1 && cow.fromScale >= 0.9 && cow.fromScale < 1, "scales stay subtle");
  assert.ok(avatarIntro.triggerAt > 0 && avatarIntro.triggerAt < 0.5, "starts while the page is still arriving");
});

test("reduce motion: Screen 2 has no entrance", () => {
  assert.equal(avatarIntroFor(true), null);
  assert.equal(avatarIntroFor(false), avatarIntro);
});

test("Screen 2 idle stays subtle, slow and centred on the figure", () => {
  const { breathe, float, cow, faces, settle } = avatarIdle;
  assert.ok(breathe.amount > 0 && breathe.amount <= 0.015, "breathing is a barely-there uniform swell");
  assert.ok(float.amount > 0 && float.amount <= 4, `figure floats ${float.amount}dp`);
  assert.ok(cow.amount <= float.amount / 2 && faces.amount < cow.amount, "supporting art moves much less than the figure");
  for (const [name, l] of Object.entries({ breathe, float, cow, faces })) {
    assert.ok(l.period >= 4000, `${name} cycles every ${l.period}ms: slow, never a jitter`);
  }
  assert.equal(new Set([breathe.period, float.period, cow.period, faces.period]).size, 4, "no two layers move in lockstep");
  assert.ok(settle <= duration.base * 1.5, "returns to rest quickly when the user moves on");
});

test("reduce motion: Screen 2 has no idle motion", () => {
  assert.equal(avatarIdleFor(true), null);
  assert.equal(avatarIdleFor(false), avatarIdle);
});

test("Screen 3 entrance: hero, then staggered avatars, title last, settled within a second", () => {
  const { hero, faces, title } = gridIntro;
  assert.ok(hero.delay <= faces.delay && faces.delay <= title.delay, "stages start in order");
  const lastFace = faces.delay + 4 * faces.step + faces.duration;
  const end = Math.max(hero.delay + hero.duration, lastFace, title.delay + title.duration);
  assert.ok(end <= 1000, `entrance ends at ${end}ms`);
  assert.ok(hero.fromScale >= 0.9 && faces.fromScale >= 0.9, "scales stay subtle");
  assert.ok(gridIntro.triggerAt > 0 && gridIntro.triggerAt < 0.5);
});

test("reduce motion: Screen 3 has no entrance", () => {
  assert.equal(gridIntroFor(true), null);
  assert.equal(gridIntroFor(false), gridIntro);
});

test("Welcome kite: quick entrance, gentle float, takeoff that hands over to Login before it ends", () => {
  const { enter, float, flight, reducedExit } = kite;
  assert.ok(enter.duration <= 450 && enter.fromScale >= 0.85 && Math.abs(enter.fromRotate) <= 8);
  assert.ok(float.amount <= 6 && float.tilt <= 3 && float.period >= 2500 && float.tiltPeriod !== float.period, "float stays lightweight");
  assert.ok(flight.duration <= 800, "takeoff never makes Login wait long");
  assert.ok(flight.navigateAt < flight.duration, "Login starts appearing before the kite has gone");
  assert.ok(flight.fadeFrom >= 0.6, "the kite visibly flies out rather than dissolving");
  assert.ok(flight.scaleTo >= 0.4 && flight.scaleTo < 1 && flight.rotateTo <= 20);
  assert.ok(reducedExit <= duration.fast);
});

