export const fmt = (v, d = 1) => (v === null || v === undefined || Number.isNaN(v) ? "–" : Number(v).toFixed(d));

export function simClock(simSec, start = "07:30") {
  const [h, m] = start.split(":").map(Number);
  const total = h * 60 + m + Math.floor(simSec / 60);
  const hh = Math.floor(total / 60) % 24;
  return { hm: `${String(((hh + 11) % 12) + 1).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`, ampm: hh < 12 ? "am" : "pm", full: `${String(hh).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}` };
}

export const wallTime = (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export const POLICY_VAR = { DoubleDQN: "var(--s1)", "fixed-time": "var(--s2)", "longest-queue": "var(--s3)", "max-pressure": "var(--s4)" };
export const POLICY_LABEL = { DoubleDQN: "Double DQN (learning)", "fixed-time": "Fixed-time", "longest-queue": "Longest-queue", "max-pressure": "Max-pressure" };

// People-cluster identity colours (avatars on the map); fixed order by cluster index.
const CLUSTER_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#c98500", "#d55181", "#008300", "#6250d6", "#e34948"];
export const clusterColor = (i) => CLUSTER_COLORS[i % CLUSTER_COLORS.length];
export const initials = (name) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

// Traffic state of a cell from speed ratio (v / v_free) — status colours, always with a legend.
export function speedColor(r, factor = 0.6) {
  if (r >= 0.9) return "#0ca30c";
  if (r >= factor) return "#fab219";
  if (r >= factor / 2) return "#ec835a";
  return "#d03b3b";
}

export const linkLabel = (i, n) => `${i === 0 ? "West gateway" : `J${i}`}→${i === n ? "East exit" : `J${i + 1}`}`;
