"""
Weather Celery Tasks - Periyodik hava durumu güncelleme.

Tüm organizasyonlar için hava durumu verilerini düzenli olarak çeker.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from celery import shared_task

from app.extensions import db
from app.models import Organization
from app.models.weather import WeatherData, WeatherForecast
from app.services.weather_service import weather_service

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="weather.fetch_current_for_all",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True
)
def fetch_weather_for_all_organizations(self) -> dict:
    """
    Tüm aktif organizasyonlar için anlık hava durumu çek.
    
    Her 15 dakikada bir çalıştırılmalı (Celery Beat).
    """
    from flask import current_app
    
    # Flask app context gerekli
    with current_app.app_context():
        organizations = Organization.query.filter_by(is_active=True).all()
        
        success_count = 0
        error_count = 0
        skipped_count = 0
        
        for org in organizations:
            location = org.location or {}
            lat = location.get("latitude") or location.get("lat")
            lon = location.get("longitude") or location.get("lon")
            
            if lat is None or lon is None:
                skipped_count += 1
                continue
            
            try:
                weather_data = weather_service.get_current_weather(lat, lon, use_cache=False)
                if not weather_data:
                    error_count += 1
                    continue
                
                # Veritabanına kaydet
                recorded_at = datetime.fromisoformat(
                    weather_data["recorded_at"].replace("Z", "+00:00")
                )
                
                # Aynı zaman damgası varsa atla (duplicate önleme)
                existing = WeatherData.query.filter_by(
                    organization_id=org.id,
                    recorded_at=recorded_at
                ).first()
                
                if existing:
                    skipped_count += 1
                    continue
                
                weather_record = WeatherData(
                    organization_id=org.id,
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
                success_count += 1
                
            except Exception as e:
                logger.error(f"Weather fetch failed for org {org.id}: {e}")
                db.session.rollback()
                error_count += 1
        
        result = {
            "success": success_count,
            "errors": error_count,
            "skipped": skipped_count,
            "total": len(organizations)
        }
        
        logger.info(f"Weather fetch completed: {result}")
        return result


@shared_task(
    bind=True,
    name="weather.fetch_forecast_for_all",
    max_retries=3,
    default_retry_delay=120
)
def fetch_forecast_for_all_organizations(self) -> dict:
    """
    Tüm aktif organizasyonlar için 5 günlük tahmin çek.
    
    Her saat başı çalıştırılmalı (Celery Beat).
    """
    from flask import current_app
    
    with current_app.app_context():
        organizations = Organization.query.filter_by(is_active=True).all()
        
        success_count = 0
        error_count = 0
        skipped_count = 0
        
        for org in organizations:
            location = org.location or {}
            lat = location.get("latitude") or location.get("lat")
            lon = location.get("longitude") or location.get("lon")
            
            if lat is None or lon is None:
                skipped_count += 1
                continue
            
            try:
                forecasts = weather_service.get_forecast(lat, lon, use_cache=False)
                if not forecasts:
                    error_count += 1
                    continue
                
                # Veritabanına kaydet (upsert)
                for fc in forecasts:
                    forecast_time = datetime.fromisoformat(
                        fc["forecast_time"].replace("Z", "+00:00")
                    )
                    
                    existing = WeatherForecast.query.filter_by(
                        organization_id=org.id,
                        forecast_time=forecast_time
                    ).first()
                    
                    if existing:
                        # Güncelle
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
                        # Yeni kayıt
                        forecast_record = WeatherForecast(
                            organization_id=org.id,
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
                success_count += 1
                
            except Exception as e:
                logger.error(f"Forecast fetch failed for org {org.id}: {e}")
                db.session.rollback()
                error_count += 1
        
        result = {
            "success": success_count,
            "errors": error_count,
            "skipped": skipped_count,
            "total": len(organizations)
        }
        
        logger.info(f"Forecast fetch completed: {result}")
        return result


@shared_task(name="weather.fetch_for_organization")
def fetch_weather_for_organization(organization_id: str) -> Optional[dict]:
    """
    Belirli bir organizasyon için hava durumu çek.
    
    Manuel tetikleme veya webhook için kullanılır.
    """
    from flask import current_app
    
    with current_app.app_context():
        org = Organization.query.get(organization_id)
        if not org:
            logger.warning(f"Organization not found: {organization_id}")
            return None
        
        location = org.location or {}
        lat = location.get("latitude") or location.get("lat")
        lon = location.get("longitude") or location.get("lon")
        
        if lat is None or lon is None:
            logger.warning(f"Organization {organization_id} has no location")
            return None
        
        weather_data = weather_service.get_current_weather(lat, lon, use_cache=False)
        if not weather_data:
            return None
        
        try:
            recorded_at = datetime.fromisoformat(
                weather_data["recorded_at"].replace("Z", "+00:00")
            )
            
            weather_record = WeatherData(
                organization_id=org.id,
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
            
            logger.info(f"Weather fetched for org {organization_id}")
            return weather_data
            
        except Exception as e:
            logger.error(f"Failed to save weather for org {organization_id}: {e}")
            db.session.rollback()
            return None


@shared_task(name="weather.cleanup_old_data")
def cleanup_old_weather_data(days: int = 30) -> dict:
    """
    Eski hava durumu verilerini temizle.
    
    Varsayılan: 30 günden eski veriler silinir.
    Günlük çalıştırılmalı.
    """
    from flask import current_app
    
    with current_app.app_context():
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Eski weather data sil
        weather_deleted = WeatherData.query.filter(
            WeatherData.recorded_at < cutoff_date
        ).delete(synchronize_session=False)
        
        # Geçmiş forecast'ları sil (forecast_time geçmiş olanlar)
        forecast_deleted = WeatherForecast.query.filter(
            WeatherForecast.forecast_time < datetime.now(timezone.utc)
        ).delete(synchronize_session=False)
        
        db.session.commit()
        
        result = {
            "weather_deleted": weather_deleted,
            "forecast_deleted": forecast_deleted,
            "cutoff_date": cutoff_date.isoformat()
        }
        
        logger.info(f"Weather cleanup completed: {result}")
        return result
