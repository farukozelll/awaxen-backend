"""Enerji piyasası fiyatları (EPİAŞ) iş mantığı - v6.0."""
import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import redis

from app.extensions import db
from app.models import MarketPrice

logger = logging.getLogger(__name__)

# Redis bağlantısı (cache için)
REDIS_URL = os.getenv("REDIS_URL", os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"))
CACHE_TTL_SECONDS = 3600  # 1 saat

# Varsayılan fiyat (EPİAŞ'tan veri alınamazsa kullanılır)
DEFAULT_PRICE_TRY_KWH = 3.50  # TL/kWh


def _get_redis_client() -> Optional[redis.Redis]:
    """Redis client'ı döndür. Bağlantı hatası varsa None döner."""
    try:
        client = redis.from_url(REDIS_URL, decode_responses=True)
        client.ping()
        return client
    except Exception as e:
        logger.warning(f"Redis bağlantısı kurulamadı: {e}")
        return None


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    """Redis'ten cache değeri oku."""
    client = _get_redis_client()
    if not client:
        return None
    try:
        data = client.get(key)
        return json.loads(data) if data else None
    except Exception as e:
        logger.warning(f"Redis cache okuma hatası: {e}")
        return None


def _cache_set(key: str, value: Dict[str, Any], ttl: int = CACHE_TTL_SECONDS) -> bool:
    """Redis'e cache değeri yaz."""
    client = _get_redis_client()
    if not client:
        return False
    try:
        client.setex(key, ttl, json.dumps(value, default=str))
        return True
    except Exception as e:
        logger.warning(f"Redis cache yazma hatası: {e}")
        return False


def save_market_prices(prices: List[Dict[str, Any]]) -> int:
    """
    EPİAŞ'tan çekilen fiyatları kaydet.
    
    Yeni format: time (timestamp), price (TL/kWh), ptf, smf
    """
    saved_count = 0

    for price_data in prices:
        price_time = price_data.get("time")
        
        # String ise datetime'a çevir
        if isinstance(price_time, str):
            price_time = datetime.fromisoformat(price_time.replace("Z", "+00:00"))
        
        # Upsert mantığı (time primary key)
        existing = MarketPrice.query.filter_by(time=price_time).first()

        if existing:
            existing.price = price_data.get("price")
            existing.ptf = price_data.get("ptf")
            existing.smf = price_data.get("smf")
        else:
            new_price = MarketPrice(
                time=price_time,
                price=price_data.get("price"),
                ptf=price_data.get("ptf"),
                smf=price_data.get("smf"),
                currency=price_data.get("currency", "TRY"),
                region=price_data.get("region", "TR"),
            )
            db.session.add(new_price)
            saved_count += 1

    db.session.commit()
    return saved_count


def get_market_prices_for_date(target_date: date) -> List[Dict[str, Any]]:
    """Belirli bir gün için piyasa fiyatlarını getir."""
    start = datetime.combine(target_date, datetime.min.time())
    end = start + timedelta(days=1)
    
    prices = MarketPrice.query.filter(
        MarketPrice.time >= start,
        MarketPrice.time < end
    ).order_by(MarketPrice.time).all()
    
    return [p.to_dict() for p in prices]


def get_current_market_price() -> Dict[str, Any]:
    """
    Şu anki saatin piyasa fiyatını getir.

    Öncelik sırası:
    1. Redis cache (1 saat TTL)
    2. Bu saatin veritabanı kaydı
    3. En son veritabanı kaydı (is_latest=True)
    4. Varsayılan fiyat (DEFAULT_PRICE_TRY_KWH)
    
    Her zaman bir değer döner (fallback mekanizması).
    """
    cache_key = "market:current_price"
    
    # 1. Redis cache'den oku
    cached = _cache_get(cache_key)
    if cached:
        cached["source"] = "cache"
        return cached
    
    now = datetime.utcnow()
    hour_start = now.replace(minute=0, second=0, microsecond=0)

    # 2. Bu saatin fiyatını veritabanından al
    price = MarketPrice.query.filter_by(time=hour_start).first()
    if price:
        data = price.to_dict()
        data["is_latest"] = False
        data["source"] = "database"
        _cache_set(cache_key, data)
        return data

    # 3. En son fiyatı al
    latest_price = MarketPrice.query.order_by(MarketPrice.time.desc()).first()
    if latest_price:
        data = latest_price.to_dict()
        data["is_latest"] = True
        data["source"] = "database_latest"
        _cache_set(cache_key, data, ttl=1800)  # 30 dakika cache
        return data

    # 4. Varsayılan fiyat (fallback)
    logger.warning("Veritabanında fiyat bulunamadı, varsayılan fiyat kullanılıyor")
    return {
        "time": now.isoformat(),
        "price": DEFAULT_PRICE_TRY_KWH,
        "ptf": DEFAULT_PRICE_TRY_KWH * 1000,  # TL/MWh
        "smf": None,
        "currency": "TRY",
        "region": "TR",
        "is_latest": True,
        "is_default": True,
        "source": "fallback",
    }


def get_latest_price() -> Optional[float]:
    """En son fiyatı getir (TL/kWh)."""
    price = MarketPrice.query.order_by(MarketPrice.time.desc()).first()
    return price.price if price else None
