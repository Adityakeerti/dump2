// Small geodesy helpers for drawing on real streets (lat/lon in, metres along polylines).
export const M_PER_DEG_LAT = 111320;
export const mPerDegLon = (lat) => M_PER_DEG_LAT * Math.cos((lat * Math.PI) / 180);

export function distM(a, b) {
  const dy = (b[0] - a[0]) * M_PER_DEG_LAT;
  const dx = (b[1] - a[1]) * mPerDegLon((a[0] + b[0]) / 2);
  return Math.hypot(dx, dy);
}

export function bearingDeg(a, b) {
  const dy = (b[0] - a[0]) * M_PER_DEG_LAT;
  const dx = (b[1] - a[1]) * mPerDegLon((a[0] + b[0]) / 2);
  return ((Math.atan2(dx, dy) * 180) / Math.PI + 360) % 360;
}

export function cumulative(poly) {
  const out = [0];
  for (let i = 1; i < poly.length; i++) out.push(out[i - 1] + distM(poly[i - 1], poly[i]));
  return out;
}

// Point and heading at arc length d along a polyline (with precomputed cumulative lengths).
export function along(poly, cum, d) {
  const total = cum[cum.length - 1];
  const x = Math.min(Math.max(d, 0), total);
  let i = 1;
  while (i < cum.length - 1 && cum[i] < x) i++;
  const seg = cum[i] - cum[i - 1] || 1;
  const t = (x - cum[i - 1]) / seg;
  const a = poly[i - 1], b = poly[i];
  return { p: [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t], heading: bearingDeg(a, b) };
}

// Offset a point sideways (right of heading = positive) and forwards, in metres.
export function offset(p, heading, rightM, fwdM = 0) {
  const h = (heading * Math.PI) / 180;
  const east = Math.sin(h) * fwdM + Math.cos(h) * rightM;
  const north = Math.cos(h) * fwdM - Math.sin(h) * rightM;
  return [p[0] + north / M_PER_DEG_LAT, p[1] + east / mPerDegLon(p[0])];
}

// Vertices of a polyline strictly between arc lengths d0 < d1 (to densify trails along curved roads).
export function verticesBetween(poly, cum, d0, d1) {
  const out = [];
  for (let i = 0; i < poly.length; i++) if (cum[i] > d0 && cum[i] < d1) out.push({ p: poly[i], d: cum[i] });
  return out;
}

export const ll = (p) => [p[1], p[0]]; // [lat, lon] -> [lon, lat]

export function hexToRgb(hex, a = 255) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255, a];
}

// Build one route (polyline + per-cell offsets) per trip source from the twin's cell geometry.
export function buildRoutes(geo) {
  const cellById = Object.fromEntries(geo.cells.map((c) => [c.id, c]));
  const cellLen = {};
  for (const c of geo.cells) cellLen[c.id] = cumulative(c.coords).at(-1);
  const routes = {};
  // Paths of each source: arterial cells (kind=arterial, ordered) or the junction's cross street.
  const arterial = geo.cells.filter((c) => c.kind === "arterial").map((c) => c.id).sort((a, b) => a - b);
  for (const s of geo.sources) {
    const ids = s.kind === "arterial" ? arterial
      : geo.cells.filter((c) => c.kind === "cross" && c.link === s.junction && (s.leg === null || s.leg === undefined || c.leg === s.leg)).map((c) => c.id).sort((a, b) => a - b);
    const poly = [];
    const start = {};
    let acc = 0;
    for (const id of ids) {
      start[id] = acc;
      const pts = cellById[id].coords;
      poly.push(...(poly.length ? pts.slice(1) : pts));
      acc += cellLen[id];
    }
    routes[s.id] = { poly, cum: cumulative(poly), start, ids };
  }
  return { routes, cellLen, cellCum: Object.fromEntries(geo.cells.map((c) => [c.id, cumulative(c.coords)])) };
}
