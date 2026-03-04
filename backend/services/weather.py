"""Weather service using Open-Meteo API (free, no API key).

Supports:
- City from user message (with disambiguation when multiple matches)
- Qualitative labels: very cold, cold, cool, mild, warm, very warm, hot; rainy; windy
- Accurate date resolution: today, tomorrow, this weekend (next Sat), next week (next Mon)
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Unambiguous city -> (lat, lon) fallbacks. Exclude cities that exist in multiple countries (London, Paris).
CITY_COORDS = {
    "san francisco": (37.7749, -122.4194),
    "sf": (37.7749, -122.4194),
    "new york": (40.7128, -74.0060),
    "nyc": (40.7128, -74.0060),
    "los angeles": (34.0522, -118.2437),
    "la": (34.0522, -118.2437),
    "chicago": (41.8781, -87.6298),
    "seattle": (47.6062, -122.3321),
    "boston": (42.3601, -71.0589),
    "austin": (30.2672, -97.7431),
    "denver": (39.7392, -104.9903),
    "miami": (25.7617, -80.1918),
}

# Country code -> display name
COUNTRY_NAMES = {
    "US": "United States",
    "GB": "United Kingdom",
    "CA": "Canada",
    "AU": "Australia",
    "FR": "France",
    "DE": "Germany",
    "IN": "India",
    "JP": "Japan",
}

WEATHER_TRIGGER_PATTERNS = (
    r"\btomorrow\b",
    r"\btoday\b",
    r"\bthis week\b",
    r"\bthis weekend\b",
    r"\bnext week\b",
    r"\bmorning\b",
    r"\bevening\b",
    r"\boutdoor\b",
    r"\boutside\b",
    r"\bweather\b",
    r"\brain\b",
    r"\bcold\b",
    r"\bhot\b",
    r"\bwarm\b",
    r"\bcool\b",
)


def _geocode_search(location: str, count: int = 5) -> list[dict]:
    """Search for places. Returns list of {name, country_code, admin1, latitude, longitude}."""
    loc = (location or "").strip()
    if not loc:
        return []
    loc_lower = loc.lower()
    if loc_lower in CITY_COORDS:
        lat, lon = CITY_COORDS[loc_lower]
        return [{"name": loc.title(), "country_code": "?", "admin1": "", "latitude": lat, "longitude": lon}]
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(GEOCODING_URL, params={"name": location, "count": count})
            r.raise_for_status()
            data = r.json()
            return data.get("results", [])
    except Exception:
        return []


def _geocode_resolve(location: str) -> tuple[Optional[tuple[float, float]], Optional[str]]:
    """
    Resolve location to (lat, lon) or return disambiguation message.
    Returns (coords, None) if single match, (None, disambiguation_msg) if multiple, (None, None) if not found.
    """
    loc = (location or "").strip()
    if not loc:
        return (None, None)
    loc_lower = loc.lower()
    if loc_lower in CITY_COORDS:
        return (CITY_COORDS[loc_lower], None)
    results = _geocode_search(location, count=5)
    if not results:
        return (None, None)
    # Dedupe by (country_code, admin1) to detect multiple cities
    seen = set()
    unique = []
    for r in results:
        key = (r.get("country_code", ""), r.get("admin1", ""))
        if key not in seen:
            seen.add(key)
            unique.append(r)
    if len(unique) == 1:
        r = unique[0]
        return ((r["latitude"], r["longitude"]), None)
    # Multiple places: build disambiguation message
    parts = []
    for i, r in enumerate(unique[:5], 1):
        name = r.get("name", "?")
        cc = r.get("country_code", "")
        admin1 = r.get("admin1", "")
        country = COUNTRY_NAMES.get(cc, cc)
        if admin1:
            label = f"{i}) {name}, {admin1}, {country}"
        else:
            label = f"{i}) {name}, {country}"
        parts.append(label)
    msg = (
        f"Multiple places named \"{location}\" found. Which one does the user mean? "
        f"Ask them to specify: {'; '.join(parts)}"
    )
    return (None, msg)


def _target_day_index(query: str) -> int:
    """
    Compute days ahead for the target date. Uses real calendar.
    0=today, 1=tomorrow, N=days until target.
    """
    q = (query or "").lower()
    now = datetime.now(timezone.utc)
    today = now.date()

    if re.search(r"\btoday\b", q):
        return 0
    if re.search(r"\btomorrow\b", q):
        return 1
    if re.search(r"\bthis weekend\b", q):
        # Next Saturday (weekday 5)
        wd = today.weekday()  # Mon=0, Sat=5, Sun=6
        return (5 - wd) % 7 if wd != 5 else 0
    if re.search(r"\bnext week\b", q):
        # Next Monday
        wd = today.weekday()
        return 7 if wd == 0 else 7 - wd
    if re.search(r"\bthis week\b", q):
        # Use 3 days ahead as a reasonable "this week" target
        return min(3, 6 - today.weekday()) if today.weekday() < 6 else 1
    return 1  # default: tomorrow


def _temp_label(temp_f: float) -> str:
    """Qualitative temperature label."""
    if temp_f < 35:
        return "very cold"
    if temp_f < 45:
        return "cold"
    if temp_f < 55:
        return "cool"
    if temp_f < 65:
        return "mild"
    if temp_f < 75:
        return "warm"
    if temp_f < 85:
        return "very warm"
    return "hot"


def _day_label(days_ahead: int) -> str:
    """Human-readable day label."""
    if days_ahead == 0:
        return "Today"
    if days_ahead == 1:
        return "Tomorrow"
    d = datetime.now(timezone.utc).date() + timedelta(days=days_ahead)
    return d.strftime("%A, %b %d")


def fetch_forecast(lat: float, lon: float, days_ahead: int, location_name: str) -> Optional[str]:
    """
    Fetch forecast for (lat, lon). Returns human-readable summary with qualitative labels.
    """
    forecast_days = min(max(days_ahead + 1, 1), 16)  # Open-Meteo allows up to 16
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(
                FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max",
                    "forecast_days": forecast_days,
                    "timezone": "auto",
                    "temperature_unit": "fahrenheit",
                },
            )
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None

    daily = data.get("daily", {})
    temps_max = daily.get("temperature_2m_max", [])
    temps_min = daily.get("temperature_2m_min", [])
    precip = daily.get("precipitation_probability_max", [])
    wind = daily.get("wind_speed_10m_max", [])
    dates = daily.get("time", [])

    if not dates:
        return None

    idx = min(days_ahead, len(dates) - 1)
    temp_high = temps_max[idx] if idx < len(temps_max) else None
    temp_low = temps_min[idx] if idx < len(temps_min) else None
    rain_chance = precip[idx] if idx < len(precip) else None
    wind_speed = wind[idx] if idx < len(wind) else None

    parts = []
    if temp_high is not None and temp_low is not None:
        label = _temp_label((temp_high + temp_low) / 2)
        parts.append(f"{label} (high {temp_high}°F, low {temp_low}°F)")
    elif temp_high is not None:
        label = _temp_label(temp_high)
        parts.append(f"{label} (high {temp_high}°F)")
    if rain_chance is not None and rain_chance > 0:
        if rain_chance >= 50:
            parts.append("rainy")
        else:
            parts.append(f"{rain_chance}% chance of rain")
    if wind_speed is not None and wind_speed >= 30:  # 30 km/h ≈ 18 mph = windy
        parts.append("windy")
    if not parts:
        return None

    day_label = _day_label(days_ahead)
    return f"{day_label} in {location_name}: {', '.join(parts)}"


def query_needs_weather(query: str) -> bool:
    """True if the query implies weather should be considered."""
    q = (query or "").lower()
    return any(re.search(p, q, re.IGNORECASE) for p in WEATHER_TRIGGER_PATTERNS)


def get_weather_context(location: str, query: str) -> str:
    """
    Get weather context for the prompt. Returns:
    - Forecast string with qualitative labels if successful
    - Disambiguation message if multiple places match (agent should ask user)
    - Empty string if not needed or location not found
    """
    if not query_needs_weather(query):
        return ""
    coords, disambiguation = _geocode_resolve(location)
    if disambiguation:
        return f"### Weather (clarification needed)\n{disambiguation}\n"
    if not coords:
        return ""
    lat, lon = coords
    days_ahead = _target_day_index(query)
    location_name = location.strip() if location else "your location"
    forecast = fetch_forecast(lat, lon, days_ahead, location_name)
    if forecast:
        return f"### Weather\n{forecast}\n"
    return ""
