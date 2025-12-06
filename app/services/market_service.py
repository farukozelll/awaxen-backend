"""Enerji piyasası fiyatları (EPİAŞ) iş mantığı - v6.0."""
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from app.extensions import db
from app.models import MarketPrice


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


def get_current_market_price() -> Optional[Dict[str, Any]]:
    """Şu anki saatin piyasa fiyatını getir."""
    now = datetime.utcnow()
    # Bu saatin başlangıcı
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    
    price = MarketPrice.query.filter_by(time=hour_start).first()
    return price.to_dict() if price else None


def get_latest_price() -> Optional[float]:
    """En son fiyatı getir (TL/kWh)."""
    price = MarketPrice.query.order_by(MarketPrice.time.desc()).first()
    return price.price if price else None
