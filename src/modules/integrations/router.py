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
# EPİAŞ ENDPOINTS
# ============================================

@router.get("/epias/prices", response_model=EPIASPriceResponse)
async def get_electricity_prices(
    target_date: date | None = Query(None, description="Date to fetch prices for (default: today)"),
    user: Auth0User = Depends(get_current_user_auth0),
) -> EPIASPriceResponse:
    """
    Get day-ahead electricity prices from EPİAŞ.
    
    Returns hourly PTF (Piyasa Takas Fiyatı) prices in TRY/MWh.
    """
    service = get_epias_service()
    prices = await service.get_day_ahead_prices(target_date)
    avg_price = await service.get_average_price(target_date)
    
    return EPIASPriceResponse(
        date=(target_date or date.today()).isoformat(),
        prices=prices,
        average_price=float(avg_price) if avg_price else None,
    )


@router.get("/epias/current-price")
async def get_current_electricity_price(
    user: Auth0User = Depends(get_current_user_auth0),
) -> dict[str, Any]:
    """
    Get current hour's electricity price.
    """
    service = get_epias_service()
    price = await service.get_hourly_price()
    
    if price is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Current price not available",
        )
    
    return {
        "price_per_mwh": float(price),
        "price_per_kwh": float(price / 1000),
        "currency": "TRY",
    }


@router.post("/epias/calculate-cost", response_model=CostCalculationResponse)
async def calculate_electricity_cost(
    request: CostCalculationRequest,
    user: Auth0User = Depends(get_current_user_auth0),
) -> CostCalculationResponse:
    """
    Calculate electricity cost for given consumption.
    """
    service = get_epias_service()
    result = await service.calculate_cost(request.consumption_kwh)
    
    return CostCalculationResponse(
        consumption_kwh=result["consumption_kwh"],
        price_per_kwh=result.get("price_per_kwh"),
        cost=result.get("cost"),
    )


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
