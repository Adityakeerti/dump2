import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import MapGL, { NavigationControl, useControl } from "react-map-gl/maplibre";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { ColumnLayer, PathLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { TripsLayer } from "@deck.gl/geo-layers";
import { SimpleMeshLayer } from "@deck.gl/mesh-layers";
import { CubeGeometry } from "@luma.gl/engine";
import "maplibre-gl/dist/maplibre-gl.css";
import { Crosshair, Eye, Map as MapIcon, X } from "lucide-react";
import { along, bearingDeg, buildRoutes, cumulative, hexToRgb, ll, offset, verticesBetween } from "../lib/geo.js";
import { clusterColor, fmt, simClock } from "../lib/format.js";

const OFM = "https://tiles.openfreemap.org";
const STYLE_LIGHT = `${OFM}/styles/liberty`;
const STYLE_DARK = `${OFM}/styles/dark`;
const ESRI_BASE = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer";
const ESRI_DEFAULT_MAX = 18; // safe default where Esri's tile map cannot be read
const BUILDINGS_3D = (color, opacity) => ({
  id: "cs-buildings-3d",
  type: "fill-extrusion",
  source: "openmaptiles",
  "source-layer": "building",
  minzoom: 14,
  paint: {
    "fill-extrusion-color": color,
    "fill-extrusion-height": ["coalesce", ["get", "render_height"], 8],
    "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
    "fill-extrusion-opacity": opacity,
  },
});
// `maxzoom` is the deepest level Esri actually has imagery for here; beyond it MapLibre upscales those tiles
// instead of requesting Esri's grey "Map data not yet available" placeholders.
const satelliteStyle = (maxzoom) => ({
  version: 8,
  sources: {
    sat: { type: "raster", tiles: [`${ESRI_BASE}/tile/{z}/{y}/{x}`], tileSize: 256, maxzoom, attribution: "Imagery © Esri, Maxar, Earthstar Geographics" },
    openmaptiles: { type: "vector", url: `${OFM}/planet`, attribution: "OpenFreeMap © OpenMapTiles · Data © OpenStreetMap contributors" },
  },
  layers: [{ id: "sat", type: "raster", source: "sat" }, BUILDINGS_3D("#e8e2d8", 0.5)],
});

// Ask Esri's tile map which zoom levels have real imagery at a point (deepest available level, 16..20).
async function esriMaxZoom(lat, lon) {
  let best = ESRI_DEFAULT_MAX;
  for (const z of [17, 18, 19, 20]) {
    const n = 2 ** z;
    const x = Math.floor(((lon + 180) / 360) * n);
    const y = Math.floor(((1 - Math.asinh(Math.tan((lat * Math.PI) / 180)) / Math.PI) / 2) * n);
    try {
      const res = await fetch(`${ESRI_BASE}/tilemap/${z}/${y}/${x}/1/1`);
      const tm = await res.json();
      if (tm?.data?.[0] === 1) best = z; else return Math.min(best, z - 1);
    } catch {
      return best;
    }
  }
  return best;
}
const SAT_OVERZOOM = 2.5; // allow zooming this far past the imagery limit (upscaled) in satellite mode

const CAR = new CubeGeometry();
const CAR_SCALE = [2.2, 0.95, 0.75]; // half-extents in metres: 4.4 m long, 1.9 m wide, 1.5 m tall
const CAR_GAP = 7;          // metres between queued cars
const LANE = 1.7;           // lane centre offset from road axis
const WALK_MS = 1.4;        // pedestrian speed, m per simulated second
const TRAIL_SEC = 120;      // simulated seconds of trail behind each car cluster
const GREEN = [22, 200, 90, 255];
const RED = [235, 55, 55, 255];
const BG_CAR = [236, 238, 240, 255];

const speedRGBA = (r, a = 150) =>
  r >= 0.9 ? [12, 163, 12, a] : r >= 0.6 ? [250, 178, 25, a] : r >= 0.3 ? [236, 131, 90, a] : [208, 59, 59, a];

function DeckOverlay(props) {
  const overlay = useControl(() => new MapboxOverlay({ interleaved: true }));
  overlay.setProps(props);
  return null;
}

export default function CityMap3D({ topology, state, clusters, traces, decisions, mode, theme, overlays, onTrace, diagnosis }) {
  const geo = topology?.geometry;
  const model = useMemo(() => (geo ? buildRoutes(geo) : null), [geo]);
  const clusterIdx = useMemo(() => Object.fromEntries((clusters || []).map((c, i) => [c.id, i])), [clusters]);
  const arterialBearing = useMemo(() => {
    if (!geo) return 0;
    const a = geo.cells.filter((c) => c.kind === "arterial");
    return bearingDeg(a[0].coords[0], a.at(-1).coords.at(-1));
  }, [geo]);
  const overview = useMemo(() => geo && ({
    longitude: geo.center[1], latitude: geo.center[0], zoom: 15.4, pitch: 55, bearing: arterialBearing - 90,
  }), [geo, arterialBearing]);
  const streetLevel = useCallback(() => {
    const j = geo.junctions[Math.floor(geo.junctions.length / 2)];
    return { longitude: j.lon, latitude: j.lat, zoom: 18.6, pitch: 72, bearing: arterialBearing - 25 };
  }, [geo, arterialBearing]);

  const [view, setView] = useState(null);
  const mapRef = useRef(null);
  const [satMax, setSatMax] = useState(ESRI_DEFAULT_MAX);
  useEffect(() => {
    if (!geo) return;
    let alive = true;
    esriMaxZoom(geo.center[0], geo.center[1]).then((z) => alive && setSatMax(z));
    return () => { alive = false; };
  }, [geo]);
  const [follow, setFollow] = useState(null);
  const [frame, setFrame] = useState(0);
  const anim = useRef({ prev: null, cur: null, tickWall: 0, trails: new Map(), phase: {}, lastWall: performance.now(), episode: null });

  // Deep link: ?cam=street opens at street level, ?cam=follow chases the first car cluster.
  useEffect(() => {
    if (!overview || view) return;
    const cam = new URLSearchParams(location.search).get("cam");
    setView(cam === "street" || cam === "follow" ? streetLevel() : overview);
    if (cam === "follow") setFollow("first");
  }, [overview, view, streetLevel]);
  useEffect(() => {
    if (follow === "first" && heads.length) setFollow(heads[0].id);
  });

  // --- ingest a new twin tick: positions per car cluster, densified trails ---------------------------
  useEffect(() => {
    if (!state || !model) return;
    const a = anim.current;
    if (a.episode !== state.episode) { a.trails.clear(); a.prev = null; a.cur = null; a.episode = state.episode; }
    if (a.cur && a.cur.t === state.sim_time) return;
    const pos = new Map();
    for (const p of state.platoons) {
      if (p.status !== "moving") continue;
      const r = model.routes[p.source_id];
      if (!r || r.start[p.cell] === undefined) continue;
      const d = r.start[p.cell] + Math.min(1, p.frac) * model.cellLen[p.cell];
      pos.set(p.id, { d, p });
      let tr = a.trails.get(p.id);
      if (!tr) {
        tr = { id: p.id, cluster_id: p.cluster_id, source: p.source_id, path: [], ts: [], lastD: null, lastT: null, end: null };
        a.trails.set(p.id, tr);
      }
      if (tr.lastD !== null && d > tr.lastD) {
        for (const v of verticesBetween(r.poly, r.cum, tr.lastD, d)) {
          tr.path.push(ll(v.p));
          tr.ts.push(tr.lastT + ((v.d - tr.lastD) / (d - tr.lastD)) * (state.sim_time - tr.lastT));
        }
      }
      if (tr.lastD === null || d > tr.lastD) {
        tr.path.push(ll(along(r.poly, r.cum, d).p));
        tr.ts.push(state.sim_time);
        tr.lastD = d; tr.lastT = state.sim_time;
      }
    }
    for (const [id, tr] of a.trails) {
      if (!pos.has(id) && tr.end === null) tr.end = state.sim_time;
      if (tr.end !== null && state.sim_time - tr.end > TRAIL_SEC) a.trails.delete(id);
    }
    a.prev = a.cur;
    a.cur = { t: state.sim_time, pos };
    a.tickWall = performance.now();
  }, [state, model]);

  // --- animation clock -----------------------------------------------------------------------------
  useEffect(() => {
    let raf;
    const loop = () => { setFrame((f) => (f + 1) % 1e9); raf = requestAnimationFrame(loop); };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  const tickSec = topology?.tick_interval_sec || 0.25;
  const a = anim.current;
  const now = performance.now();
  const alpha = a.prev ? Math.min(1, (now - a.tickWall) / (tickSec * 1000)) : 1;
  const tDisplay = a.cur ? (a.prev ? a.prev.t + (a.cur.t - a.prev.t) * alpha : a.cur.t) : 0;
  const simRate = state?.status === "running" ? (state.steps_per_tick || 1) / tickSec : 0;
  const dtSim = ((now - a.lastWall) / 1000) * simRate;
  a.lastWall = now;

  // interpolated head position of every moving car cluster
  const heads = useMemo(() => {
    if (!a.cur || !model) return [];
    const out = [];
    for (const [id, cur] of a.cur.pos) {
      const prev = a.prev?.pos.get(id);
      const d = prev ? prev.d + (cur.d - prev.d) * alpha : cur.d;
      const r = model.routes[cur.p.source_id];
      const { p, heading } = along(r.poly, r.cum, d);
      out.push({ id, d, p, heading, platoon: cur.p, route: r });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frame, model]);

  // chase camera
  useEffect(() => {
    if (follow === null) return;
    const h = heads.find((x) => x.id === follow);
    if (!h) return;
    setView((v) => ({ ...v, longitude: h.p[1], latitude: h.p[0], bearing: h.heading, pitch: 74, zoom: 18.7 }));
  }, [frame, follow]); // eslint-disable-line react-hooks/exhaustive-deps

  const layers = useMemo(() => {
    if (!geo || !state || !model) return [];
    const ratio = state.cells.speed_ratio;
    const veh = state.cells.vehicles;
    const disrupted = new Set((state.disruptions || []).flatMap((d) => d.cells));
    const cellById = Object.fromEntries(geo.cells.map((c) => [c.id, c]));

    // --- road surface coloured by speed -------------------------------------------------------------
    const roads = geo.cells.map((c) => ({
      path: c.coords.map(ll), color: speedRGBA(ratio[c.id] ?? 1, c.synthetic ? 70 : 150), width: c.kind === "arterial" ? 8 : 6,
      tip: `Cell ${c.id} (${c.kind}${c.synthetic ? ", schematic: no mapped road on this side" : ""}) · ${fmt((ratio[c.id] ?? 1) * 100, 0)}% of free-flow speed · ${fmt(veh[c.id], 1)} veh`,
    }));
    const closures = geo.cells.filter((c) => disrupted.has(c.id)).map((c) => ({ path: c.coords.map(ll), tip: `Capacity disruption on cell ${c.id}` }));

    // --- car-cluster cars (coloured) and background traffic (CTM densities) -------------------------
    const cars = [];
    const inCell = {};
    for (const h of heads) {
      const n = Math.max(1, Math.min(24, Math.round(h.platoon.vehicles)));
      const color = hexToRgb(clusterColor(clusterIdx[h.platoon.cluster_id] ?? 0));
      for (let k = 0; k < n; k++) {
        const d = h.d - Math.floor(k / 2) * CAR_GAP;
        if (d < 0) break;
        const at = along(h.route.poly, h.route.cum, d);
        cars.push({ p: offset(at.p, at.heading, k % 2 ? LANE : -LANE), heading: at.heading, color, platoon: h.id,
          tip: `Car cluster #${h.id} · ${h.platoon.cluster} · ${h.platoon.intent} · ${fmt(h.platoon.vehicles, 0)} veh${h.platoon.held ? " · held at red" : ""} (click to follow)` });
      }
      inCell[h.platoon.cell] = (inCell[h.platoon.cell] || 0) + h.platoon.vehicles;
    }
    for (const c of geo.cells) {
      const n = Math.min(14, Math.max(0, Math.round((veh[c.id] || 0) - (inCell[c.id] || 0))));
      if (!n) continue;
      const L = model.cellLen[c.id];
      const cum = model.cellCum[c.id];
      const r = ratio[c.id] ?? 1;
      const perLane = Math.ceil(n / 2);
      const queued = r < 0.3;
      const gap = queued ? Math.min(CAR_GAP, L / perLane) : L / perLane;
      const v = r * 13.89 * (L / 15); // drawn metres per simulated second
      a.phase[c.id] = ((a.phase[c.id] || 0) + (queued ? 0 : v * dtSim)) % L;
      for (let k = 0; k < n; k++) {
        const i = Math.floor(k / 2);
        let d = L - (i + 0.5) * gap - (k % 2) * gap * 0.35;
        if (!queued) d = (((d + a.phase[c.id]) % L) + L) % L;
        const at = along(c.coords, cum, d);
        cars.push({ p: offset(at.p, at.heading, k % 2 ? LANE : -LANE), heading: at.heading, color: BG_CAR,
          tip: `Background traffic · cell ${c.id} · ${fmt(r * 100, 0)}% speed` });
      }
    }

    // --- signals: stop bars + light poles -----------------------------------------------------------
    const bars = [];
    const poles = [];
    for (const j of geo.junctions) {
      const js = state.junctions[j.id];
      const legs = j.cross_approaches || [j.cross_approach];
      const approaches = [[j.arterial_approach, j.arterial_phase, "arterial"], ...legs.map((c, i) => [c, j.cross_phase, legs.length > 1 ? `side road ${i ? "south/right" : "north/left"}` : "cross street"])];
      for (const [cellId, phase, label] of approaches) {
        const c = cellById[cellId];
        const end = along(c.coords, model.cellCum[cellId], model.cellLen[cellId] - 1.5);
        const go = js?.phase === phase;
        const legQ = js?.cross_leg_queues?.[legs.indexOf(cellId)];
        const tip = `J${j.id + 1} ${label}: ${go ? "GREEN" : "RED"} · ${fmt(js?.time_in_phase, 0)}s in phase · queue ${fmt(label === "arterial" ? js?.art_queue : legQ ?? js?.cross_queue)} veh · last switch #${js?.last_decision ?? "–"}`;
        bars.push({ path: [ll(offset(end.p, end.heading, -4.6)), ll(offset(end.p, end.heading, 4.6))], color: go ? GREEN : RED, tip });
        poles.push({ p: offset(end.p, end.heading, 5.6), color: go ? GREEN : RED, tip });
      }
    }
    const jLabels = geo.junctions.map((j) => ({ p: [j.lat, j.lon], text: `J${j.id + 1}` }));

    // --- people: neighbourhood towers and walkers along real footpaths ------------------------------
    const bigCut = [...(clusters || [])].map((c) => c.population).sort((a, b) => b - a)[9] ?? 0;
    const towers = (clusters || []).filter((c) => c.location).map((c, i) => ({
      p: c.location, color: hexToRgb(clusterColor(i), 150), h: Math.max(8, c.population / 30), id: c.id, big: c.population >= bigCut,
      label: c.name, plan: c.last ? `${c.last.plan.intent} · ${c.last.plan.departure.replace("_", " ")}` : "planning…",
      tip: `${c.name} · ${c.population} people${c.last ? ` · ${c.last.clock}: ${c.last.plan.intent}, leave ${c.last.plan.departure.replace("_", " ")}, share ${c.last.plan.share} (${c.last.decided_by === "llm" ? "Gemma" : "fallback"}) — “${c.last.plan.reason}”` : ""}`,
    }));
    const walkers = [];
    const walkerHeads = [];
    const byId = Object.fromEntries((clusters || []).map((c, i) => [c.id, { ...c, i }]));
    for (const t of traces || []) {
      if (t.episode !== state.episode || !t.car_clusters) continue;
      const c = byId[t.cluster_id];
      const path = c?.walk_path;
      if (!path || path.length < 2) continue;
      const cum = cumulative(path);
      const dur = cum.at(-1) / WALK_MS;
      const n = Math.min(10, Math.max(2, Math.ceil(t.vehicles / 3)));
      for (let k = 0; k < n; k++) {
        const start = t.sim_time + k * 6;
        if (tDisplay < start || tDisplay > start + dur + 60) continue;
        const side = ((k % 3) - 1) * 1.6;
        const pts = path.map((pt, i) => offset(pt, bearingDeg(path[Math.max(0, i - 1)], path[Math.min(path.length - 1, i + 1)]), side));
        const color = hexToRgb(clusterColor(c.i));
        walkers.push({ path: pts.map(ll), ts: cum.map((m) => start + m / WALK_MS), color });
        if (tDisplay <= start + dur) {
          const at = along(pts, cumulative(pts), (tDisplay - start) * WALK_MS);
          walkerHeads.push({ p: at.p, color, tip: `${c.name}: walking to the car (${t.plan.intent})` });
        }
      }
    }

    // --- congestion points: red ripples (click to trace the root cause) ----------------------------
    const minAge = topology.diagnosis_min_jam_age_sec ?? 0;
    const ripplePts = (state.congestion_points || []).map((cp) => {
      const c = cellById[cp.head_cell];
      const end = along(c.coords, model.cellCum[cp.head_cell], model.cellLen[cp.head_cell] * 0.5);
      const age = state.sim_time - cp.since_sec;
      const mature = age >= minAge;
      const head = `Congestion on ${cp.name}: ${cp.cells.length} slow cells, slowest at ${fmt(cp.min_speed_ratio * 100, 0)}% of free flow, for ${fmt(age, 0)} s.`;
      return { ...cp, p: end.p, mature, tip: mature ? `${head} Click to trace the root cause.` : `${head} Maturing: traceable in ${fmt(minAge - age, 0)} s (simulated).` };
    });
    const wall = performance.now() / 1000;
    const rings = [];
    for (const rp of ripplePts) for (let k = 0; k < (rp.mature ? 3 : 2); k++) {
      const ph = (wall / (rp.mature ? 1.8 : 2.6) + k / 3) % 1;
      rings.push({ p: rp.p, r: 6 + ph * (rp.mature ? 46 : 26), a: Math.round((1 - ph) * 230), c: rp.mature ? [232, 36, 36] : [240, 150, 40] });
    }

    // --- active root-cause trace overlay ------------------------------------------------------------
    const traceLayers = [];
    if (diagnosis?.found) {
      const jamCells = diagnosis.jam.cells.filter((id) => cellById[id]);
      const origin = cellById[diagnosis.origin.cell];
      traceLayers.push(new PathLayer({ id: "rc-jam", data: jamCells.map((id) => ({ path: cellById[id].coords.map(ll) })), getPath: (d) => d.path, getColor: [150, 20, 20, 120], getWidth: 16, widthUnits: "meters", capRounded: true }));
      if (origin) {
        const o = along(origin.coords, model.cellCum[origin.id], model.cellLen[origin.id] * 0.5);
        const r0 = model.routes[0];
        const tail = cellById[Math.min(...jamCells)];
        if (r0 && r0.start[origin.id] !== undefined && tail && r0.start[tail.id] !== undefined) {
          const d1 = r0.start[origin.id] + model.cellLen[origin.id] * 0.5;
          const d0 = r0.start[tail.id];
          const pts = [];
          for (let d = d1; d >= d0; d -= 4) pts.push(ll(along(r0.poly, r0.cum, d).p));
          traceLayers.push(new PathLayer({ id: "rc-shockwave", data: [{ path: pts }], getPath: (d) => d.path, getColor: [98, 80, 214, 230], getWidth: 3, widthUnits: "meters", widthMinPixels: 3, capRounded: true, jointRounded: true }));
        }
        traceLayers.push(new ColumnLayer({ id: "rc-origin", data: [{ p: o.p }], getPosition: (d) => [d.p[1], d.p[0]], getElevation: 42, radius: 2.6, diskResolution: 16, extruded: true, getFillColor: [208, 30, 30, 235], material: { ambient: 1, diffuse: 0.2 } }));
        traceLayers.push(new TextLayer({ id: "rc-origin-label", data: [{ p: o.p, text: `ROOT CAUSE · cell ${origin.id}` }], getPosition: (d) => [d.p[1], d.p[0], 48], getText: (d) => d.text, getSize: 12, getColor: [255, 255, 255, 255], getBackgroundColor: [176, 24, 24, 235], background: true, backgroundPadding: [6, 3], fontFamily: "Poppins, system-ui, sans-serif", fontWeight: 600, billboard: true }));
      }
    }

    const trails = [...a.trails.values()].filter((t) => t.path.length > 1).map((t) => ({
      path: t.path, ts: t.ts, color: hexToRgb(clusterColor(clusterIdx[t.cluster_id] ?? 0)),
    }));

    return [
      new PathLayer({ id: "closures", data: closures, getPath: (d) => d.path, getColor: [255, 255, 255, 90], getWidth: 20, widthUnits: "meters", capRounded: true, pickable: true }),
      new PathLayer({ id: "roads", data: roads, getPath: (d) => d.path, getColor: (d) => d.color, getWidth: (d) => d.width, widthUnits: "meters", jointRounded: true, capRounded: false, pickable: true }),
      new TripsLayer({ id: "car-trails", data: trails, getPath: (d) => d.path, getTimestamps: (d) => d.ts, getColor: (d) => d.color, widthMinPixels: 4, getWidth: 3, widthUnits: "meters", capRounded: true, jointRounded: true, fadeTrail: true, trailLength: TRAIL_SEC, currentTime: tDisplay }),
      new TripsLayer({ id: "walk-trails", data: walkers, getPath: (d) => d.path, getTimestamps: (d) => d.ts, getColor: (d) => d.color, widthMinPixels: 2, getWidth: 1.2, widthUnits: "meters", fadeTrail: true, trailLength: 70, currentTime: tDisplay, capRounded: true, jointRounded: true }),
      new PathLayer({ id: "stop-bars", data: bars, getPath: (d) => d.path, getColor: (d) => d.color, getWidth: 1.4, widthUnits: "meters", pickable: true }),
      new SimpleMeshLayer({ id: "cars", data: cars, mesh: CAR, getPosition: (d) => [d.p[1], d.p[0], 0.8], getOrientation: (d) => [0, 90 - d.heading, 0], getScale: CAR_SCALE, getColor: (d) => d.color, pickable: true, material: { ambient: 0.55, diffuse: 0.6, shininess: 40, specularColor: [255, 255, 255] }, onClick: ({ object }) => object?.platoon && setFollow(object.platoon) }),
      new ColumnLayer({ id: "signal-poles", data: poles, getPosition: (d) => [d.p[1], d.p[0]], getElevation: 6.5, radius: 0.7, diskResolution: 12, extruded: true, getFillColor: (d) => d.color, pickable: true, material: { ambient: 0.9, diffuse: 0.3 } }),
      new ScatterplotLayer({ id: "walkers", data: walkerHeads, getPosition: (d) => [d.p[1], d.p[0], 1], getFillColor: (d) => d.color, getLineColor: [255, 255, 255, 255], stroked: true, lineWidthMinPixels: 1.5, getRadius: 2.2, radiusUnits: "meters", radiusMinPixels: 3, pickable: true }),
      new ColumnLayer({ id: "neighbourhoods", data: towers, getPosition: (d) => [d.p[1], d.p[0]], getElevation: (d) => d.h, radius: 10, diskResolution: 24, extruded: true, getFillColor: (d) => d.color, pickable: true, material: { ambient: 0.6, diffuse: 0.5 } }),
      new TextLayer({ id: "neighbourhood-labels", data: towers.filter((t) => t.big || view?.zoom >= 16.5), getPosition: (d) => [d.p[1], d.p[0], d.h + 10], getText: (d) => d.label, getSize: 11, getColor: [255, 255, 255, 255], getBackgroundColor: [12, 16, 14, 150], background: true, backgroundPadding: [5, 2], fontFamily: "Poppins, system-ui, sans-serif", fontWeight: 500, billboard: true, characterSet: "auto", sizeMinPixels: 9, sizeMaxPixels: 12 }),
      ...traceLayers,
      new ScatterplotLayer({ id: "ripples", data: rings, getPosition: (d) => [d.p[1], d.p[0], 1.5], getRadius: (d) => d.r, radiusUnits: "meters", stroked: true, filled: false, getLineColor: (d) => [...d.c, d.a], lineWidthUnits: "meters", getLineWidth: 2.2, lineWidthMinPixels: 1.5 }),
      new ScatterplotLayer({ id: "congestion-points", data: ripplePts, getPosition: (d) => [d.p[1], d.p[0], 2], getRadius: 6, radiusUnits: "meters", radiusMinPixels: 7, getFillColor: (d) => (d.mature ? [222, 28, 28, 245] : [240, 150, 40, 235]), stroked: true, getLineColor: [255, 255, 255, 255], lineWidthMinPixels: 2, pickable: true, onClick: ({ object }) => object && onTrace?.(object) }),
      new TextLayer({ id: "junction-labels", data: jLabels, getPosition: (d) => [d.p[1], d.p[0], 9], getText: (d) => d.text, getSize: 13, getColor: [255, 255, 255, 255], getBackgroundColor: [30, 70, 48, 230], background: true, backgroundPadding: [5, 2], fontFamily: "Poppins, system-ui, sans-serif", fontWeight: 600, billboard: true }),
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frame, geo, state, model, clusters, traces, diagnosis]);

  const satStyle = useMemo(() => satelliteStyle(satMax), [satMax]);
  const mapStyle = mode === "satellite" ? satStyle : theme === "dark" ? STYLE_DARK : STYLE_LIGHT;
  const maxZoom = mode === "satellite" ? satMax + SAT_OVERZOOM : 22;
  const onLoad = useCallback((e) => {
    const map = e.target;
    const ensure = () => {
      const has = map.getStyle()?.layers?.some((l) => l.type === "fill-extrusion");
      if (!has && map.getSource("openmaptiles")) map.addLayer(BUILDINGS_3D(theme === "dark" ? "#2a2f2c" : "#d8d3cb", 0.85));
    };
    const sky = () => {
      if (typeof map.setSky !== "function") return;
      map.setSky(theme === "dark"
        ? { "sky-color": "#0d1512", "horizon-color": "#1d2a24", "fog-color": "#111816", "sky-horizon-blend": 0.7, "horizon-fog-blend": 0.6, "fog-ground-blend": 0.9 }
        : { "sky-color": "#bcd6ea", "horizon-color": "#eef1ef", "fog-color": "#f1f1ef", "sky-horizon-blend": 0.6, "horizon-fog-blend": 0.5, "fog-ground-blend": 0.92 });
    };
    ensure();
    sky();
    map.on("styledata", () => { ensure(); sky(); });
  }, [theme]);

  // When a root-cause trace arrives, frame the jam and its origin (left of the drawer).
  useEffect(() => {
    if (!diagnosis?.found || !geo || !mapRef.current) return;
    const ids = new Set([...diagnosis.jam.cells, diagnosis.origin.cell]);
    const pts = geo.cells.filter((c) => ids.has(c.id)).flatMap((c) => c.coords);
    if (!pts.length) return;
    const lats = pts.map((p) => p[0]), lons = pts.map((p) => p[1]);
    setFollow(null);
    const drawer = Math.min(560, window.innerWidth * 0.5);
    mapRef.current.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
      { padding: { top: 90, bottom: 60, left: 60, right: drawer }, pitch: 52, bearing: arterialBearing - 90, duration: 1400, maxZoom: 18.2 });
  }, [diagnosis, geo, arterialBearing]);

  // Overview frames the whole corridor plus every neighbourhood (the locality is ~2.7 km long).
  const fitOverview = useCallback((duration = 1000) => {
    if (!geo || !mapRef.current) return;
    const pts = [...geo.cells.flatMap((c) => c.coords), ...(clusters || []).map((c) => c.location).filter(Boolean)];
    const lats = pts.map((p) => p[0]), lons = pts.map((p) => p[1]);
    setFollow(null);
    // Fit the rotated bounds flat (fitBounds with pitch over-zooms out), then tilt with a small zoom boost.
    const cam = mapRef.current.cameraForBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
      { padding: { top: 90, bottom: 30, left: 30, right: 30 }, bearing: arterialBearing - 90 });
    if (!cam) return;
    const c = cam.center;
    mapRef.current.easeTo({ center: c, zoom: cam.zoom + 0.35, pitch: 50, bearing: arterialBearing - 90, duration });
  }, [geo, clusters, arterialBearing]);
  const framed = useRef(false);
  useEffect(() => {
    if (framed.current || !mapRef.current || !clusters?.length || new URLSearchParams(location.search).get("cam")) return;
    framed.current = true;
    fitOverview(0);
  });

  const followed = heads.find((h) => h.id === follow);
  const decisionById = useMemo(() => Object.fromEntries((decisions || []).map((d) => [d.id, d])), [decisions]);

  if (!geo || !view) return <div className="empty" style={{ color: "#ccc", paddingTop: 200 }}>Connecting to the digital twin…</div>;
  const streets = geo.streets;

  return (
    <>
      <MapGL
        ref={mapRef}
        {...view}
        onMove={(e) => { if (follow === null) setView(e.viewState); }}
        mapStyle={mapStyle}
        onLoad={onLoad}
        maxPitch={80}
        maxZoom={maxZoom}
        attributionControl={{ compact: true }}
        style={{ width: "100%", height: "100%" }}
      >
        <NavigationControl position="bottom-right" visualizePitch />
        <DeckOverlay
          layers={layers}
          getTooltip={({ object }) => object?.tip && { text: object.tip, style: { background: "rgba(12,16,14,.92)", color: "#eef0ee", borderRadius: "10px", font: "11px Poppins, system-ui", maxWidth: "320px", padding: "6px 9px" } }}
        />
      </MapGL>

      <div className="map-overlay tr cam-bar" role="group" aria-label="Camera">
        <button className={follow === null && view.pitch < 70 ? "on" : ""} onClick={() => fitOverview()}><MapIcon size={13} /> Overview</button>
        <button onClick={() => { setFollow(null); setView(streetLevel()); }}><Eye size={13} /> Street level</button>
        <button className={follow !== null ? "on" : ""} disabled={!heads.length} onClick={() => {
          const ids = heads.map((h) => h.id);
          const next = follow === null ? ids[0] : ids[(ids.indexOf(follow) + 1) % ids.length];
          setFollow(next ?? null);
        }}><Crosshair size={13} /> {follow === null ? "Follow a car cluster" : "Next car cluster"}</button>
      </div>

      {followed && (
        <div className="map-overlay br follow-card">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="legend-swatch" style={{ background: clusterColor(clusterIdx[followed.platoon.cluster_id] ?? 0), width: 12, height: 12, borderRadius: 6 }} />
            <b>Car cluster #{followed.id}</b>
            <button className="icon-btn" onClick={() => setFollow(null)} aria-label="Stop following"><X size={13} /></button>
          </div>
          <div>{followed.platoon.cluster} · {followed.platoon.intent} · {fmt(followed.platoon.vehicles, 0)} vehicles</div>
          <div className="num">departed {simClock(followed.platoon.depart).full} · {followed.platoon.held ? "waiting at red" : "moving"}</div>
          {followed.platoon.passes.length === 0 && <div style={{ opacity: 0.7 }}>no junction passed yet</div>}
          {followed.platoon.passes.map((x, i) => {
            const dec = decisionById[x.released_by];
            return (
              <div key={i} className="num">
                J{x.junction + 1}: waited {fmt(x.wait_sec, 0)}s · released by #{x.released_by ?? "–"}
                {dec && <span style={{ opacity: 0.75 }}> ({dec.mode}{dec.shield ? `, shield ${dec.shield}` : ""})</span>}
              </div>
            );
          })}
        </div>
      )}

      {overlays}
      <div className="map-overlay tc">
        {streets ? <>Corridor on <b>{streets.arterial_name}</b> (OSM) · links drawn at {Math.min(...streets.link_scale)}–{Math.max(...streets.link_scale)}× simulated length</> : "Schematic corridor layout"}
        {mode === "satellite" && view.zoom > satMax && <> · imagery upscaled (Esri has none beyond zoom {satMax} here)</>}
      </div>
    </>
  );
}
