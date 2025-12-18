"""
Awaxen Models - Market.

Piyasa fiyatları modeli.
"""
from datetime import datetime, timezone

from app.extensions import db


class MarketPrice(db.Model):
    """
    EPİAŞ Piyasa Fiyatları - Global tablo.
    
    Worker saatlik günceller, tüm müşteriler kullanır.
    """
    __tablename__ = "market_prices"

    time = db.Column(db.DateTime(timezone=True), primary_key=True)
    price = db.Column(db.Float, nullable=False)  # TL/kWh
    currency = db.Column(db.String(10), default="TRY")
    region = db.Column(db.String(10), default="TR")
    
    ptf = db.Column(db.Float)  # Piyasa Takas Fiyatı (TL/MWh)
    smf = db.Column(db.Float)  # Sistem Marjinal Fiyatı

    def to_dict(self) -> dict:
        return {
            "time": self.time.isoformat() if self.time else None,
            "price": self.price,
            "currency": self.currency,
            "region": self.region,
            "ptf": self.ptf,
            "smf": self.smf,
        }
    
    @classmethod
    def get_latest(cls) -> "MarketPrice":
        """En son fiyatı getir."""
        return cls.query.order_by(cls.time.desc()).first()
    
    @classmethod
    def get_current_price(cls) -> float:
        """Mevcut fiyatı döndür (TL/kWh)."""
        latest = cls.get_latest()
        return latest.price if latest else 0.0
