"""
Awaxen Models - Energy Savings.

Enerji tasarruf hesaplama ve takip modelleri.
"""
from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.extensions import db


def utcnow() -> datetime:
    """Timezone-aware UTC datetime döndür."""
    return datetime.now(timezone.utc)


class EnergySavings(db.Model):
    """
    Enerji Tasarruf Kaydı - Otomasyon kaynaklı tasarrufları takip eder.
    
    Tasarruf Hesaplama Mantığı:
    - Otomasyon cihazı kapattığında veya dimmer'ı düşürdüğünde
    - Kapalı kalma süresi * Cihaz gücü (kW) = Tasarruf (kWh)
    - Tasarruf (kWh) * Elektrik fiyatı = Para tasarrufu
    """
    __tablename__ = "energy_savings"
    
    __table_args__ = (
        db.Index('idx_savings_org_date', 'organization_id', 'date'),
        db.Index('idx_savings_org_device', 'organization_id', 'device_id'),
        db.Index('idx_savings_date', 'date'),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = db.Column(UUID(as_uuid=True), db.ForeignKey("smart_devices.id", ondelete="SET NULL"), index=True)
    automation_id = db.Column(UUID(as_uuid=True), db.ForeignKey("automations.id", ondelete="SET NULL"), index=True)
    
    # Tarih (günlük aggregation için)
    date = db.Column(db.Date, nullable=False, index=True)
    
    # Tasarruf metrikleri
    off_duration_minutes = db.Column(db.Integer, default=0)  # Kapalı kalma süresi (dakika)
    power_rating_watt = db.Column(db.Integer, default=0)  # Cihaz gücü (Watt)
    energy_saved_kwh = db.Column(db.Numeric(10, 4), default=0)  # Tasarruf edilen enerji (kWh)
    money_saved = db.Column(db.Numeric(10, 2), default=0)  # Para tasarrufu
    currency = db.Column(db.String(10), default="TRY")
    
    # Tasarruf kaynağı
    source_type = db.Column(db.String(50), default="automation")  # automation, schedule, manual, vpp
    
    # Detay bilgisi
    details = db.Column(JSONB, default=dict)
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "device_id": str(self.device_id) if self.device_id else None,
            "automation_id": str(self.automation_id) if self.automation_id else None,
            "date": self.date.isoformat() if self.date else None,
            "off_duration_minutes": self.off_duration_minutes,
            "power_rating_watt": self.power_rating_watt,
            "energy_saved_kwh": float(self.energy_saved_kwh) if self.energy_saved_kwh else 0,
            "money_saved": float(self.money_saved) if self.money_saved else 0,
            "currency": self.currency,
            "source_type": self.source_type,
            "details": self.details or {},
        }
    
    @classmethod
    def calculate_savings(cls, power_watt: int, duration_minutes: int, price_per_kwh: float) -> dict:
        """
        Tasarruf hesapla.
        
        Args:
            power_watt: Cihaz gücü (Watt)
            duration_minutes: Kapalı kalma süresi (dakika)
            price_per_kwh: Elektrik birim fiyatı (TL/kWh)
        
        Returns:
            dict: {energy_saved_kwh, money_saved}
        """
        # Watt -> kW, dakika -> saat
        power_kw = power_watt / 1000
        duration_hours = duration_minutes / 60
        
        # Tasarruf = Güç (kW) * Süre (saat)
        energy_saved_kwh = power_kw * duration_hours
        money_saved = energy_saved_kwh * price_per_kwh
        
        return {
            "energy_saved_kwh": round(energy_saved_kwh, 4),
            "money_saved": round(money_saved, 2)
        }


class DeviceStateLog(db.Model):
    """
    Cihaz Durum Logu - Açık/Kapalı durumlarını takip eder.
    
    Tasarruf hesaplaması için cihazın ne zaman açılıp kapandığını bilmemiz gerekir.
    """
    __tablename__ = "device_state_logs"
    
    __table_args__ = (
        db.Index('idx_state_device_time', 'device_id', 'timestamp'),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = db.Column(UUID(as_uuid=True), db.ForeignKey("smart_devices.id", ondelete="CASCADE"), nullable=False, index=True)
    
    timestamp = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    state = db.Column(db.String(20), nullable=False)  # on, off, dimmed
    power_level = db.Column(db.Integer, default=100)  # 0-100 (dimmer için)
    
    # Durum değişikliği kaynağı
    triggered_by = db.Column(db.String(50))  # automation, manual, schedule, vpp
    automation_id = db.Column(UUID(as_uuid=True), db.ForeignKey("automations.id", ondelete="SET NULL"))
    
    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "device_id": str(self.device_id),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "state": self.state,
            "power_level": self.power_level,
            "triggered_by": self.triggered_by,
            "automation_id": str(self.automation_id) if self.automation_id else None,
        }
