import type { Feature, Polygon } from "geojson";

/** Geodesic circle approximated as a polygon, for drawing the geofence. */
export function circlePolygon(lat: number, lng: number, radiusMeters: number, steps = 72): Feature<Polygon> {
  const R = 6371008.8;
  const d = radiusMeters / R;
  const latR = (lat * Math.PI) / 180;
  const lngR = (lng * Math.PI) / 180;
  const ring: [number, number][] = [];
  for (let i = 0; i <= steps; i++) {
    const brg = (2 * Math.PI * i) / steps;
    const lat2 = Math.asin(Math.sin(latR) * Math.cos(d) + Math.cos(latR) * Math.sin(d) * Math.cos(brg));
    const lng2 = lngR + Math.atan2(Math.sin(brg) * Math.sin(d) * Math.cos(latR), Math.cos(d) - Math.sin(latR) * Math.sin(lat2));
    ring.push([(lng2 * 180) / Math.PI, (lat2 * 180) / Math.PI]);
  }
  return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [ring] } };
}

/** [west, south, east, north] box enclosing a circle of radiusMeters. */
export function boundsAround(lat: number, lng: number, radiusMeters: number): [number, number, number, number] {
  const dLat = radiusMeters / 111320;
  const dLng = radiusMeters / (111320 * Math.cos((lat * Math.PI) / 180));
  return [lng - dLng, lat - dLat, lng + dLng, lat + dLat];
}

export function formatDistance(m?: number | null): string {
  if (m == null) return "";
  return m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(m < 10000 ? 1 : 0)} km`;
}

export function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
