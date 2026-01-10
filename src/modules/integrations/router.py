"""
Integrations API Router
Endpoints for external service integrations (EPİAŞ, Weather, Telegram).
"""
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.core.auth0 import Auth0User, get_current_user_auth0
from src.modules.integrations.epias import get_epias_service
from src.modules.integrations.weather import TURKISH_CITIES, get_weather_service

router = APIRouter(prefix="/integrations", tags=["integrations"])


# ============================================
# SCHEMAS
# ============================================

class EPIASPriceResponse(BaseModel):
    date: str
    prices: list[dict[str, Any]]
    average_price: float | None


class WeatherResponse(BaseModel):
    location: str | None
    temperature: float | None
    feels_like: float | None
    humidity: int | None
    description: str | None
    wind_speed: float | None


class CostCalculationRequest(BaseModel):
    consumption_kwh: float


class CostCalculationResponse(BaseModel):
    consumption_kwh: float
    price_per_kwh: float | None
    cost: float | None
    currency: str = "TRY"


# ============================================
# EPİAŞ INTEGRATION (Bağlantı Yönetimi)
# ============================================
# NOT: Fiyat verileri için /api/v1/market/epias/* endpoint'lerini kullanın.
# Bu endpoint'ler sadece bağlantı testi ve API key yönetimi içindir.

@router.get("/epias/status")
async def get_epias_status(
    user: Auth0User = Depends(get_current_user_auth0),
) -> dict[str, Any]:
    """
    EPİAŞ API bağlantı durumunu kontrol et.
    
    **NOT**: Fiyat verileri için `/api/v1/market/epias/prices/current` kullanın.
    Bu endpoint sadece bağlantı testi içindir.
    """
    service = get_epias_service()
    
    return {
        "service": "epias",
        "status": "connected" if service else "not_configured",
        "message": "Fiyat verileri için /api/v1/market/epias/* kullanın",
    }


# ============================================
# WEATHER ENDPOINTS
# ============================================

@router.get("/weather/current", response_model=WeatherResponse)
async def get_current_weather(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    user: Auth0User = Depends(get_current_user_auth0),
) -> WeatherResponse:
    """
    Get current weather conditions for a location.
    """
    service = get_weather_service()
    
    if not service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Weather service not configured",
        )
    
    data = await service.get_current(lat, lon)
    
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weather data not available",
        )
    
    return WeatherResponse(**data)


@router.get("/weather/city/{city_name}", response_model=WeatherResponse)
async def get_weather_by_city(
    city_name: str,
    user: Auth0User = Depends(get_current_user_auth0),
) -> WeatherResponse:
    """
    Get current weather for a Turkish city.
    
    Supported cities: istanbul, ankara, izmir, bursa, antalya, adana, konya, gaziantep, mersin, diyarbakir
    """
    service = get_weather_service()
    
    if not service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Weather service not configured",
        )
    
    city_lower = city_name.lower()
    if city_lower not in TURKISH_CITIES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"City not found. Available: {', '.join(TURKISH_CITIES.keys())}",
        )
    
    coords = TURKISH_CITIES[city_lower]
    data = await service.get_current(coords["lat"], coords["lon"])
    
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weather data not available",
        )
    
    return WeatherResponse(**data)


@router.get("/weather/forecast")
async def get_weather_forecast(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    user: Auth0User = Depends(get_current_user_auth0),
) -> dict[str, Any]:
    """
    Get 5-day weather forecast (3-hour intervals).
    """
    service = get_weather_service()
    
    if not service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Weather service not configured",
        )
    
    forecasts = await service.get_forecast(lat, lon)
    
    return {
        "location": {"lat": lat, "lon": lon},
        "forecasts": forecasts,
        "count": len(forecasts),
    }


# ============================================
# HEALTH CHECK
# ============================================

@router.get("/health")
async def integrations_health() -> dict[str, Any]:
    """
    Check health of external integrations.
    """
    from src.modules.integrations.telegram import get_telegram_service
    
    epias = get_epias_service()
    weather = get_weather_service()
    telegram = get_telegram_service()
    
    return {
        "epias": {
            "configured": epias.is_authenticated,
            "status": "ok" if epias.is_authenticated else "not_configured",
        },
        "weather": {
            "configured": weather.is_configured,
            "status": "ok" if weather.is_configured else "not_configured",
        },
        "telegram": {
            "configured": telegram.is_configured,
            "status": "ok" if telegram.is_configured else "not_configured",
        },
    }
