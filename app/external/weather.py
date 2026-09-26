"""
Weather service using the Open-Meteo API (https://api.open-meteo.com).

Open-Meteo is a free, no-API-key-required weather API. This service
routes all HTTP requests through ExternalHttpClient to enforce the
domain allowlist and SSRF protections. The two domains used are:
  - geocoding-api.open-meteo.com  (location name → lat/lon)
  - api.open-meteo.com            (lat/lon → current weather)

DESIGN: the service accepts a human-readable location string, resolves it
to coordinates via the geocoding endpoint, then fetches current conditions.
This is intentional: asking the LLM to supply lat/lon would require it to
hallucinate or look up coordinates itself, introducing inaccuracy. The
location string keeps tool arguments natural-language-friendly.
"""

from __future__ import annotations

from typing import Any

from app.external.client import ExternalHttpClient, ExternalRequestError

# WMO Weather interpretation codes (subset covering common codes)
# Source: https://open-meteo.com/en/docs
_WMO_CODES: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Icy fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with heavy hail",
}


class WeatherService:
    """Fetches current weather for a given location name via Open-Meteo."""

    GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, client: ExternalHttpClient | None = None) -> None:
        self._client = client or ExternalHttpClient()

    def get_current_weather(self, location: str) -> dict[str, Any]:
        """Return a clean weather summary dict for `location`.

        Returns dict with keys:
            location_name, country, latitude, longitude,
            temperature_c, humidity_pct, wind_speed_mph,
            conditions, conditions_code, data_time
        Raises ExternalRequestError on any network or allowlist failure.
        Raises ValueError if the location cannot be found.
        """
        # Step 1: Geocode the location name to lat/lon
        geo_data = self._client.get(
            self.GEOCODING_URL,
            params={"name": location, "count": 1, "format": "json"},
        )

        if not isinstance(geo_data, dict) or not geo_data.get("results"):
            raise ValueError(
                f"Location '{location}' could not be found via Open-Meteo geocoding."
            )

        result = geo_data["results"][0]
        lat: float = result["latitude"]
        lon: float = result["longitude"]
        location_name: str = result.get("name", location)
        country: str = result.get("country", "")

        # Step 2: Fetch current weather for those coordinates
        weather_data = self._client.get(
            self.FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                "wind_speed_unit": "mph",
                "temperature_unit": "celsius",
                "forecast_days": 1,
            },
        )

        if not isinstance(weather_data, dict) or "current" not in weather_data:
            raise ExternalRequestError(
                "Unexpected response format from Open-Meteo forecast API."
            )

        current = weather_data["current"]
        weather_code: int = int(current.get("weather_code", -1))
        conditions = _WMO_CODES.get(weather_code, f"Unknown (code {weather_code})")

        return {
            "location_name": location_name,
            "country": country,
            "latitude": lat,
            "longitude": lon,
            "temperature_c": current.get("temperature_2m"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "wind_speed_mph": current.get("wind_speed_10m"),
            "conditions": conditions,
            "conditions_code": weather_code,
            "data_time": current.get("time"),
        }
