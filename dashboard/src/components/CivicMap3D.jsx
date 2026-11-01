import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import MapGL, { NavigationControl, useControl } from "react-map-gl/maplibre";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { ArcLayer, ColumnLayer, PathLayer, PolygonLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { SimpleMeshLayer } from "@deck.gl/mesh-layers";
import { CubeGeometry } from "@luma.gl/engine";
import "maplibre-gl/dist/maplibre-gl.css";
import { Crosshair, Eye, Map as MapIcon } from "lucide-react";
import { cumulative, along, ll, M_PER_DEG_LAT, mPerDegLon } from "../lib/geo.js";

// Civic simulator on a schematic 6x6 block grid anchored on Dehradun. Residents live in their blocks and file
// complaints (arcs to the department HQ); crews drive from HQ to the asset they inspect or repair; confirmed
// root causes pulse red with their affected zone outlined. Everything shown is SIMULATED.

const OFM = "https://tiles.openfreemap.org";
const STYLE_LIGHT = `${OFM}/styles/liberty`;
const STYLE_DARK = `${OFM}/styles/dark`;
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer";
const BUILDINGS_3D = (color, opacity) => ({
  id: "cs-buildings-3d", type: "fill-extrusion", source: "openmaptiles", "source-layer": "building", minzoom: 14,
  paint: { "fill-extrusion-color": color, "fill-extrusion-height": ["coalesce", ["get", "render_height"], 8],
    "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0], "fill-extrusion-opacity": opacity },
});
const SATELLITE = {
  version: 8,
  sources: {
    sat: { type: "raster", tiles: [`${ESRI}/tile/{z}/{y}/{x}`], tileSize: 256, maxzoom: 18, attribution: "Imagery © Esri, Maxar, Earthstar Geographics" },
    openmaptiles: { type: "vector", url: `${OFM}/planet`, attribution: "OpenFreeMap © OpenMapTiles · Data © OpenStreetMap contributors" },
  },
  layers: [{ id: "sat", type: "raster", source: "sat" }, BUILDINGS_3D("#e8e2d8", 0.35)],
};

export const DEPT_RGB = { municipal: [42, 120, 214], police: [235, 104, 52] };
const WATER = [40, 150, 255];
const SEWER = [150, 104, 60];
const ROUTE_RGB = [[27, 175, 122], [201, 133, 0], [213, 81, 129], [98, 80, 214]];
const LAMP_ON = [255, 214, 92];
const LAMP_OFF = [90, 90, 96];
const ROOT_RED = [214, 32, 32];
const VAN = new CubeGeometry();
const VAN_SCALE = [3.0, 1.25, 1.2];
const ARC_SEC = 2.6;      // seconds a complaint arc is in flight
const BUBBLE_SEC = 4.5;   // seconds a speech bubble stays above a resident
const QUAD = [[1, 1], [-1, 1], [-1, -1], [1, -1]];

function DeckOverlay(props) {
  const overlay = useControl(() => new MapboxOverlay({ interleaved: true }));
  overlay.setProps(props);
  return null;
}

const move = (p, eastM, northM) => [p[0] + northM / M_PER_DEG_LAT, p[1] + eastM / mPerDegLon(p[0])];
const rc = (name) => [Number(name[1]), Number(name[2])];
function rand(seed) { // deterministic 0..1 from an integer
  let t = (seed + 0x6d2b79f5) | 0;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}

// Static geometry derived once from /api/civic/map.
function buildModel(map) {
  const blocks = map.blocks;
  const byName = Object.fromEntries(blocks.map((b) => [b.name, b]));
  const rows = Math.max(...blocks.map((b) => rc(b.name)[0])) + 1;
  const cols = Math.max(...blocks.map((b) => rc(b.name)[1])) + 1;
  const at = (r, c) => blocks[r * cols + c];
  const S = map.spacing_m;
  const centre = (b) => [b.lat, b.lon];
  const hqBlocks = new Set(map.departments.map((d) => d.hq.block));
  const hq = Object.fromEntries(map.departments.map((d) => [d.id, { ...d, p: move([d.hq.lat, d.hq.lon], 62, 62) }]));

  // street grid through block centres (extended half a block past the edge)
  const streets = [];
  for (let r = 0; r < rows; r++) {
    const a = centre(at(r, 0)), b = centre(at(r, cols - 1));
    const art = blocks.filter((x) => rc(x.name)[0] === r).every((x) => x.arterial);
    streets.push({ path: [move(a, -S / 2, 0), move(b, S / 2, 0)].map(ll), art, tip: art ? `Arterial road (row ${r})` : `Street (row ${r})` });
  }
  for (let c = 0; c < cols; c++) {
    const a = centre(at(0, c)), b = centre(at(rows - 1, c));
    const art = blocks.filter((x) => rc(x.name)[1] === c).every((x) => x.arterial);
    streets.push({ path: [move(a, 0, S / 2), move(b, 0, -S / 2)].map(ll), art, tip: art ? `Arterial road (column ${c})` : `Street (column ${c})` });
  }

  // residents' homes: each resident owns a deterministic spot in a block quadrant (away from the street axes)
  const per = map.residents_per_block;
  const homes = [];
  blocks.forEach((b, bi) => {
    for (let k = 0; k < per; k++) {
      const id = bi * per + k;
      let q = k % 4;
      if (hqBlocks.has(b.name) && q === 0) q = 2;
      const [sx, sy] = QUAD[q];
      const e = sx * (24 + rand(id * 3 + 1) * 80), n = sy * (24 + rand(id * 3 + 2) * 80);
      homes.push({ id, block: b.name, p: move(centre(b), e, n), h: 5 + rand(id * 7) * 9, phase: rand(id * 11) * 6.28 });
    }
  });

  // pipes run along streets, water on one side and sewer on the other
  const pipe = (edges, side, color, label) => edges.map(([p, v]) => {
    const a = blocks[p], b = blocks[v];
    const horiz = rc(a.name)[0] === rc(b.name)[0];
    const off = (x) => (horiz ? move(centre(x), 0, side) : move(centre(x), side, 0));
    return { path: [off(a), off(b)].map(ll), color, key: `${a.name}-${b.name}`, from: a.name, to: b.name, tip: `${label}: ${a.name} → ${b.name}` };
  });
  const water = pipe(map.layers.water?.edges || [], 7, WATER, "Water main (flow from reservoir)");
  const sewer = pipe(map.layers.sewer?.edges || [], -7, SEWER, "Sewer (flow towards outfall)");

  const square = (b, f) => {
    const h = (S * f) / 2;
    return [move(centre(b), -h, -h), move(centre(b), h, -h), move(centre(b), h, h), move(centre(b), -h, h)].map(ll);
  };
  const routes = (map.layers.waste?.groups || []).flatMap((g, i) => g.blocks.map((bi) => ({
    poly: square(blocks[bi], 0.74), color: ROUTE_RGB[i % ROUTE_RGB.length], tip: `${g.name} (blocks ${g.blocks.map((x) => blocks[x].name).join(", ")})`,
  })));
  const feederOf = {};
  for (const g of map.layers.streetlight?.groups || []) for (const bi of g.blocks) feederOf[blocks[bi].name] = g.name;
  const lamps = blocks.flatMap((b) => [[40, 7], [-40, -7], [7, 40], [-7, -40]].map(([e, n], i) => ({
    block: b.name, p: move(centre(b), e, n), tip: `Streetlight · ${b.name} · ${feederOf[b.name] || "feeder"}`, i,
  })));
  return { blocks, byName, rows, cols, S, centre, hq, streets, homes, water, sewer, routes, lamps, square, per };
}

// Street path a crew drives: along the HQ row, then along the target column (Manhattan route through centres).
function crewPath(model, fromName, toName, start) {
  const [r0, c0] = rc(fromName), [r1, c1] = rc(toName);
  const pts = [start];
  const step = (a, b) => (a <= b ? 1 : -1);
  for (let c = c0; c !== c1; c += step(c0, c1)) pts.push(model.centre(model.blocks[r0 * model.cols + c + step(c0, c1)]));
  for (let r = r0; r !== r1; r += step(r0, r1)) pts.push(model.centre(model.blocks[(r + step(r0, r1)) * model.cols + c1]));
  const end = move(model.centre(model.byName[toName]), 10, -10);
  pts.push(end);
  return pts;
}

export default function CivicMap3D({ map, state, health, complaints, actions, diagnosis, mode, theme, show, selected, onSelect, overlays }) {
  const model = useMemo(() => (map ? buildModel(map) : null), [map]);
  const overview = useMemo(() => map && ({ longitude: map.center[1], latitude: map.center[0] - 0.0015, zoom: 15.3, pitch: 56, bearing: -18 }), [map]);
  const [view, setView] = useState(null);
  const [follow, setFollow] = useState(false);
  const [frame, setFrame] = useState(0);
  const mapRef = useRef(null);
  useEffect(() => { if (overview && !view) setView(overview); }, [overview, view]);
  useEffect(() => {
    let raf;
    const loop = () => { setFrame((f) => (f + 1) % 1e9); raf = requestAnimationFrame(loop); };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  const tickSec = health?.tick_interval_sec || 3;
  const now = performance.now() / 1000;

  // crews: latest non-wait action per department, animated from HQ to the target block
  const crews = useMemo(() => {
    if (!model) return [];
    const out = [];
    for (const dept of Object.keys(model.hq)) {
      const a = [...(actions || [])].reverse().find((x) => x.department === dept && x.action !== "wait");
      if (!a || !a.block || now - a._seen > tickSec * 3.5) continue;
      const pts = crewPath(model, model.hq[dept].hq.block, a.block, model.hq[dept].p);
      const cum = cumulative(pts);
      const travel = Math.max(1.0, tickSec * 0.6);
      const t = Math.min(1, (now - a._seen) / travel);
      const pos = along(pts, cum, t * cum.at(-1));
      out.push({ ...a, pts, pos, arrived: t >= 1, t });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frame, model, actions, tickSec]);

  useEffect(() => {
    if (!follow) return;
    const c = crews.find((x) => !x.arrived) || crews[0];
    if (c) setView((v) => ({ ...v, longitude: c.pos.p[1], latitude: c.pos.p[0], zoom: 17.6, pitch: 70, bearing: c.pos.heading }));
  }, [frame, follow]); // eslint-disable-line react-hooks/exhaustive-deps

  // fly to a selected root cause
  useEffect(() => {
    if (!selected || !model || !mapRef.current) return;
    const pts = (selected.zone || [selected.where?.block || selected.block]).map((n) => model.byName[n]).filter(Boolean);
    if (!pts.length) return;
    setFollow(false);
    const lats = pts.map((b) => b.lat), lons = pts.map((b) => b.lon), pad = model.S / 2 / M_PER_DEG_LAT;
    mapRef.current.fitBounds([[Math.min(...lons) - pad, Math.min(...lats) - pad], [Math.max(...lons) + pad, Math.max(...lats) + pad]],
      { padding: { top: 90, bottom: 60, left: 60, right: Math.min(560, window.innerWidth * 0.45) }, pitch: 55, bearing: -18, duration: 1400, maxZoom: 17.2 });
  }, [selected, model]);

  const layers = useMemo(() => {
    if (!model || !state) return [];
    const { blocks, centre, hq, S } = model;
    const wall = now;
    const blockState = state.blocks || [];
    const maxRecent = Math.max(4, ...blockState.map((b) => b.recent_municipal + b.recent_police));

    // evidence-driven lamp state: a block whose residents recently reported dark streets shows dim lamps
    const darkBlocks = new Set((complaints || []).filter((c) => c.category === "streetlight" && c.tick >= (state.tick - 6)).map((c) => c.block));

    const heat = blocks.map((b, i) => {
      const s = blockState[i] || { recent_municipal: 0, recent_police: 0, potholes: 0 };
      const tot = s.recent_municipal + s.recent_police;
      const k = tot / maxRecent;
      const rgb = s.recent_police > s.recent_municipal ? DEPT_RGB.police : [208, 59, 59];
      return { poly: model.square(b, 0.9), color: [...rgb, Math.round(18 + k * 120)], elev: 0.4 + k * 3,
        tip: `${b.name} · ward ${b.ward + 1}${b.arterial ? " · arterial" : ""}\n${s.recent_municipal} municipal + ${s.recent_police} police complaints in the last 8 ticks · ${s.potholes} open potholes` };
    });

    const homes = model.homes.map((h) => ({ ...h, tip: `Home of resident R${String(h.id).padStart(4, "0")} · ${h.block}` }));
    const people = model.homes.map((h) => {
      const w = wall * 0.35 + h.phase;
      return { p: move(h.p, Math.cos(w) * 9, Math.sin(w * 1.3) * 7), id: h.id };
    });

    // complaints in flight: arc from the resident's home to the department HQ, plus speech bubbles
    const homeOf = (c) => model.homes[Number(String(c.citizen.id).slice(1))];
    const flying = (complaints || []).filter((c) => wall - c._seen < ARC_SEC && homeOf(c));
    const arcs = flying.map((c) => ({ from: homeOf(c).p, to: hq[c.department]?.p, color: DEPT_RGB[c.department], a: 1 - (wall - c._seen) / ARC_SEC,
      tip: `${c.citizen.id} (${c.citizen.persona}) → ${c.unit}: ${c.text}` })).filter((x) => x.to);
    const comets = arcs.map((x, i) => {
      const t = Math.min(1, (wall - flying[i]._seen) / (ARC_SEC * 0.8));
      const lat = x.from[0] + (x.to[0] - x.from[0]) * t, lon = x.from[1] + (x.to[1] - x.from[1]) * t;
      const len = Math.hypot((x.to[0] - x.from[0]) * M_PER_DEG_LAT, (x.to[1] - x.from[1]) * mPerDegLon(lat));
      return { p: [lat, lon], z: 4 * t * (1 - t) * len * 0.22 + 8, color: x.color, done: t >= 1 };
    }).filter((c) => !c.done);
    const pings = flying.map((c) => ({ p: homeOf(c).p, r: 4 + ((wall - c._seen) / ARC_SEC) * 26, a: Math.round(220 * (1 - (wall - c._seen) / ARC_SEC)), color: DEPT_RGB[c.department] }));
    const bubbles = (complaints || []).filter((c) => wall - c._seen < BUBBLE_SEC && homeOf(c)).slice(-7)
      .map((c) => ({ p: homeOf(c).p, text: `${c.label}${c.text_by === "llm" ? " ✎" : ""}`, color: DEPT_RGB[c.department] }));

    // potholes: dark discs along the street arms of each block
    const potholes = blocks.flatMap((b, i) => Array.from({ length: blockState[i]?.potholes || 0 }, (_, k) => {
      const arm = [[1, 0], [-1, 0], [0, 1], [0, -1]][k % 4], d = 22 + 16 * Math.floor(k / 4);
      return { p: move(centre(b), arm[0] * d + arm[1] * 2.2, arm[1] * d + arm[0] * 2.2), tip: `Pothole · ${b.name}` };
    }));

    // root causes and hypotheses
    const roots = diagnosis?.root_causes || [];
    const hyps = (diagnosis?.hypotheses || []).slice(0, 3);
    const zoneSet = new Set(roots.flatMap((r) => r.zone || []));
    const selZone = new Set(selected?.zone || []);
    const zoneEdges = (edges, list) => edges.filter((e) => roots.some((r) => r.where.layer === list && (r.zone || []).includes(e.from) && (r.zone || []).includes(e.to)));
    const rootPts = roots.map((r) => ({ ...r, p: move(centre(model.byName[r.where.block]), 10, -10), fixed: r.status === "FIXED",
      tip: `${r.status}: ${r.where.asset} · ${r.responsible_department}\nWhy: ${r.why}\nClick for the full trace` }));
    const rings = [];
    for (const r of rootPts) for (let k = 0; k < 3; k++) {
      const ph = (wall / (r.fixed ? 2.6 : 1.6) + k / 3) % 1;
      rings.push({ p: r.p, r: 8 + ph * (r.fixed ? 40 : 70), a: Math.round((1 - ph) * 230), c: r.fixed ? [22, 170, 90] : ROOT_RED });
    }
    const hypPts = hyps.map((h) => ({ ...h, p: move(centre(model.byName[h.block]), 10, -10),
      tip: `HYPOTHESIS (unconfirmed): ${h.asset_name} · score ${h.score}\nNext step: ${h.next_step}` }));
    for (const h of hypPts) for (let k = 0; k < 2; k++) {
      const ph = (wall / 2.4 + k / 2) % 1;
      rings.push({ p: h.p, r: 6 + ph * 30, a: Math.round((1 - ph) * 170), c: [240, 150, 40] });
    }

    // crews
    const vans = crews.map((c) => ({ ...c, color: DEPT_RGB[c.department],
      tip: `${c.department === "police" ? "Police" : "Municipal"} crew → ${c.action} ${c.asset_name}${c.arrived ? (c.found_fault ? " · FAULT FOUND" : " · nothing found") : " (en route)"}` }));
    const crewTrails = crews.filter((c) => !c.arrived).map((c) => ({ path: c.pts.map(ll), color: [...DEPT_RGB[c.department], 110] }));
    const work = crews.filter((c) => c.arrived).map((c) => {
      const symptom = ["road", "traffic"].includes(c.layer);
      const label = c.action === "inspect" ? (c.found_fault ? "FAULT FOUND" : "inspected · nothing found")
        : symptom ? (c.layer === "road" ? "potholes patched" : "marshal deployed")
        : c.found_fault ? "REPAIRED ROOT CAUSE" : "repaired · nothing wrong";
      const good = c.found_fault && !symptom;
      return { p: c.pos.p, text: label, bg: good ? [22, 140, 70, 235] : symptom ? [70, 80, 90, 220] : c.action === "inspect" ? [40, 60, 90, 220] : [150, 60, 40, 225], good, inspect: c.action === "inspect" };
    });
    const scans = work.filter((w) => w.inspect).flatMap((w) => [0, 1].map((k) => {
      const ph = (wall / 1.2 + k / 2) % 1;
      return { p: w.p, r: 5 + ph * 22, a: Math.round((1 - ph) * 220) };
    }));

    const L = [];
    L.push(new PolygonLayer({ id: "civic-block-heat", data: heat, getPolygon: (d) => d.poly, getFillColor: (d) => d.color, extruded: false, stroked: false, pickable: true }));
    if (show.waste) L.push(new PolygonLayer({ id: "civic-waste-routes", data: model.routes, getPolygon: (d) => d.poly, filled: false, stroked: true, getLineColor: (d) => [...d.color, 200], getLineWidth: 2.5, lineWidthUnits: "meters", pickable: true }));
    L.push(new PathLayer({ id: "civic-streets", data: model.streets, getPath: (d) => d.path, getColor: (d) => (d.art ? [70, 74, 82, 235] : [110, 114, 120, 200]), getWidth: (d) => (d.art ? 14 : 9), widthUnits: "meters", capRounded: true, pickable: true }));
    L.push(new PathLayer({ id: "civic-street-paint", data: model.streets.filter((s) => s.art), getPath: (d) => d.path, getColor: [250, 250, 245, 160], getWidth: 0.5, widthUnits: "meters", widthMinPixels: 1, getDashArray: [6, 6] }));
    if (show.water) L.push(new PathLayer({ id: "civic-water", data: model.water, getPath: (d) => d.path, getColor: (d) => [...d.color, 220], getWidth: 2.4, widthUnits: "meters", widthMinPixels: 1.5, capRounded: true, pickable: true }));
    if (show.sewer) L.push(new PathLayer({ id: "civic-sewer", data: model.sewer, getPath: (d) => d.path, getColor: (d) => [...d.color, 230], getWidth: 2.4, widthUnits: "meters", widthMinPixels: 1.5, capRounded: true, pickable: true }));
    const hotPipes = [...(show.water ? zoneEdges(model.water, "water") : []), ...(show.sewer ? zoneEdges(model.sewer, "sewer") : [])];
    if (hotPipes.length) L.push(new PathLayer({ id: "civic-pipes-affected", data: hotPipes, getPath: (d) => d.path, getColor: [...ROOT_RED, 235], getWidth: 4, widthUnits: "meters", widthMinPixels: 2.5, capRounded: true }));
    if (zoneSet.size) L.push(new PolygonLayer({ id: "civic-root-zones", data: blocks.filter((b) => zoneSet.has(b.name)).map((b) => ({ poly: model.square(b, 0.94), sel: selZone.has(b.name) })), getPolygon: (d) => d.poly, filled: false, stroked: true, getLineColor: (d) => [...ROOT_RED, d.sel ? 255 : 140], getLineWidth: (d) => (d.sel ? 5 : 2.5), lineWidthUnits: "meters", updateTriggers: { getLineColor: [selected], getLineWidth: [selected] } }));
    L.push(new ScatterplotLayer({ id: "civic-potholes", data: potholes, getPosition: (d) => [d.p[1], d.p[0], 0.3], getRadius: 2.6, radiusUnits: "meters", radiusMinPixels: 2, getFillColor: [28, 26, 24, 255], stroked: true, getLineColor: [160, 150, 130, 255], lineWidthMinPixels: 1, pickable: true }));
    if (show.lights) L.push(new ColumnLayer({ id: "civic-lamps", data: model.lamps, getPosition: (d) => [d.p[1], d.p[0]], getElevation: 7, radius: 0.6, diskResolution: 8, extruded: true, getFillColor: (d) => (darkBlocks.has(d.block) ? LAMP_OFF : LAMP_ON), pickable: true, material: { ambient: 1, diffuse: 0.2 }, updateTriggers: { getFillColor: [state.tick] } }));
    L.push(new ColumnLayer({ id: "civic-homes", data: homes, getPosition: (d) => [d.p[1], d.p[0]], getElevation: (d) => d.h, radius: 5, diskResolution: 4, angle: 45, extruded: true, getFillColor: theme === "dark" ? [120, 128, 124, 255] : [236, 228, 214, 255], pickable: true, material: { ambient: 0.6, diffuse: 0.5 } }));
    L.push(new ScatterplotLayer({ id: "civic-people", data: people, getPosition: (d) => [d.p[1], d.p[0], 1], getRadius: 1.6, radiusUnits: "meters", radiusMinPixels: 1.6, getFillColor: [250, 250, 248, 255], stroked: true, getLineColor: [40, 44, 48, 255], lineWidthMinPixels: 0.8 }));
    L.push(new ScatterplotLayer({ id: "civic-complaint-pings", data: pings, getPosition: (d) => [d.p[1], d.p[0], 1.5], getRadius: (d) => d.r, radiusUnits: "meters", stroked: true, filled: false, getLineColor: (d) => [...d.color, d.a], getLineWidth: 1.6, lineWidthUnits: "meters", lineWidthMinPixels: 1 }));
    L.push(new ArcLayer({ id: "civic-complaint-arcs", data: arcs, getSourcePosition: (d) => [d.from[1], d.from[0], 2], getTargetPosition: (d) => [d.to[1], d.to[0], 30], getSourceColor: (d) => [...d.color, Math.round(220 * d.a)], getTargetColor: (d) => [...d.color, Math.round(90 * d.a)], getWidth: 2, getHeight: 0.35, pickable: true }));
    L.push(new ScatterplotLayer({ id: "civic-complaint-comets", data: comets, getPosition: (d) => [d.p[1], d.p[0], d.z], getRadius: 3.2, radiusUnits: "meters", radiusMinPixels: 3, getFillColor: (d) => [...d.color, 255], stroked: true, getLineColor: [255, 255, 255, 255], lineWidthMinPixels: 1 }));
    const hqData = Object.values(hq).map((d) => ({ ...d, tip: `${d.label} · ${d.hq_label}\nReceives ${d.id} complaints and dispatches crews from here` }));
    L.push(new ColumnLayer({ id: "civic-hq", data: hqData, getPosition: (d) => [d.p[1], d.p[0]], getElevation: 46, radius: 18, diskResolution: 4, angle: 45, extruded: true, getFillColor: (d) => [...DEPT_RGB[d.id], 255], pickable: true, material: { ambient: 0.6, diffuse: 0.5 } }));
    L.push(new TextLayer({ id: "civic-hq-labels", data: hqData, getPosition: (d) => [d.p[1], d.p[0], 56], getText: (d) => d.hq_label, getSize: 12, getColor: [255, 255, 255, 255], getBackgroundColor: (d) => [...DEPT_RGB[d.id], 235], background: true, backgroundPadding: [6, 3], fontFamily: "Poppins, system-ui, sans-serif", fontWeight: 600, billboard: true, pickable: true }));
    L.push(new PathLayer({ id: "civic-crew-trails", data: crewTrails, getPath: (d) => d.path, getColor: (d) => d.color, getWidth: 3, widthUnits: "meters", widthMinPixels: 2, getDashArray: [4, 3], capRounded: true }));
    L.push(new SimpleMeshLayer({ id: "civic-crews", data: vans, mesh: VAN, getPosition: (d) => [d.pos.p[1], d.pos.p[0], 1.3], getOrientation: (d) => [0, 90 - d.pos.heading, 0], getScale: VAN_SCALE, getColor: (d) => [...d.color, 255], pickable: true, material: { ambient: 0.55, diffuse: 0.6, shininess: 40, specularColor: [255, 255, 255] } }));
    L.push(new ScatterplotLayer({ id: "civic-crew-beacons", data: vans, getPosition: (d) => [d.pos.p[1], d.pos.p[0], 3.4], getRadius: 1.3, radiusUnits: "meters", radiusMinPixels: 2, getFillColor: (d) => (Math.floor(wall * 4) % 2 ? [255, 255, 255, 255] : [...d.color, 255]) }));
    L.push(new ScatterplotLayer({ id: "civic-inspection-scan", data: scans, getPosition: (d) => [d.p[1], d.p[0], 1.2], getRadius: (d) => d.r, radiusUnits: "meters", stroked: true, filled: false, getLineColor: (d) => [60, 200, 230, d.a], getLineWidth: 1.4, lineWidthUnits: "meters" }));
    L.push(new TextLayer({ id: "civic-work-labels", data: work, getPosition: (d) => [d.p[1], d.p[0], 14], getText: (d) => d.text, getSize: 11, getColor: [255, 255, 255, 255], getBackgroundColor: (d) => d.bg, background: true, backgroundPadding: [5, 2], fontFamily: "Poppins, system-ui, sans-serif", fontWeight: 600, billboard: true }));
    L.push(new TextLayer({ id: "civic-bubbles", data: bubbles, getPosition: (d) => [d.p[1], d.p[0], 18], getText: (d) => d.text, getSize: 10.5, getColor: [20, 22, 24, 255], getBackgroundColor: [255, 255, 255, 235], getBorderColor: (d) => [...d.color, 255], getBorderWidth: 1.5, background: true, backgroundPadding: [5, 2], fontFamily: "Poppins, system-ui, sans-serif", fontWeight: 500, billboard: true, characterSet: "auto" }));
    L.push(new ScatterplotLayer({ id: "civic-rings", data: rings, getPosition: (d) => [d.p[1], d.p[0], 2], getRadius: (d) => d.r, radiusUnits: "meters", stroked: true, filled: false, getLineColor: (d) => [...d.c, d.a], getLineWidth: 2.4, lineWidthUnits: "meters", lineWidthMinPixels: 1.5 }));
    L.push(new ColumnLayer({ id: "civic-root-beams", data: rootPts, getPosition: (d) => [d.p[1], d.p[0]], getElevation: (d) => (d.fixed ? 40 : 75), radius: 3, diskResolution: 16, extruded: true, getFillColor: (d) => (d.fixed ? [22, 160, 80, 220] : [...ROOT_RED, 235]), pickable: true, onClick: ({ object }) => object && onSelect?.(object), material: { ambient: 1, diffuse: 0.2 } }));
    L.push(new TextLayer({ id: "civic-root-labels", data: rootPts, getPosition: (d) => [d.p[1], d.p[0], d.fixed ? 46 : 82], getText: (d) => `${d.fixed ? "FIXED" : "ROOT CAUSE"} · ${d.where.asset}`, getSize: 12, getColor: [255, 255, 255, 255], getBackgroundColor: (d) => (d.fixed ? [22, 130, 70, 235] : [176, 24, 24, 235]), background: true, backgroundPadding: [6, 3], fontFamily: "Poppins, system-ui, sans-serif", fontWeight: 600, billboard: true, pickable: true, onClick: ({ object }) => object && onSelect?.(object) }));
    L.push(new ScatterplotLayer({ id: "civic-hypotheses", data: hypPts, getPosition: (d) => [d.p[1], d.p[0], 2], getRadius: 5, radiusUnits: "meters", radiusMinPixels: 6, getFillColor: [240, 150, 40, 240], stroked: true, getLineColor: [255, 255, 255, 255], lineWidthMinPixels: 2, pickable: true, onClick: ({ object }) => object && onSelect?.(object) }));
    L.push(new TextLayer({ id: "civic-block-labels", data: view?.zoom >= 15.8 ? blocks : [], getPosition: (b) => [b.lon, b.lat, 2], getText: (b) => b.name, getSize: 10, getColor: [255, 255, 255, 230], getBackgroundColor: [12, 16, 14, 140], background: true, backgroundPadding: [4, 1], fontFamily: "Poppins, system-ui, sans-serif", billboard: true }));
    return L;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frame, model, state, complaints, diagnosis, crews, show, selected, theme]);

  const onLoad = useCallback((e) => {
    const m = e.target;
    const ensure = () => {
      const has = m.getStyle()?.layers?.some((l) => l.type === "fill-extrusion");
      if (!has && m.getSource("openmaptiles")) m.addLayer(BUILDINGS_3D(theme === "dark" ? "#2a2f2c" : "#d8d3cb", 0.45));
    };
    const sky = () => {
      if (typeof m.setSky !== "function") return;
      m.setSky(theme === "dark"
        ? { "sky-color": "#0d1512", "horizon-color": "#1d2a24", "fog-color": "#111816", "sky-horizon-blend": 0.7, "horizon-fog-blend": 0.6, "fog-ground-blend": 0.9 }
        : { "sky-color": "#bcd6ea", "horizon-color": "#eef1ef", "fog-color": "#f1f1ef", "sky-horizon-blend": 0.6, "horizon-fog-blend": 0.5, "fog-ground-blend": 0.92 });
    };
    ensure(); sky();
    m.on("styledata", () => { ensure(); sky(); });
  }, [theme]);

  if (!model || !view) return <div className="empty" style={{ color: "#ccc", paddingTop: 200 }}>Connecting to the civic simulator (port 8005)…</div>;

  return (
    <>
      <MapGL ref={mapRef} {...view} onMove={(e) => { if (!follow) setView(e.viewState); }}
        mapStyle={mode === "satellite" ? SATELLITE : theme === "dark" ? STYLE_DARK : STYLE_LIGHT}
        onLoad={onLoad} maxPitch={80} maxZoom={mode === "satellite" ? 19.5 : 22} attributionControl={{ compact: true }} style={{ width: "100%", height: "100%" }}>
        <NavigationControl position="bottom-right" visualizePitch />
        <DeckOverlay layers={layers}
          getTooltip={({ object }) => object?.tip && { text: object.tip, style: { background: "rgba(12,16,14,.92)", color: "#eef0ee", borderRadius: "10px", font: "11px Poppins, system-ui", maxWidth: "340px", padding: "6px 9px", whiteSpace: "pre-line" } }} />
      </MapGL>
      <div className="map-overlay tr cam-bar" role="group" aria-label="Camera">
        <button className={!follow && view.pitch < 66 ? "on" : ""} onClick={() => { setFollow(false); setView(overview); }}><MapIcon size={13} /> Overview</button>
        <button onClick={() => { setFollow(false); setView({ ...overview, zoom: 17.2, pitch: 72, latitude: overview.latitude + 0.0012 }); }}><Eye size={13} /> Street level</button>
        <button className={follow ? "on" : ""} disabled={!crews.length && !follow} onClick={() => setFollow(!follow)}><Crosshair size={13} /> {follow ? "Stop following" : "Follow a crew"}</button>
      </div>
      {overlays}
    </>
  );
}
