"""Enerji piyasası fiyatları (EPİAŞ) iş mantığı."""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from .. import db
from ..models import EnergyMarketPrice


def save_market_prices(prices: List[Dict[str, Any]]) -> int:
    """EPİAŞ'tan çekilen fiyatları kaydet."""
    saved_count = 0

    for price_data in prices:
        price_date = price_data.get("date")
        hour = price_data.get("hour")

        if isinstance(price_date, str):
            price_date = datetime.strptime(price_date, "%Y-%m-%d").date()

        # Upsert mantığı
        existing = EnergyMarketPrice.query.filter_by(date=price_date, hour=hour).first()

        if existing:
            existing.ptf = price_data.get("ptf")
            existing.smf = price_data.get("smf")
            existing.positive_imbalance = price_data.get("positive_imbalance")
            existing.negative_imbalance = price_data.get("negative_imbalance")
        else:
            new_price = EnergyMarketPrice(
                date=price_date,
                hour=hour,
                ptf=price_data.get("ptf"),
                smf=price_data.get("smf"),
                positive_imbalance=price_data.get("positive_imbalance"),
                negative_imbalance=price_data.get("negative_imbalance"),
            )
            db.session.add(new_price)
            saved_count += 1

    db.session.commit()
    return saved_count


def get_market_prices_for_date(target_date: date) -> List[Dict[str, Any]]:
    """Belirli bir gün için piyasa fiyatlarını getir."""
    prices = EnergyMarketPrice.query.filter_by(date=target_date).order_by(EnergyMarketPrice.hour).all()
    return [p.to_dict() for p in prices]


def get_current_market_price() -> Optional[Dict[str, Any]]:
    """Şu anki saatin piyasa fiyatını getir."""
    now = datetime.now()
    price = EnergyMarketPrice.query.filter_by(date=now.date(), hour=now.hour).first()
    return price.to_dict() if price else None
