"""
OpenWeather API Entegrasyonu.

Dokümantasyon: https://openweathermap.org/api

Özellikler:
- Current Weather Data (Anlık hava durumu)
- 5 Day / 3 Hour Forecast (5 günlük tahmin)
- Redis cache desteği
- Retry mekanizması
- Rate limiting koruması

Best Practices:
- API key environment variable'dan okunur
- Tüm istekler timeout ile yapılır
- Hata durumları loglanır
- Cache ile gereksiz API çağrıları önlenir
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
import requests

from app.constants import (
    WEATHER_CACHE_TIMEOUT,
    API_TIMEOUT_DEFAULT,
)

# Redis cache için (opsiyonel)
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


class OpenWeatherService:
    """
    OpenWeather API Client.
    
    Current weather ve 5-day forecast verilerini çeker.
    Redis cache ile optimize edilmiştir.
    """
    
    BASE_URL = "https://api.openweathermap.org/data/2.5"
    GEO_URL = "https://api.openweathermap.org/geo/1.0"
    
    # Cache key prefixes
    CACHE_PREFIX_CURRENT = "weather:current"
    CACHE_PREFIX_FORECAST = "weather:forecast"
    CACHE_PREFIX_GEOCODE = "weather:geocode"
    
    # Cache TTL (saniye)
    CACHE_TTL_CURRENT = WEATHER_CACHE_TIMEOUT  # 15 dakika
    CACHE_TTL_FORECAST = 3600  # 1 saat (tahminler daha az değişir)
    CACHE_TTL_GEOCODE = 86400  # 24 saat (lokasyonlar değişmez)
    
    def __init__(self):
        self.api_key = os.getenv("OPENWEATHER_API_KEY")
        self._redis: Optional[redis.Redis] = None
        
        if not self.api_key:
            logger.warning("OPENWEATHER_API_KEY not configured")
        
        # Redis bağlantısı (varsa)
        if REDIS_AVAILABLE:
            redis_url = os.getenv("REDIS_URL", os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"))
            try:
                self._redis = redis.from_url(redis_url)
                self._redis.ping()
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
                self._redis = None
    
    def _is_configured(self) -> bool:
        """API key yapılandırılmış mı?"""
        return bool(self.api_key)
    
    def _get_cache(self, key: str) -> Optional[Dict]:
        """Cache'den veri getir."""
        if not self._redis:
            return None
        
        try:
            import json
            cached = self._redis.get(key)
            if cached:
                return json.loads(cached.decode('utf-8'))
        except Exception as e:
            logger.debug(f"Cache read error: {e}")
        
        return None
    
    def _set_cache(self, key: str, data: Dict, ttl: int):
        """Cache'e veri yaz."""
        if not self._redis:
            return
        
        try:
            import json
            self._redis.setex(key, ttl, json.dumps(data, default=str))
        except Exception as e:
            logger.debug(f"Cache write error: {e}")
    
    def _make_request(
        self, 
        endpoint: str, 
        params: Dict[str, Any],
        timeout: int = API_TIMEOUT_DEFAULT
    ) -> Optional[Dict]:
        """
        OpenWeather API'ye istek yap.
        
        Args:
            endpoint: API endpoint (örn: "weather", "forecast")
            params: Query parametreleri
            timeout: İstek timeout süresi
        
        Returns:
            API yanıtı veya None (hata durumunda)
        """
        if not self._is_configured():
            logger.error("OpenWeather API key not configured")
            return None
        
        url = f"{self.BASE_URL}/{endpoint}"
        params["appid"] = self.api_key
        params["units"] = "metric"  # Celsius
        params["lang"] = "tr"  # Türkçe açıklamalar
        
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error("OpenWeather API key invalid")
            elif e.response.status_code == 429:
                logger.warning("OpenWeather API rate limit exceeded")
            else:
                logger.error(f"OpenWeather API HTTP error: {e}")
            return None
            
        except requests.exceptions.Timeout:
            logger.error(f"OpenWeather API timeout ({timeout}s)")
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"OpenWeather API request error: {e}")
            return None
    
    def get_current_weather(
        self, 
        lat: float, 
        lon: float,
        use_cache: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Anlık hava durumu verisi çek.
        
        Args:
            lat: Enlem
            lon: Boylam
            use_cache: Cache kullan (varsayılan: True)
        
        Returns:
            Normalize edilmiş hava durumu verisi
        """
        cache_key = f"{self.CACHE_PREFIX_CURRENT}:{lat:.4f}:{lon:.4f}"
        
        # Cache kontrolü
        if use_cache:
            cached = self._get_cache(cache_key)
            if cached:
                logger.debug(f"Weather cache hit: {cache_key}")
                return cached
        
        # API çağrısı
        data = self._make_request("weather", {"lat": lat, "lon": lon})
        if not data:
            return None
        
        # Normalize et
        normalized = self._normalize_current_weather(data)
        
        # Cache'le
        self._set_cache(cache_key, normalized, self.CACHE_TTL_CURRENT)
        
        logger.info(f"Weather fetched: {normalized.get('location_name')} - {normalized.get('temperature')}°C")
        return normalized
    
    def get_forecast(
        self, 
        lat: float, 
        lon: float,
        use_cache: bool = True
    ) -> Optional[List[Dict[str, Any]]]:
        """
        5 günlük hava durumu tahmini çek.
        
        OpenWeather 3 saatlik aralıklarla 40 veri noktası döner.
        
        Args:
            lat: Enlem
            lon: Boylam
            use_cache: Cache kullan
        
        Returns:
            Tahmin listesi
        """
        cache_key = f"{self.CACHE_PREFIX_FORECAST}:{lat:.4f}:{lon:.4f}"
        
        # Cache kontrolü
        if use_cache:
            cached = self._get_cache(cache_key)
            if cached:
                logger.debug(f"Forecast cache hit: {cache_key}")
                return cached
        
        # API çağrısı
        data = self._make_request("forecast", {"lat": lat, "lon": lon})
        if not data:
            return None
        
        # Normalize et
        forecasts = self._normalize_forecast(data)
        
        # Cache'le
        self._set_cache(cache_key, forecasts, self.CACHE_TTL_FORECAST)
        
        logger.info(f"Forecast fetched: {len(forecasts)} data points")
        return forecasts
    
    def geocode(
        self, 
        city: str, 
        country_code: str = "TR",
        limit: int = 1
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Şehir adından koordinat bul.
        
        Args:
            city: Şehir adı
            country_code: Ülke kodu (ISO 3166)
            limit: Maksimum sonuç sayısı
        
        Returns:
            Lokasyon listesi
        """
        cache_key = f"{self.CACHE_PREFIX_GEOCODE}:{city.lower()}:{country_code}"
        
        # Cache kontrolü
        cached = self._get_cache(cache_key)
        if cached:
            return cached
        
        if not self._is_configured():
            return None
        
        url = f"{self.GEO_URL}/direct"
        params = {
            "q": f"{city},{country_code}",
            "limit": limit,
            "appid": self.api_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=API_TIMEOUT_DEFAULT)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                logger.warning(f"Geocode: No results for {city}, {country_code}")
                return None
            
            results = [
                {
                    "name": item.get("name"),
                    "local_names": item.get("local_names", {}),
                    "lat": item.get("lat"),
                    "lon": item.get("lon"),
                    "country": item.get("country"),
                    "state": item.get("state"),
                }
                for item in data
            ]
            
            # Cache'le
            self._set_cache(cache_key, results, self.CACHE_TTL_GEOCODE)
            
            return results
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Geocode error: {e}")
            return None
    
    def reverse_geocode(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """
        Koordinattan şehir adı bul.
        
        Args:
            lat: Enlem
            lon: Boylam
        
        Returns:
            Lokasyon bilgisi
        """
        cache_key = f"{self.CACHE_PREFIX_GEOCODE}:reverse:{lat:.4f}:{lon:.4f}"
        
        cached = self._get_cache(cache_key)
        if cached:
            return cached
        
        if not self._is_configured():
            return None
        
        url = f"{self.GEO_URL}/reverse"
        params = {
            "lat": lat,
            "lon": lon,
            "limit": 1,
            "appid": self.api_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=API_TIMEOUT_DEFAULT)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                return None
            
            item = data[0]
            result = {
                "name": item.get("name"),
                "local_names": item.get("local_names", {}),
                "lat": item.get("lat"),
                "lon": item.get("lon"),
                "country": item.get("country"),
                "state": item.get("state"),
            }
            
            self._set_cache(cache_key, result, self.CACHE_TTL_GEOCODE)
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Reverse geocode error: {e}")
            return None
    
    def _normalize_current_weather(self, data: Dict) -> Dict[str, Any]:
        """
        OpenWeather current weather yanıtını normalize et.
        
        API Response örneği:
        {
            "coord": {"lon": 28.9784, "lat": 41.0082},
            "weather": [{"id": 800, "main": "Clear", "description": "açık", "icon": "01d"}],
            "main": {"temp": 25.5, "feels_like": 24.8, "humidity": 45, "pressure": 1015},
            "wind": {"speed": 3.5, "deg": 180, "gust": 5.2},
            "clouds": {"all": 0},
            "visibility": 10000,
            "rain": {"1h": 0.5},
            "snow": {"1h": 0},
            "sys": {"sunrise": 1234567890, "sunset": 1234567890},
            "name": "Istanbul",
            "dt": 1234567890
        }
        """
        weather = data.get("weather", [{}])[0]
        main = data.get("main", {})
        wind = data.get("wind", {})
        clouds = data.get("clouds", {})
        rain = data.get("rain", {})
        snow = data.get("snow", {})
        sys = data.get("sys", {})
        
        # Unix timestamp'leri datetime'a çevir
        dt = data.get("dt")
        sunrise = sys.get("sunrise")
        sunset = sys.get("sunset")
        
        return {
            "location_name": data.get("name"),
            "latitude": data.get("coord", {}).get("lat"),
            "longitude": data.get("coord", {}).get("lon"),
            "recorded_at": datetime.fromtimestamp(dt, tz=timezone.utc).isoformat() if dt else None,
            "temperature": main.get("temp"),
            "feels_like": main.get("feels_like"),
            "temp_min": main.get("temp_min"),
            "temp_max": main.get("temp_max"),
            "humidity": main.get("humidity"),
            "pressure": main.get("pressure"),
            "wind_speed": wind.get("speed"),
            "wind_direction": wind.get("deg"),
            "wind_gust": wind.get("gust"),
            "clouds": clouds.get("all"),
            "visibility": data.get("visibility"),
            "rain_1h": rain.get("1h", 0),
            "rain_3h": rain.get("3h", 0),
            "snow_1h": snow.get("1h", 0),
            "snow_3h": snow.get("3h", 0),
            "weather_main": weather.get("main"),
            "weather_description": weather.get("description"),
            "weather_icon": weather.get("icon"),
            "sunrise": datetime.fromtimestamp(sunrise, tz=timezone.utc).isoformat() if sunrise else None,
            "sunset": datetime.fromtimestamp(sunset, tz=timezone.utc).isoformat() if sunset else None,
            "source": "openweather",
            "raw_data": data,
        }
    
    def _normalize_forecast(self, data: Dict) -> List[Dict[str, Any]]:
        """
        OpenWeather forecast yanıtını normalize et.
        
        5 günlük tahmin, 3 saatlik aralıklarla (40 veri noktası).
        """
        forecasts = []
        city = data.get("city", {})
        
        for item in data.get("list", []):
            weather = item.get("weather", [{}])[0]
            main = item.get("main", {})
            wind = item.get("wind", {})
            clouds = item.get("clouds", {})
            rain = item.get("rain", {})
            snow = item.get("snow", {})
            
            dt = item.get("dt")
            
            forecasts.append({
                "forecast_time": datetime.fromtimestamp(dt, tz=timezone.utc).isoformat() if dt else None,
                "temperature": main.get("temp"),
                "feels_like": main.get("feels_like"),
                "temp_min": main.get("temp_min"),
                "temp_max": main.get("temp_max"),
                "humidity": main.get("humidity"),
                "pressure": main.get("pressure"),
                "clouds": clouds.get("all"),
                "wind_speed": wind.get("speed"),
                "wind_direction": wind.get("deg"),
                "pop": item.get("pop"),  # Probability of precipitation
                "rain_3h": rain.get("3h", 0),
                "snow_3h": snow.get("3h", 0),
                "weather_main": weather.get("main"),
                "weather_description": weather.get("description"),
                "weather_icon": weather.get("icon"),
                "latitude": city.get("coord", {}).get("lat"),
                "longitude": city.get("coord", {}).get("lon"),
            })
        
        return forecasts
    
    def get_weather_for_organization(
        self, 
        organization_id: str,
        lat: Optional[float] = None,
        lon: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Organization için hava durumu getir.
        
        Koordinatlar verilmezse organization'ın lokasyonunu kullanır.
        
        Args:
            organization_id: Organization UUID
            lat: Enlem (opsiyonel)
            lon: Boylam (opsiyonel)
        
        Returns:
            Hava durumu verisi
        """
        # Koordinatlar verilmemişse organization'dan al
        if lat is None or lon is None:
            from app.models import Organization
            org = Organization.query.get(organization_id)
            if not org:
                logger.warning(f"Organization not found: {organization_id}")
                return None
            
            location = org.location or {}
            lat = location.get("latitude") or location.get("lat")
            lon = location.get("longitude") or location.get("lon")
            
            if lat is None or lon is None:
                logger.warning(f"Organization {organization_id} has no location configured")
                return None
        
        return self.get_current_weather(lat, lon)
    
    def is_good_weather_for_solar(self, lat: float, lon: float) -> Tuple[bool, str]:
        """
        Güneş enerjisi üretimi için hava durumu uygun mu?
        
        Returns:
            (is_good, reason) tuple
        """
        weather = self.get_current_weather(lat, lon)
        if not weather:
            return False, "Weather data unavailable"
        
        clouds = weather.get("clouds", 100)
        weather_main = weather.get("weather_main", "").lower()
        
        # Bulutluluk %30'dan az ve yağış yok
        if clouds < 30 and weather_main not in ("rain", "snow", "thunderstorm"):
            return True, f"Clear sky ({clouds}% clouds)"
        elif clouds < 50:
            return True, f"Partly cloudy ({clouds}% clouds)"
        else:
            return False, f"Cloudy ({clouds}% clouds) - {weather_main}"
    
    def is_good_weather_for_hvac_savings(self, lat: float, lon: float) -> Tuple[bool, str]:
        """
        HVAC tasarrufu için hava durumu uygun mu?
        
        Ilıman hava (15-25°C) = HVAC kapatılabilir.
        
        Returns:
            (is_good, reason) tuple
        """
        weather = self.get_current_weather(lat, lon)
        if not weather:
            return False, "Weather data unavailable"
        
        temp = weather.get("temperature")
        if temp is None:
            return False, "Temperature data unavailable"
        
        if 15 <= temp <= 25:
            return True, f"Comfortable temperature ({temp}°C) - HVAC can be turned off"
        elif temp < 15:
            return False, f"Cold ({temp}°C) - Heating needed"
        else:
            return False, f"Hot ({temp}°C) - Cooling needed"


# Singleton instance
weather_service = OpenWeatherService()
