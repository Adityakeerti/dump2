import { useEffect, useRef, useState } from "react";
import { fmt, simClock } from "../lib/format.js";

// Time-space diagram of arterial speed: x = simulated time, y = position (west at bottom).
// Sequential single-hue ramp on congestion = 1 - v/v_free; shockwaves show as diagonal bands.
const RAMP_LIGHT = [[250, 243, 236], [178, 54, 26]];
const RAMP_DARK = [[34, 38, 35], [236, 110, 70]];

function colorFor(c, dark) {
  const [a, b] = dark ? RAMP_DARK : RAMP_LIGHT;
  const t = Math.max(0, Math.min(1, c));
  return `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(",")})`;
}

export default function Heatmap({ history, topology, height = 220 }) {
  const ref = useRef(null);
  const [tip, setTip] = useState(null);
  const cpl = topology?.cells_per_link || 8;
  const nCells = topology?.arterial_cells?.length || 0;

  useEffect(() => {
    const cv = ref.current;
    if (!cv || !nCells) return;
    const dark = document.documentElement.dataset.theme === "dark" ||
      (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
    const cols = Math.max(history.length, 1);
    cv.width = cols;
    cv.height = nCells;
    const ctx = cv.getContext("2d");
    ctx.fillStyle = dark ? "#222824" : "#f6f6f4";
    ctx.fillRect(0, 0, cols, nCells);
    history.forEach((row, x) => {
      row.v.forEach((r, i) => {
        ctx.fillStyle = colorFor(1 - r, dark);
        ctx.fillRect(x, nCells - 1 - i, 1, 1);
      });
    });
  }, [history, nCells]);

  if (!nCells) return null;
  const junctionRows = Array.from({ length: topology.num_junctions }, (_, j) => (j + 1) * cpl);

  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.floor(((e.clientX - rect.left) / rect.width) * history.length);
    const yCell = nCells - 1 - Math.floor(((e.clientY - rect.top) / rect.height) * nCells);
    const row = history[x];
    if (!row) return setTip(null);
    setTip({ left: e.clientX - rect.left + 12, top: e.clientY - rect.top + 8, t: row.t, cell: yCell, r: row.v[yCell] });
  };

  return (
    <div className="chart-wrap" onMouseMove={onMove} onMouseLeave={() => setTip(null)}>
      <canvas ref={ref} className="heat" style={{ height }} aria-label="Time-space diagram of arterial speed" />
      {junctionRows.map((c, j) => (
        <div key={j} style={{ position: "absolute", left: 0, right: 0, top: `${(1 - c / nCells) * 100}%`, borderTop: "1px dashed var(--axis)", pointerEvents: "none" }}>
          <span className="muted" style={{ fontSize: 9, position: "absolute", left: 4, top: -12 }}>J{j + 1}</span>
        </div>
      ))}
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10 }} className="muted num">
        <span>{history[0] ? simClock(history[0].t).full : ""} · west gateway at bottom, flow upward</span>
        <span>{history.at(-1) ? simClock(history.at(-1).t).full : ""}</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, marginTop: 4 }} className="muted">
        free flow
        <span style={{ width: 90, height: 8, borderRadius: 4, background: `linear-gradient(90deg, ${colorFor(0, false)}, ${colorFor(1, false)})`, border: "1px solid var(--line)" }} />
        stopped
      </div>
      {tip && (
        <div className="chart-tip num" style={{ left: tip.left, top: tip.top }}>
          {simClock(tip.t).full} · cell {tip.cell}<br />speed {fmt(tip.r * 100, 0)}% of free flow
        </div>
      )}
    </div>
  );
}
