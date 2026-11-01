import { useState } from "react";
import { fmt } from "../lib/format.js";

// Multi-series line chart with crosshair tooltip and direct end labels.
// series: [{ key, label, color, values: [number|null] }], x = index (episode).
export default function LineChart({ series, xLabels, height = 220, yLabel, digits = 1 }) {
  const [hover, setHover] = useState(null);
  const W = 640, H = height, m = { l: 44, r: 128, t: 10, b: 26 };
  const n = Math.max(...series.map((s) => s.values.length), 0);
  const all = series.flatMap((s) => s.values.filter((v) => v !== null && v !== undefined));
  if (!n || !all.length) return <div className="empty">No completed episodes yet — the first finishes after 30 simulated minutes.</div>;
  const lo = Math.min(0, ...all), hi = Math.max(...all) * 1.08 || 1;
  const x = (i) => m.l + (n === 1 ? (W - m.l - m.r) / 2 : (i / (n - 1)) * (W - m.l - m.r));
  const y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
  const ticks = Array.from({ length: 5 }, (_, i) => lo + ((hi - lo) * i) / 4);
  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const i = Math.round(((px - m.l) / (W - m.l - m.r)) * (n - 1));
    setHover(i >= 0 && i < n ? i : null);
  };
  // de-overlap end labels
  const ends = series.map((s) => ({ s, v: [...s.values].reverse().find((v) => v !== null && v !== undefined) }))
    .filter((e) => e.v !== undefined).map((e) => ({ ...e, py: y(e.v) })).sort((a, b) => a.py - b.py);
  ends.forEach((e, i) => { if (i && e.py - ends[i - 1].py < 13) e.py = ends[i - 1].py + 13; });

  return (
    <div className="chart-wrap">
      <div className="legend">{series.map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>)}</div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" onMouseMove={onMove} onMouseLeave={() => setHover(null)} role="img" aria-label={yLabel}>
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={m.l} x2={W - m.r} y1={y(t)} y2={y(t)} stroke="var(--grid)" strokeWidth="1" />
            <text x={m.l - 6} y={y(t) + 3} textAnchor="end" fontSize="10" fill="var(--muted)" className="num">{fmt(t, hi - lo < 5 ? 2 : 0)}</text>
          </g>
        ))}
        <line x1={m.l} x2={W - m.r} y1={H - m.b} y2={H - m.b} stroke="var(--axis)" />
        {xLabels.map((l, i) => (n <= 16 || i % Math.ceil(n / 16) === 0) && (
          <text key={i} x={x(i)} y={H - 8} textAnchor="middle" fontSize="10" fill="var(--muted)" className="num">{l}</text>
        ))}
        <text x={m.l} y={H - 8} textAnchor="end" fontSize="10" fill="var(--muted)" dx="-6">ep</text>
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={m.t} y2={H - m.b} stroke="var(--axis)" />}
        {series.map((s) => {
          const pts = s.values.map((v, i) => (v === null || v === undefined ? null : [x(i), y(v)]));
          const d = pts.reduce((acc, p, i) => (p ? acc + `${acc && pts[i - 1] ? "L" : "M"}${p[0]},${p[1]}` : acc), "");
          return (
            <g key={s.key}>
              <path d={d} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" />
              {pts.map((p, i) => p && (n <= 30 || i === hover) && (
                <circle key={i} cx={p[0]} cy={p[1]} r={i === hover ? 4.5 : 3} fill={s.color} stroke="var(--panel)" strokeWidth="2" />
              ))}
            </g>
          );
        })}
        {ends.map((e) => (
          <text key={e.s.key} x={W - m.r + 8} y={e.py + 3} fontSize="10.5" fill="var(--ink-2)">{e.s.label} {fmt(e.v, digits)}</text>
        ))}
      </svg>
      {hover !== null && (
        <div className="chart-tip num" style={{ left: `${(x(hover) / W) * 100}%`, top: 24, transform: "translateX(8px)" }}>
          <b>Episode {xLabels[hover]}</b>
          {series.map((s) => <div key={s.key}><i style={{ display: "inline-block", width: 10, height: 3, background: s.color, marginRight: 6, verticalAlign: "middle" }} />{s.label}: {fmt(s.values[hover], digits)}</div>)}
        </div>
      )}
    </div>
  );
}
