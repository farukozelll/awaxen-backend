"""
Awaxen Models - Weather.

Hava durumu verisi modeli - OpenWeather API entegrasyonu.
Enerji tüketim tahminleri ve otomasyon kuralları için kullanılır.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import uuid

from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import validates

from app.extensions import db


def utcnow() -> datetime:
    """Timezone-aware UTC datetime döndür."""
    return datetime.now(timezone.utc)


class WeatherData(db.Model):
    """
    Hava Durumu Verisi - OpenWeather API'den çekilen veriler.
    
    Organization bazlı lokasyon için hava durumu saklanır.
    Enerji tüketim tahminleri ve HVAC otomasyonları için kullanılır.
    
    TimescaleDB hypertable olarak yapılandırılabilir (yüksek hacimli veri için).
    """
    __tablename__ = "weather_data"
    
    # Composite indexes for time-series queries
    __table_args__ = (
        db.Index('idx_weather_org_time', 'organization_id', 'recorded_at'),
        db.Index('idx_weather_location', 'latitude', 'longitude'),
        db.UniqueConstraint('organization_id', 'recorded_at', name='uq_weather_org_time'),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(
        UUID(as_uuid=True), 
        db.ForeignKey("organizations.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    
    # Lokasyon bilgisi
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    location_name = db.Column(db.String(200))  # Şehir/bölge adı
    
    # Zaman damgası
    recorded_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    
    # Temel hava durumu verileri
    temperature = db.Column(db.Float)  # Celsius
    feels_like = db.Column(db.Float)  # Hissedilen sıcaklık (Celsius)
    humidity = db.Column(db.Integer)  # % (0-100)
    pressure = db.Column(db.Integer)  # hPa
    
    # Rüzgar
    wind_speed = db.Column(db.Float)  # m/s
    wind_direction = db.Column(db.Integer)  # derece (0-360)
    wind_gust = db.Column(db.Float)  # m/s (ani rüzgar)
    
    # Bulutluluk ve görüş
    clouds = db.Column(db.Integer)  # % (0-100)
    visibility = db.Column(db.Integer)  # metre
    
    # Yağış
    rain_1h = db.Column(db.Float, default=0)  # mm (son 1 saat)
    rain_3h = db.Column(db.Float, default=0)  # mm (son 3 saat)
    snow_1h = db.Column(db.Float, default=0)  # mm (son 1 saat)
    snow_3h = db.Column(db.Float, default=0)  # mm (son 3 saat)
    
    # Hava durumu açıklaması
    weather_main = db.Column(db.String(50))  # Clear, Clouds, Rain, Snow, etc.
    weather_description = db.Column(db.String(200))  # Detaylı açıklama
    weather_icon = db.Column(db.String(10))  # OpenWeather icon kodu
    
    # Güneş bilgisi
    sunrise = db.Column(db.DateTime(timezone=True))
    sunset = db.Column(db.DateTime(timezone=True))
    
    # UV Index (varsa)
    uv_index = db.Column(db.Float)
    
    # Ham API yanıtı (debug/analiz için)
    raw_data = db.Column(JSONB, default=dict)
    
    # Veri kaynağı
    source = db.Column(db.String(50), default="openweather")
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, index=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "location": {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "name": self.location_name,
            },
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
            "temperature": self.temperature,
            "feels_like": self.feels_like,
            "humidity": self.humidity,
            "pressure": self.pressure,
            "wind": {
                "speed": self.wind_speed,
                "direction": self.wind_direction,
                "gust": self.wind_gust,
            },
            "clouds": self.clouds,
            "visibility": self.visibility,
            "precipitation": {
                "rain_1h": self.rain_1h,
                "rain_3h": self.rain_3h,
                "snow_1h": self.snow_1h,
                "snow_3h": self.snow_3h,
            },
            "weather": {
                "main": self.weather_main,
                "description": self.weather_description,
                "icon": self.weather_icon,
            },
            "sun": {
                "sunrise": self.sunrise.isoformat() if self.sunrise else None,
                "sunset": self.sunset.isoformat() if self.sunset else None,
            },
            "uv_index": self.uv_index,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def to_summary_dict(self) -> Dict[str, Any]:
        """Özet hava durumu bilgisi (dashboard için)."""
        return {
            "temperature": self.temperature,
            "feels_like": self.feels_like,
            "humidity": self.humidity,
            "weather_main": self.weather_main,
            "weather_description": self.weather_description,
            "weather_icon": self.weather_icon,
            "wind_speed": self.wind_speed,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
        }
    
    @validates('humidity')
    def validate_humidity(self, key: str, value: int) -> int:
        """Nem değeri 0-100 arasında olmalı."""
        if value is not None and not (0 <= value <= 100):
            raise ValueError("Humidity must be between 0 and 100")
        return value
    
    @validates('clouds')
    def validate_clouds(self, key: str, value: int) -> int:
        """Bulutluluk değeri 0-100 arasında olmalı."""
        if value is not None and not (0 <= value <= 100):
            raise ValueError("Clouds must be between 0 and 100")
        return value
    
    @validates('wind_direction')
    def validate_wind_direction(self, key: str, value: int) -> int:
        """Rüzgar yönü 0-360 arasında olmalı."""
        if value is not None and not (0 <= value <= 360):
            raise ValueError("Wind direction must be between 0 and 360")
        return value


class WeatherForecast(db.Model):
    """
    Hava Durumu Tahmini - 5 günlük tahmin verisi.
    
    Enerji tüketim planlaması ve otomasyon optimizasyonu için kullanılır.
    """
    __tablename__ = "weather_forecasts"
    
    __table_args__ = (
        db.Index('idx_forecast_org_time', 'organization_id', 'forecast_time'),
        db.UniqueConstraint('organization_id', 'forecast_time', name='uq_forecast_org_time'),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(
        UUID(as_uuid=True), 
        db.ForeignKey("organizations.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    
    # Lokasyon
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    
    # Tahmin zamanı
    forecast_time = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    
    # Sıcaklık
    temperature = db.Column(db.Float)
    feels_like = db.Column(db.Float)
    temp_min = db.Column(db.Float)
    temp_max = db.Column(db.Float)
    
    # Diğer veriler
    humidity = db.Column(db.Integer)
    pressure = db.Column(db.Integer)
    clouds = db.Column(db.Integer)
    wind_speed = db.Column(db.Float)
    wind_direction = db.Column(db.Integer)
    
    # Yağış olasılığı
    pop = db.Column(db.Float)  # Probability of precipitation (0-1)
    rain_3h = db.Column(db.Float, default=0)
    snow_3h = db.Column(db.Float, default=0)
    
    # Hava durumu
    weather_main = db.Column(db.String(50))
    weather_description = db.Column(db.String(200))
    weather_icon = db.Column(db.String(10))
    
    # Metadata
    fetched_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    source = db.Column(db.String(50), default="openweather")
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "forecast_time": self.forecast_time.isoformat() if self.forecast_time else None,
            "temperature": self.temperature,
            "feels_like": self.feels_like,
            "temp_min": self.temp_min,
            "temp_max": self.temp_max,
            "humidity": self.humidity,
            "pressure": self.pressure,
            "clouds": self.clouds,
            "wind": {
                "speed": self.wind_speed,
                "direction": self.wind_direction,
            },
            "precipitation": {
                "probability": self.pop,
                "rain_3h": self.rain_3h,
                "snow_3h": self.snow_3h,
            },
            "weather": {
                "main": self.weather_main,
                "description": self.weather_description,
                "icon": self.weather_icon,
            },
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }
