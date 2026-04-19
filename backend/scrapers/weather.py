"""
OpenWeatherMap weather fetcher.
Free tier: 1,000 calls/day.
Fetches current + 5-day forecast for stadium coordinates.
"""
from typing import Optional
from datetime import datetime
from scrapers.base import ScraperBase
from app.core.config import settings
from app.core.logging import logger


class WeatherScraper(ScraperBase):
    SOURCE_NAME = "openweathermap"
    BASE_URL = "https://api.openweathermap.org/data/2.5"
    CACHE_TTL = 3600 * 3  # 3 hours

    def scrape_league_season(self, league_slug: str, season: str) -> list[dict]:
        """Not applicable for weather — use get_match_weather() directly."""
        return []

    def get_match_weather(
        self,
        lat: float,
        lon: float,
        match_timestamp: Optional[int] = None
    ) -> dict:
        """
        Get weather for a stadium location at match time.
        Uses current weather or 5-day forecast depending on match proximity.
        """
        if not settings.OPENWEATHER_API_KEY:
            logger.warning("OpenWeatherMap API key not configured")
            return {}

        try:
            if match_timestamp:
                hours_until = (match_timestamp - datetime.utcnow().timestamp()) / 3600
                if hours_until > 5 * 24:
                    return {}  # Too far in future for free tier
                elif hours_until > 3:
                    return self._get_forecast(lat, lon, match_timestamp)

            return self._get_current(lat, lon)
        except Exception as e:
            logger.error("Weather fetch failed", lat=lat, lon=lon, error=str(e))
            return {}

    def _get_current(self, lat: float, lon: float) -> dict:
        url = f"{self.BASE_URL}/weather"
        params = {
            "lat": lat,
            "lon": lon,
            "appid": settings.OPENWEATHER_API_KEY,
            "units": "metric",
        }
        data = self.fetch_json(url, params=params)
        return self._parse_weather(data)

    def _get_forecast(self, lat: float, lon: float, target_timestamp: int) -> dict:
        url = f"{self.BASE_URL}/forecast"
        params = {
            "lat": lat,
            "lon": lon,
            "appid": settings.OPENWEATHER_API_KEY,
            "units": "metric",
        }
        data = self.fetch_json(url, params=params)
        forecasts = data.get("list", [])

        # Find closest forecast to match time
        closest = min(
            forecasts,
            key=lambda f: abs(f.get("dt", 0) - target_timestamp),
            default=None,
        )
        return self._parse_weather(closest) if closest else {}

    def _parse_weather(self, data: dict) -> dict:
        if not data:
            return {}
        main = data.get("main", {})
        wind = data.get("wind", {})
        rain = data.get("rain", {})
        weather = data.get("weather", [{}])[0]

        return {
            "temp_c": main.get("temp"),
            "feels_like_c": main.get("feels_like"),
            "humidity_pct": main.get("humidity"),
            "precipitation_mm": rain.get("1h", rain.get("3h", 0.0)),
            "wind_speed_kmh": round((wind.get("speed", 0) * 3.6), 1),
            "wind_gust_kmh": round((wind.get("gust", 0) * 3.6), 1),
            "condition": weather.get("main", ""),
            "condition_desc": weather.get("description", ""),
            "is_rainy": weather.get("main", "").lower() in ("rain", "drizzle", "thunderstorm"),
            "is_heavy_rain": rain.get("1h", 0) > 5,
        }
