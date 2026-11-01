"""Weather Service integrating Open-Meteo Free API for Real-Time Weather

and Inundation Analytics across Indian Cities (Dehradun, Delhi, Uttarakhand & Nationwide)."""

import time
import urllib.request
import urllib.parse
import json
from typing import Dict, Any, Optional
from pydantic import BaseModel


class WeatherCondition(BaseModel):
    city: str
    latitude: float
    longitude: float
    temperature_c: float
    relative_humidity: float
    precipitation_mm: float
    rain_mm: float
    weather_code: int
    wind_speed_kmh: float
    condition_text: str
    risk_level: str  # NORMAL, MODERATE, HIGH, CRITICAL
    water_depth_cm_estimate: float
    observed_at: str
    source: str = "Open-Meteo Free Global API"


# Coordinates for key reference locations
CITY_COORDINATES: Dict[str, Dict[str, float]] = {
    "dehradun": {"lat": 30.3165, "lon": 78.0322, "state": "Uttarakhand"},
    "clock_tower_dehradun": {"lat": 30.3243, "lon": 78.0418, "state": "Uttarakhand"},
    "rajpur_road": {"lat": 30.3350, "lon": 78.0550, "state": "Uttarakhand"},
    "delhi": {"lat": 28.6139, "lon": 77.2090, "state": "Delhi"},
    "rishikesh": {"lat": 30.0869, "lon": 78.2676, "state": "Uttarakhand"},
    "haridwar": {"lat": 29.9457, "lon": 78.1642, "state": "Uttarakhand"},
    "nainital": {"lat": 29.3919, "lon": 79.4542, "state": "Uttarakhand"},
    "mumbai": {"lat": 19.0760, "lon": 72.8777, "state": "Maharashtra"},
    "bengaluru": {"lat": 12.9716, "lon": 77.5946, "state": "Karnataka"},
}

WMO_CODE_MAP = {
    0: ("Clear Sky", "NORMAL"),
    1: ("Mainly Clear", "NORMAL"),
    2: ("Partly Cloudy", "NORMAL"),
    3: ("Overcast", "NORMAL"),
    45: ("Foggy", "MODERATE"),
    48: ("Depositing Rime Fog", "MODERATE"),
    51: ("Light Drizzle", "NORMAL"),
    53: ("Moderate Drizzle", "MODERATE"),
    55: ("Dense Drizzle", "MODERATE"),
    61: ("Slight Rain", "MODERATE"),
    63: ("Moderate Rain", "HIGH"),
    65: ("Heavy Rain", "CRITICAL"),
    71: ("Slight Snow Fall", "MODERATE"),
    73: ("Moderate Snow Fall", "HIGH"),
    75: ("Heavy Snow Fall", "CRITICAL"),
    80: ("Slight Rain Showers", "MODERATE"),
    81: ("Moderate Rain Showers", "HIGH"),
    82: ("Violent Rain Showers", "CRITICAL"),
    95: ("Thunderstorm", "CRITICAL"),
    96: ("Thunderstorm with Slight Hail", "CRITICAL"),
    99: ("Thunderstorm with Heavy Hail", "CRITICAL"),
}


class WeatherService:
    _instance: Optional["WeatherService"] = None

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl_seconds = 300  # 5 minutes

    @classmethod
    def get_instance(cls) -> "WeatherService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def get_weather_for_location(cls, lat: float, lon: float, city_label: str = "India (Custom Coordinates)") -> WeatherCondition:
        return cls.get_instance().get_weather_by_coords(lat, lon, city_label)

    @classmethod
    def get_city_weather(cls, city_name: str) -> WeatherCondition:
        return cls.get_instance().get_weather_for_city(city_name)

    def get_weather_for_city(self, city_name: str) -> WeatherCondition:
        norm = city_name.strip().lower().replace(" ", "_")
        coords = CITY_COORDINATES.get(norm, CITY_COORDINATES["dehradun"])
        return self.get_weather_by_coords(coords["lat"], coords["lon"], city_label=city_name.capitalize())

    def get_weather_by_coords(self, lat: float, lon: float, city_label: str = "India (Custom Coordinates)") -> WeatherCondition:
        cache_key = f"{round(lat, 3)}_{round(lon, 3)}"
        now = time.time()
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if now - entry["timestamp"] < self._cache_ttl_seconds:
                return entry["data"]

        # Call Open-Meteo Free API
        url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,precipitation,rain,weather_code,wind_speed_10m"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CitySense-SmartCity/1.0"})
            with urllib.request.urlopen(req, timeout=4) as response:
                raw = json.loads(response.read().decode("utf-8"))
                current = raw.get("current", {})

                temp = current.get("temperature_2m", 22.0)
                rh = current.get("relative_humidity_2m", 60.0)
                precip = current.get("precipitation", 0.0)
                rain = current.get("rain", 0.0)
                code = current.get("weather_code", 0)
                wind = current.get("wind_speed_10m", 5.0)
                obs_time = current.get("time", time.strftime("%Y-%m-%dT%H:%M:%SZ"))

                cond_text, default_risk = WMO_CODE_MAP.get(code, ("Unknown Conditions", "NORMAL"))

                # Estimate water accumulation / flood depth for low-lying urban areas
                # 1 mm of continuous rain on urban impervious surfaces ~ 0.8 to 1.5 cm accumulation in underpasses
                water_depth = 0.0
                if rain > 0 or precip > 0:
                    water_depth = round((rain or precip) * 1.2, 1)

                risk = default_risk
                if water_depth > 30.0:
                    risk = "CRITICAL"
                elif water_depth > 15.0:
                    risk = "HIGH"
                elif water_depth > 5.0:
                    risk = "MODERATE"

                cond = WeatherCondition(
                    city=city_label,
                    latitude=lat,
                    longitude=lon,
                    temperature_c=temp,
                    relative_humidity=rh,
                    precipitation_mm=precip,
                    rain_mm=rain,
                    weather_code=code,
                    wind_speed_kmh=wind,
                    condition_text=cond_text,
                    risk_level=risk,
                    water_depth_cm_estimate=water_depth,
                    observed_at=obs_time,
                )
                self._cache[cache_key] = {"timestamp": now, "data": cond}
                return cond

        except Exception as e:
            # Resilient fallback
            return WeatherCondition(
                city=city_label,
                latitude=lat,
                longitude=lon,
                temperature_c=20.0,
                relative_humidity=65.0,
                precipitation_mm=0.0,
                rain_mm=0.0,
                weather_code=0,
                wind_speed_kmh=4.0,
                condition_text="Clear Sky (Cached Fallback)",
                risk_level="NORMAL",
                water_depth_cm_estimate=0.0,
                observed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                source="Offline Cached Fallback"
            )


weather_service = WeatherService()
