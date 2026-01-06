"""
OpenWeather API Integration
Fetches weather data for energy consumption predictions.
"""
from typing import Any

import httpx

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

OPENWEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5"


class WeatherService:
    """
    OpenWeather API Service.
    
    Provides weather data for:
    - Current conditions
    - Forecasts
    - Historical data
    
    Usage:
        weather = WeatherService()
        current = await weather.get_current(lat=41.0082, lon=28.9784)  # Istanbul
    """
    
    def __init__(self, api_key: str | None = None):
        """
        Initialize Weather service.
        
        Args:
            api_key: OpenWeather API key. Uses settings if not provided.
        """
        self.api_key = api_key or settings.openweather_api_key
        self._client: httpx.AsyncClient | None = None
    
    @property
    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def _request(self, endpoint: str, **params) -> dict[str, Any] | None:
        """
        Make a request to OpenWeather API.
        
        Args:
            endpoint: API endpoint
            **params: Query parameters
            
        Returns:
            API response or None on error
        """
        if not self.is_configured:
            logger.warning("OpenWeather API not configured")
            return None
        
        client = await self._get_client()
        url = f"{OPENWEATHER_BASE_URL}/{endpoint}"
        
        params["appid"] = self.api_key
        params.setdefault("units", "metric")
        
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error("Weather API request failed", endpoint=endpoint, error=str(e))
            return None
    
    async def get_current(
        self,
        lat: float,
        lon: float,
        lang: str = "tr",
    ) -> dict[str, Any] | None:
        """
        Get current weather conditions.
        
        Args:
            lat: Latitude
            lon: Longitude
            lang: Language code
            
        Returns:
            Current weather data
        """
        data = await self._request("weather", lat=lat, lon=lon, lang=lang)
        
        if not data:
            return None
        
        return {
            "location": data.get("name"),
            "temperature": data.get("main", {}).get("temp"),
            "feels_like": data.get("main", {}).get("feels_like"),
            "humidity": data.get("main", {}).get("humidity"),
            "pressure": data.get("main", {}).get("pressure"),
            "wind_speed": data.get("wind", {}).get("speed"),
            "description": data.get("weather", [{}])[0].get("description"),
            "icon": data.get("weather", [{}])[0].get("icon"),
            "clouds": data.get("clouds", {}).get("all"),
            "visibility": data.get("visibility"),
            "sunrise": data.get("sys", {}).get("sunrise"),
            "sunset": data.get("sys", {}).get("sunset"),
        }
    
    async def get_forecast(
        self,
        lat: float,
        lon: float,
        lang: str = "tr",
    ) -> list[dict[str, Any]]:
        """
        Get 5-day weather forecast (3-hour intervals).
        
        Args:
            lat: Latitude
            lon: Longitude
            lang: Language code
            
        Returns:
            List of forecast data points
        """
        data = await self._request("forecast", lat=lat, lon=lon, lang=lang)
        
        if not data:
            return []
        
        forecasts = []
        for item in data.get("list", []):
            forecasts.append({
                "timestamp": item.get("dt"),
                "datetime": item.get("dt_txt"),
                "temperature": item.get("main", {}).get("temp"),
                "feels_like": item.get("main", {}).get("feels_like"),
                "humidity": item.get("main", {}).get("humidity"),
                "description": item.get("weather", [{}])[0].get("description"),
                "wind_speed": item.get("wind", {}).get("speed"),
                "clouds": item.get("clouds", {}).get("all"),
                "pop": item.get("pop"),  # Probability of precipitation
            })
        
        return forecasts
    
    async def get_by_city(
        self,
        city: str,
        country_code: str = "TR",
        lang: str = "tr",
    ) -> dict[str, Any] | None:
        """
        Get current weather by city name.
        
        Args:
            city: City name
            country_code: ISO country code
            lang: Language code
            
        Returns:
            Current weather data
        """
        q = f"{city},{country_code}"
        data = await self._request("weather", q=q, lang=lang)
        
        if not data:
            return None
        
        return {
            "location": data.get("name"),
            "country": data.get("sys", {}).get("country"),
            "temperature": data.get("main", {}).get("temp"),
            "feels_like": data.get("main", {}).get("feels_like"),
            "humidity": data.get("main", {}).get("humidity"),
            "description": data.get("weather", [{}])[0].get("description"),
            "wind_speed": data.get("wind", {}).get("speed"),
        }


# Singleton instance
_weather_service: WeatherService | None = None


def get_weather_service() -> WeatherService:
    """Get or create Weather service singleton."""
    global _weather_service
    if _weather_service is None:
        _weather_service = WeatherService()
    return _weather_service


# Turkish city coordinates
TURKISH_CITIES = {
    "istanbul": {"lat": 41.0082, "lon": 28.9784},
    "ankara": {"lat": 39.9334, "lon": 32.8597},
    "izmir": {"lat": 38.4192, "lon": 27.1287},
    "bursa": {"lat": 40.1885, "lon": 29.0610},
    "antalya": {"lat": 36.8969, "lon": 30.7133},
    "adana": {"lat": 37.0000, "lon": 35.3213},
    "konya": {"lat": 37.8746, "lon": 32.4932},
    "gaziantep": {"lat": 37.0662, "lon": 37.3833},
    "mersin": {"lat": 36.8121, "lon": 34.6415},
    "diyarbakir": {"lat": 37.9144, "lon": 40.2306},
}
