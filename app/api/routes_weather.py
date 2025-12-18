"""
Weather Routes - Hava Durumu API Endpoints.

OpenWeather entegrasyonu ile hava durumu verileri.
Enerji tüketim tahminleri ve otomasyon kuralları için kullanılır.
"""
import logging
from typing import Tuple
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, Response
from flasgger import swag_from

from app.auth import requires_auth
from app.api.helpers import get_current_user, get_pagination_params, paginate_response
from app.services.weather_service import weather_service
from app.models import Organization
from app.models.weather import WeatherData, WeatherForecast
from app.extensions import db
from app.exceptions import error_response, success_response, not_found_response
from app.constants import HttpStatus

logger = logging.getLogger(__name__)

weather_bp = Blueprint("weather", __name__)


@weather_bp.route("/current", methods=["GET", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Weather"],
    "summary": "Anlık hava durumu",
    "description": "Organization lokasyonu veya verilen koordinatlar için anlık hava durumu.",
    "security": [{"bearerAuth": []}],
    "parameters": [
        {
            "name": "lat",
            "in": "query",
            "type": "number",
            "description": "Enlem (opsiyonel, yoksa organization lokasyonu kullanılır)"
        },
        {
            "name": "lon",
            "in": "query",
            "type": "number",
            "description": "Boylam (opsiyonel)"
        },
        {
            "name": "save",
            "in": "query",
            "type": "boolean",
            "default": False,
            "description": "Veriyi veritabanına kaydet"
        }
    ],
    "responses": {
        200: {
            "description": "Hava durumu verisi",
            "schema": {
                "type": "object",
                "properties": {
                    "temperature": {"type": "number"},
                    "feels_like": {"type": "number"},
                    "humidity": {"type": "integer"},
                    "weather_main": {"type": "string"},
                    "weather_description": {"type": "string"},
                    "wind_speed": {"type": "number"},
                    "location_name": {"type": "string"}
                }
            }
        },
        401: {"description": "Yetkisiz erişim"},
        404: {"description": "Lokasyon bulunamadı"},
        503: {"description": "Hava durumu servisi kullanılamıyor"}
    }
})
def get_current_weather() -> Tuple[Response, int]:
    """Anlık hava durumu getir."""
    user = get_current_user()
    if not user or not user.organization_id:
        return error_response("Unauthorized", HttpStatus.UNAUTHORIZED)
    
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    save_to_db = request.args.get("save", "false").lower() == "true"
    
    # Koordinatlar verilmemişse organization'dan al
    if lat is None or lon is None:
        org = Organization.query.get(user.organization_id)
        if not org:
            return not_found_response("Organization")
        
        location = org.location or {}
        lat = location.get("latitude") or location.get("lat")
        lon = location.get("longitude") or location.get("lon")
        
        if lat is None or lon is None:
            return error_response(
                "Organization location not configured. Please set latitude/longitude in organization settings.",
                HttpStatus.BAD_REQUEST
            )
    
    # Hava durumu çek
    weather_data = weather_service.get_current_weather(lat, lon)
    if not weather_data:
        return error_response(
            "Weather service unavailable",
            HttpStatus.SERVICE_UNAVAILABLE
        )
    
    # Veritabanına kaydet (opsiyonel)
    if save_to_db:
        try:
            recorded_at = datetime.fromisoformat(weather_data["recorded_at"].replace("Z", "+00:00"))
            
            weather_record = WeatherData(
                organization_id=user.organization_id,
                latitude=lat,
                longitude=lon,
                location_name=weather_data.get("location_name"),
                recorded_at=recorded_at,
                temperature=weather_data.get("temperature"),
                feels_like=weather_data.get("feels_like"),
                humidity=weather_data.get("humidity"),
                pressure=weather_data.get("pressure"),
                wind_speed=weather_data.get("wind_speed"),
                wind_direction=weather_data.get("wind_direction"),
                wind_gust=weather_data.get("wind_gust"),
                clouds=weather_data.get("clouds"),
                visibility=weather_data.get("visibility"),
                rain_1h=weather_data.get("rain_1h", 0),
                rain_3h=weather_data.get("rain_3h", 0),
                snow_1h=weather_data.get("snow_1h", 0),
                snow_3h=weather_data.get("snow_3h", 0),
                weather_main=weather_data.get("weather_main"),
                weather_description=weather_data.get("weather_description"),
                weather_icon=weather_data.get("weather_icon"),
                sunrise=datetime.fromisoformat(weather_data["sunrise"].replace("Z", "+00:00")) if weather_data.get("sunrise") else None,
                sunset=datetime.fromisoformat(weather_data["sunset"].replace("Z", "+00:00")) if weather_data.get("sunset") else None,
                raw_data=weather_data.get("raw_data", {}),
                source="openweather"
            )
            db.session.add(weather_record)
            db.session.commit()
            logger.info(f"Weather data saved for org {user.organization_id}")
        except Exception as e:
            logger.error(f"Failed to save weather data: {e}")
            db.session.rollback()
    
    return jsonify(weather_data), HttpStatus.OK


@weather_bp.route("/forecast", methods=["GET", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Weather"],
    "summary": "5 günlük hava durumu tahmini",
    "description": "3 saatlik aralıklarla 5 günlük tahmin verisi.",
    "security": [{"bearerAuth": []}],
    "parameters": [
        {
            "name": "lat",
            "in": "query",
            "type": "number",
            "description": "Enlem"
        },
        {
            "name": "lon",
            "in": "query",
            "type": "number",
            "description": "Boylam"
        },
        {
            "name": "save",
            "in": "query",
            "type": "boolean",
            "default": False,
            "description": "Veriyi veritabanına kaydet"
        }
    ],
    "responses": {
        200: {
            "description": "Tahmin listesi",
            "schema": {
                "type": "object",
                "properties": {
                    "forecasts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "forecast_time": {"type": "string", "format": "date-time"},
                                "temperature": {"type": "number"},
                                "humidity": {"type": "integer"},
                                "weather_main": {"type": "string"}
                            }
                        }
                    },
                    "count": {"type": "integer"}
                }
            }
        }
    }
})
def get_weather_forecast() -> Tuple[Response, int]:
    """5 günlük hava durumu tahmini getir."""
    user = get_current_user()
    if not user or not user.organization_id:
        return error_response("Unauthorized", HttpStatus.UNAUTHORIZED)
    
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    save_to_db = request.args.get("save", "false").lower() == "true"
    
    # Koordinatlar verilmemişse organization'dan al
    if lat is None or lon is None:
        org = Organization.query.get(user.organization_id)
        if not org:
            return not_found_response("Organization")
        
        location = org.location or {}
        lat = location.get("latitude") or location.get("lat")
        lon = location.get("longitude") or location.get("lon")
        
        if lat is None or lon is None:
            return error_response(
                "Organization location not configured",
                HttpStatus.BAD_REQUEST
            )
    
    # Tahmin çek
    forecasts = weather_service.get_forecast(lat, lon)
    if not forecasts:
        return error_response(
            "Weather service unavailable",
            HttpStatus.SERVICE_UNAVAILABLE
        )
    
    # Veritabanına kaydet (opsiyonel)
    if save_to_db:
        try:
            for fc in forecasts:
                forecast_time = datetime.fromisoformat(fc["forecast_time"].replace("Z", "+00:00"))
                
                # Upsert - varsa güncelle, yoksa ekle
                existing = WeatherForecast.query.filter_by(
                    organization_id=user.organization_id,
                    forecast_time=forecast_time
                ).first()
                
                if existing:
                    existing.temperature = fc.get("temperature")
                    existing.feels_like = fc.get("feels_like")
                    existing.temp_min = fc.get("temp_min")
                    existing.temp_max = fc.get("temp_max")
                    existing.humidity = fc.get("humidity")
                    existing.pressure = fc.get("pressure")
                    existing.clouds = fc.get("clouds")
                    existing.wind_speed = fc.get("wind_speed")
                    existing.wind_direction = fc.get("wind_direction")
                    existing.pop = fc.get("pop")
                    existing.rain_3h = fc.get("rain_3h", 0)
                    existing.snow_3h = fc.get("snow_3h", 0)
                    existing.weather_main = fc.get("weather_main")
                    existing.weather_description = fc.get("weather_description")
                    existing.weather_icon = fc.get("weather_icon")
                    existing.fetched_at = datetime.now(timezone.utc)
                else:
                    forecast_record = WeatherForecast(
                        organization_id=user.organization_id,
                        latitude=lat,
                        longitude=lon,
                        forecast_time=forecast_time,
                        temperature=fc.get("temperature"),
                        feels_like=fc.get("feels_like"),
                        temp_min=fc.get("temp_min"),
                        temp_max=fc.get("temp_max"),
                        humidity=fc.get("humidity"),
                        pressure=fc.get("pressure"),
                        clouds=fc.get("clouds"),
                        wind_speed=fc.get("wind_speed"),
                        wind_direction=fc.get("wind_direction"),
                        pop=fc.get("pop"),
                        rain_3h=fc.get("rain_3h", 0),
                        snow_3h=fc.get("snow_3h", 0),
                        weather_main=fc.get("weather_main"),
                        weather_description=fc.get("weather_description"),
                        weather_icon=fc.get("weather_icon"),
                        source="openweather"
                    )
                    db.session.add(forecast_record)
            
            db.session.commit()
            logger.info(f"Forecast data saved for org {user.organization_id}")
        except Exception as e:
            logger.error(f"Failed to save forecast data: {e}")
            db.session.rollback()
    
    return jsonify({
        "forecasts": forecasts,
        "count": len(forecasts),
        "location": {"lat": lat, "lon": lon}
    }), HttpStatus.OK


@weather_bp.route("/geocode", methods=["GET", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Weather"],
    "summary": "Şehir adından koordinat bul",
    "security": [{"bearerAuth": []}],
    "parameters": [
        {
            "name": "city",
            "in": "query",
            "type": "string",
            "required": True,
            "description": "Şehir adı"
        },
        {
            "name": "country",
            "in": "query",
            "type": "string",
            "default": "TR",
            "description": "Ülke kodu (ISO 3166)"
        }
    ],
    "responses": {
        200: {
            "description": "Lokasyon bilgisi",
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "lat": {"type": "number"},
                    "lon": {"type": "number"},
                    "country": {"type": "string"}
                }
            }
        }
    }
})
def geocode_city() -> Tuple[Response, int]:
    """Şehir adından koordinat bul."""
    user = get_current_user()
    if not user:
        return error_response("Unauthorized", HttpStatus.UNAUTHORIZED)
    
    city = request.args.get("city", "").strip()
    country = request.args.get("country", "TR").strip().upper()
    
    if not city:
        return error_response("City name is required", HttpStatus.BAD_REQUEST)
    
    results = weather_service.geocode(city, country)
    if not results:
        return not_found_response(f"Location: {city}, {country}")
    
    return jsonify({
        "locations": results,
        "count": len(results)
    }), HttpStatus.OK


@weather_bp.route("/history", methods=["GET", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Weather"],
    "summary": "Geçmiş hava durumu verileri",
    "description": "Veritabanında kayıtlı hava durumu geçmişi.",
    "security": [{"bearerAuth": []}],
    "parameters": [
        {
            "name": "page",
            "in": "query",
            "type": "integer",
            "default": 1
        },
        {
            "name": "pageSize",
            "in": "query",
            "type": "integer",
            "default": 20
        },
        {
            "name": "start_date",
            "in": "query",
            "type": "string",
            "format": "date",
            "description": "Başlangıç tarihi (YYYY-MM-DD)"
        },
        {
            "name": "end_date",
            "in": "query",
            "type": "string",
            "format": "date",
            "description": "Bitiş tarihi (YYYY-MM-DD)"
        }
    ],
    "responses": {
        200: {
            "description": "Hava durumu geçmişi"
        }
    }
})
def get_weather_history() -> Tuple[Response, int]:
    """Geçmiş hava durumu verilerini getir."""
    user = get_current_user()
    if not user or not user.organization_id:
        return error_response("Unauthorized", HttpStatus.UNAUTHORIZED)
    
    page, page_size = get_pagination_params()
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    
    query = WeatherData.query.filter_by(
        organization_id=user.organization_id
    ).order_by(WeatherData.recorded_at.desc())
    
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
            query = query.filter(WeatherData.recorded_at >= start_dt)
        except ValueError:
            pass
    
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
            query = query.filter(WeatherData.recorded_at <= end_dt)
        except ValueError:
            pass
    
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return jsonify(paginate_response(
        [w.to_summary_dict() for w in items],
        total,
        page,
        page_size
    )), HttpStatus.OK


@weather_bp.route("/analysis/solar", methods=["GET", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Weather"],
    "summary": "Güneş enerjisi analizi",
    "description": "Mevcut hava durumunun güneş enerjisi üretimi için uygunluğu.",
    "security": [{"bearerAuth": []}],
    "responses": {
        200: {
            "description": "Analiz sonucu",
            "schema": {
                "type": "object",
                "properties": {
                    "is_good": {"type": "boolean"},
                    "reason": {"type": "string"},
                    "recommendation": {"type": "string"}
                }
            }
        }
    }
})
def analyze_solar_conditions() -> Tuple[Response, int]:
    """Güneş enerjisi üretimi için hava durumu analizi."""
    user = get_current_user()
    if not user or not user.organization_id:
        return error_response("Unauthorized", HttpStatus.UNAUTHORIZED)
    
    org = Organization.query.get(user.organization_id)
    if not org:
        return not_found_response("Organization")
    
    location = org.location or {}
    lat = location.get("latitude") or location.get("lat")
    lon = location.get("longitude") or location.get("lon")
    
    if lat is None or lon is None:
        return error_response(
            "Organization location not configured",
            HttpStatus.BAD_REQUEST
        )
    
    is_good, reason = weather_service.is_good_weather_for_solar(lat, lon)
    
    recommendation = (
        "Solar panels are operating at optimal efficiency."
        if is_good else
        "Consider using grid power or stored energy."
    )
    
    return jsonify({
        "is_good": is_good,
        "reason": reason,
        "recommendation": recommendation,
        "location": {"lat": lat, "lon": lon}
    }), HttpStatus.OK


@weather_bp.route("/analysis/hvac", methods=["GET", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Weather"],
    "summary": "HVAC tasarruf analizi",
    "description": "Mevcut hava durumunun HVAC tasarrufu için uygunluğu.",
    "security": [{"bearerAuth": []}],
    "responses": {
        200: {
            "description": "Analiz sonucu"
        }
    }
})
def analyze_hvac_conditions() -> Tuple[Response, int]:
    """HVAC tasarrufu için hava durumu analizi."""
    user = get_current_user()
    if not user or not user.organization_id:
        return error_response("Unauthorized", HttpStatus.UNAUTHORIZED)
    
    org = Organization.query.get(user.organization_id)
    if not org:
        return not_found_response("Organization")
    
    location = org.location or {}
    lat = location.get("latitude") or location.get("lat")
    lon = location.get("longitude") or location.get("lon")
    
    if lat is None or lon is None:
        return error_response(
            "Organization location not configured",
            HttpStatus.BAD_REQUEST
        )
    
    is_good, reason = weather_service.is_good_weather_for_hvac_savings(lat, lon)
    
    recommendation = (
        "HVAC system can be turned off to save energy."
        if is_good else
        "HVAC system should remain active for comfort."
    )
    
    return jsonify({
        "can_save": is_good,
        "reason": reason,
        "recommendation": recommendation,
        "location": {"lat": lat, "lon": lon}
    }), HttpStatus.OK
