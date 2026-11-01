"""HTTP integrations used by agent tools.

Every function returns a plain dict and raises ``IntegrationUnavailable`` when the backing
service is not configured or not reachable, so callers can fall back to clearly-labelled
sample data (``served="fallback"``, ``simulated=True``).

Backends
--------
- Complaint module (port 8001)   ``COMPLAINT_SERVICE_URL``  — ticket lifecycle, SLA escalation.
- Emergency routing (port 8002)  ``EMERGENCY_SERVICE_URL``  — dispatch, corridors, hospitals, CCTV feed.
- Core gateway (port 8080)       ``CORE_SERVICE_URL``       — public city events.
- Public data (opt-in)           ``PUBLIC_DATA_APIS=1``     — Nominatim geocoding, Open-Meteo air quality.
"""

from __future__ import annotations

import math
from typing import Any

import httpx

from src.config import settings

TIMEOUT = httpx.Timeout(8.0, connect=3.0)


class IntegrationUnavailable(RuntimeError):
    pass


async def _request(method: str, base: str | None, path: str, **kwargs: Any) -> Any:
    if not base:
        raise IntegrationUnavailable(f"{path}: service URL not configured")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
            response = await client.request(method, f"{base}{path}", **kwargs)
    except httpx.HTTPError as exc:
        raise IntegrationUnavailable(f"{path}: {exc.__class__.__name__}") from exc
    if response.status_code == 404:
        raise LookupError("not_found")
    if response.status_code >= 400:
        raise IntegrationUnavailable(f"{path}: HTTP {response.status_code}")
    return response.json()


# ── Complaint module (8001) ──────────────────────────────────────────────────

async def complaint_get(tracking_id: str) -> dict[str, Any]:
    return await _request("GET", settings.complaint_service_url, f"/api/complaints/{tracking_id}")


async def complaint_list() -> list[dict[str, Any]]:
    return await _request("GET", settings.complaint_service_url, "/api/complaints")


async def complaint_create(
    args: dict[str, Any], lat: float | None, lng: float | None, photo: tuple[bytes, str, str] | None = None
) -> dict[str, Any]:
    form = {
        "title": f"{args['category']} at {args['location']}"[:200],
        "description": args["description"],
        "category": args["category"],
        "address": args["location"],
    }
    if lat is not None and lng is not None:
        form.update(lat=str(lat), lng=str(lng))
    files = {"photo": (photo[2], photo[0], photo[1])} if photo else None
    return await _request("POST", settings.complaint_service_url, "/api/complaints", data=form, files=files)


async def complaint_escalate(tracking_id: str) -> dict[str, Any]:
    return await _request("POST", settings.complaint_service_url, f"/api/complaints/{tracking_id}/escalate-tick")


async def complaint_reassign(tracking_id: str, reason: str) -> dict[str, Any]:
    return await _request(
        "POST", settings.complaint_service_url, f"/api/complaints/{tracking_id}/reassign", json={"reason": reason}
    )


# ── Emergency routing (8002) ─────────────────────────────────────────────────

async def emergency_dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    return await _request("POST", settings.emergency_service_url, "/api/dispatch", json=payload)


async def emergency_corridor(origin: str, destination: str, vehicle_type: str) -> dict[str, Any]:
    return await _request(
        "POST", settings.emergency_service_url, "/api/corridor",
        json={"origin": origin, "destination": destination, "vehicle_type": vehicle_type},
    )


async def emergency_signal_override(payload: dict[str, Any]) -> dict[str, Any]:
    return await _request("POST", settings.emergency_service_url, "/api/signals/override", json=payload)


async def emergency_nearest_hospital(location: str, lat: float | None, lng: float | None) -> dict[str, Any]:
    params: dict[str, Any] = {"location": location}
    if lat is not None and lng is not None:
        params.update(lat=lat, lon=lng)
    return await _request("GET", settings.emergency_service_url, "/api/hospitals/nearest", params=params)


async def emergency_incidents(limit: int) -> dict[str, Any]:
    return await _request("GET", settings.emergency_service_url, "/api/incidents", params={"limit": limit})


async def emergency_weather(lat: float | None = None, lng: float | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"city": "Dehradun"}
    if lat is not None and lng is not None:
        params.update(lat=lat, lon=lng)
    return await _request("GET", settings.emergency_service_url, "/api/weather/current", params=params)


# ── Core gateway (8080) ──────────────────────────────────────────────────────

async def core_city_events() -> list[dict[str, Any]]:
    return await _request("GET", settings.core_service_url, "/api/city-events")


def _citizen_auth() -> dict[str, str]:
    from src.agent.request_context import user_bearer

    bearer = user_bearer.get()
    if not bearer:
        raise IntegrationUnavailable("no citizen token for core")
    return {"Authorization": bearer}


async def core_incidents() -> list[dict[str, Any]]:
    """Incidents visible to this citizen (core enforces what they may see)."""
    return await _request("GET", settings.core_service_url, "/api/incidents", headers=_citizen_auth())


async def core_find_avatars(query: str, lat: float | None, lng: float | None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"q": query}
    if lat is not None and lng is not None:
        params.update(lat=lat, lng=lng, radiusMeters=50000)
    return await _request("GET", settings.core_service_url, "/api/avatars", params=params, headers=_citizen_auth())


async def core_businesses(
    lat: float | None, lng: float | None, *, radius_m: float | None = None, category: str | None = None,
    query: str | None = None, limit: int = 6,
) -> list[dict[str, Any]]:
    """Popular local businesses from core's city directory (public, nearest first)."""
    params: dict[str, Any] = {"limit": limit}
    if lat is not None and lng is not None:
        params.update(lat=lat, lng=lng)
        if radius_m:
            params["radiusMeters"] = radius_m
    if category:
        params["category"] = category
    if query:
        params["q"] = query
    return await _request("GET", settings.core_service_url, "/api/businesses", params=params)


async def complaint_notices(limit: int) -> list[dict[str, Any]]:
    """Government notices published to the complaint module (read side is public)."""
    return await _request("GET", settings.complaint_service_url, "/api/notices", params={"limit": limit})


# ── Public data APIs (opt-in) ────────────────────────────────────────────────

def _public_enabled() -> None:
    if not settings.public_data_apis:
        raise IntegrationUnavailable("PUBLIC_DATA_APIS disabled")


async def nominatim_search(query: str) -> dict[str, Any] | None:
    _public_enabled()
    rows = await _request(
        "GET", settings.nominatim_url, "/search",
        params={"q": f"{query}, Dehradun", "format": "jsonv2", "limit": 1, "countrycodes": "in"},
        headers={"User-Agent": settings.geo_user_agent},
    )
    if not rows:
        return None
    row = rows[0]
    return {"lat": float(row["lat"]), "lng": float(row["lon"]), "display_name": row.get("display_name", query)}


async def nominatim_reverse(lat: float, lng: float) -> dict[str, Any]:
    _public_enabled()
    row = await _request(
        "GET", settings.nominatim_url, "/reverse",
        params={"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 17},
        headers={"User-Agent": settings.geo_user_agent},
    )
    return {"display_name": row.get("display_name"), "address": row.get("address", {})}


async def open_meteo_air_quality(lat: float, lng: float) -> dict[str, Any]:
    _public_enabled()
    data = await _request(
        "GET", "https://air-quality-api.open-meteo.com", "/v1/air-quality",
        params={"latitude": lat, "longitude": lng, "current": "pm10,pm2_5,us_aqi,european_aqi"},
    )
    return data.get("current", {})


# ── Offline gazetteer ────────────────────────────────────────────────────────
# Approximate centroids of well-known Dehradun landmarks, used when Nominatim is disabled or
# unreachable. Responses built from these are marked precision="approximate"; zones come from
# data/corpus/municipal/nnd_wards_directory_and_helplines.md.
GAZETTEER: dict[str, dict[str, Any]] = {
    "clock tower": {"lat": 30.3243, "lng": 78.0418, "zone": "Zone 1 (Central)", "aliases": ["ghanta ghar", "घंटाघर"]},
    "paltan bazaar": {"lat": 30.3226, "lng": 78.0428, "zone": "Zone 1 (Central)", "aliases": ["पलटन बाजार"]},
    "dhamawala": {"lat": 30.3236, "lng": 78.0396, "zone": "Zone 1 (Central)", "aliases": []},
    "rajpur road": {"lat": 30.3400, "lng": 78.0600, "zone": "Zone 2 (North)", "aliases": ["राजपुर रोड"]},
    "jakhan": {"lat": 30.3600, "lng": 78.0700, "zone": "Zone 2 (North)", "aliases": ["जाखन"]},
    "dalanwala": {"lat": 30.3180, "lng": 78.0600, "zone": "Zone 2 (North)", "aliases": []},
    "karanpur": {"lat": 30.3290, "lng": 78.0520, "zone": "Zone 2 (North)", "aliases": []},
    "patel nagar": {"lat": 30.3030, "lng": 78.0220, "zone": "Zone 3 (South)", "aliases": []},
    "clement town": {"lat": 30.26133, "lng": 78.01201, "zone": "Zone 3 (South)", "aliases": []},
    "majra": {"lat": 30.29300, "lng": 78.00264, "zone": "Zone 3 (South)", "aliases": []},
    "dharampur": {"lat": 30.3000, "lng": 78.0500, "zone": "Zone 4 (Trans-Rispana)", "aliases": []},
    "nehru colony": {"lat": 30.2960, "lng": 78.0570, "zone": "Zone 4 (Trans-Rispana)", "aliases": []},
    "isbt": {"lat": 30.28791, "lng": 77.99803, "zone": "Zone 3 (South)", "aliases": ["bus stand"]},  # in Majra (OSM)
    # Points around Clement Town / Bell Road from OpenStreetMap Nominatim (2026-11-01).
    "kargi chowk": {"lat": 30.28837, "lng": 78.02394, "zone": "Zone 3 (South)", "aliases": ["kargi"]},
    "graphic era": {"lat": 30.26802, "lng": 77.99612, "zone": None, "aliases": ["bell road"]},
    "mindrolling monastery": {"lat": 30.26182, "lng": 77.99732, "zone": None, "aliases": ["mindrolling", "great stupa"]},
    "mohabbewala": {"lat": 30.27097, "lng": 77.98265, "zone": None, "aliases": []},
    "prem nagar": {"lat": 30.3340, "lng": 77.9600, "zone": None, "aliases": []},
    "sahastradhara road": {"lat": 30.3400, "lng": 78.0800, "zone": None, "aliases": []},
    "ballupur": {"lat": 30.3350, "lng": 78.0100, "zone": None, "aliases": []},
    "gandhi park": {"lat": 30.3263, "lng": 78.0485, "zone": "Zone 1 (Central)", "aliases": ["गांधी पार्क"]},
    "parade ground": {"lat": 30.3266, "lng": 78.0459, "zone": "Zone 1 (Central)", "aliases": []},
    "subhash road": {"lat": 30.3250, "lng": 78.0480, "zone": "Zone 1 (Central)", "aliases": []},
    "it park": {"lat": 30.3600, "lng": 78.0800, "zone": None, "aliases": []},
    "doon hospital": {"lat": 30.3215, "lng": 78.0406, "zone": "Zone 1 (Central)", "aliases": []},
}
CITY_CENTRE = {"lat": 30.3243, "lng": 78.0418}


def gazetteer_lookup(text: str) -> tuple[str, dict[str, Any]] | None:
    lower = text.lower()
    for name, entry in GAZETTEER.items():
        if name in lower or any(alias in lower for alias in entry["aliases"]):
            return name, entry
    return None


def gazetteer_nearest(lat: float, lng: float) -> tuple[str, dict[str, Any], float]:
    def dist(entry: dict[str, Any]) -> float:
        return math.hypot(entry["lat"] - lat, (entry["lng"] - lng) * math.cos(math.radians(lat))) * 111.0

    name, entry = min(GAZETTEER.items(), key=lambda kv: dist(kv[1]))
    return name, entry, round(dist(entry), 2)
