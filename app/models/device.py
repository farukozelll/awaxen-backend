"""
Awaxen Models - Device.

Akıllı cihaz ve varlık modelleri.
"""
from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.extensions import db


def utcnow() -> datetime:
    """Timezone-aware UTC datetime döndür."""
    return datetime.now(timezone.utc)


class SmartDevice(db.Model):
    """
    Akıllı Cihaz - Shelly Plug, Tapo P110, Sensör.
    
    Fiziksel donanım. Gateway veya Integration üzerinden bağlanır.
    """
    __tablename__ = "smart_devices"
    
    # Composite indexes for common query patterns
    __table_args__ = (
        db.Index('idx_device_org_active', 'organization_id', 'is_active'),
        db.Index('idx_device_org_brand', 'organization_id', 'brand'),
        db.Index('idx_device_org_online', 'organization_id', 'is_online'),
        db.Index('idx_device_external', 'organization_id', 'external_id'),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Bağlantı kaynağı (biri dolu olmalı)
    gateway_id = db.Column(UUID(as_uuid=True), db.ForeignKey("gateways.id"), index=True)
    integration_id = db.Column(UUID(as_uuid=True), db.ForeignKey("integrations.id"), index=True)
    
    external_id = db.Column(db.String(100), index=True)  # MAC veya Cloud ID
    name = db.Column(db.String(100))
    
    brand = db.Column(db.String(50), index=True)  # shelly, tapo, tuya
    model = db.Column(db.String(50))
    device_type = db.Column(db.String(50), index=True)  # relay, energy_meter, sensor, switch, plug, dimmer
    
    is_sensor = db.Column(db.Boolean, default=False)
    is_actuator = db.Column(db.Boolean, default=False)
    
    is_online = db.Column(db.Boolean, default=False, index=True)
    last_seen = db.Column(db.DateTime(timezone=True))
    
    settings = db.Column(JSONB, default=dict)
    is_active = db.Column(db.Boolean, default=True, index=True)
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # İlişkiler
    asset = db.relationship("SmartAsset", backref="device", uselist=False, lazy="joined")
    telemetry_data = db.relationship("DeviceTelemetry", backref="device", lazy="dynamic")
    vpp_rules = db.relationship("VppRule", backref="device", lazy="dynamic")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "gateway_id": str(self.gateway_id) if self.gateway_id else None,
            "integration_id": str(self.integration_id) if self.integration_id else None,
            "external_id": self.external_id,
            "name": self.name,
            "brand": self.brand,
            "model": self.model,
            "device_type": self.device_type,
            "is_sensor": self.is_sensor,
            "is_actuator": self.is_actuator,
            "is_online": self.is_online,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "settings": self.settings or {},
            "is_active": self.is_active,
        }
    
    def update_online_status(self, is_online: bool) -> None:
        """Cihaz online durumunu güncelle."""
        self.is_online = is_online
        if is_online:
            self.last_seen = utcnow()


class SmartAsset(db.Model):
    """
    Sanal Varlık - Klima, Isıtıcı, EV Charger.
    
    Kullanıcının gördüğü şey. Cihaz sadece araçtır.
    """
    __tablename__ = "smart_assets"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id"), nullable=False, index=True)
    device_id = db.Column(UUID(as_uuid=True), db.ForeignKey("smart_devices.id"), unique=True, index=True)
    
    name = db.Column(db.String(100))
    type = db.Column(db.String(50), index=True)  # hvac, ev_charger, heater
    
    # Sanal ölçüm için varsayılan güç (Watt)
    nominal_power_watt = db.Column(db.Integer, default=0)
    priority = db.Column(db.Integer, default=1)
    
    settings = db.Column(JSONB, default=dict)
    is_active = db.Column(db.Boolean, default=True, index=True)
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # İlişkiler
    automations = db.relationship("Automation", backref="asset", lazy="dynamic")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "device_id": str(self.device_id) if self.device_id else None,
            "name": self.name,
            "type": self.type,
            "nominal_power_watt": self.nominal_power_watt,
            "priority": self.priority,
            "settings": self.settings or {},
            "is_active": self.is_active,
            "device": self.device.to_dict() if self.device else None,
        }


class DeviceTelemetry(db.Model):
    """
    Cihaz Telemetri Verisi - TimescaleDB Hypertable.
    
    TimescaleDB hypertable olarak yapılandırılır.
    Otomatik veri sıkıştırma ve retention policy uygulanabilir.
    """
    __tablename__ = "device_telemetry"
    
    # Composite index for time-series queries
    __table_args__ = (
        db.Index('idx_telemetry_device_time', 'device_id', 'time'),
        db.Index('idx_telemetry_device_key', 'device_id', 'key'),
    )

    time = db.Column(db.DateTime(timezone=True), primary_key=True, nullable=False)
    device_id = db.Column(UUID(as_uuid=True), db.ForeignKey("smart_devices.id", ondelete="CASCADE"), primary_key=True, index=True)
    key = db.Column(db.String(50), primary_key=True, index=True)
    
    value = db.Column(db.Float)
    quality = db.Column(db.Integer, default=1)

    def to_dict(self) -> dict:
        return {
            "time": self.time.isoformat() if self.time else None,
            "device_id": str(self.device_id),
            "key": self.key,
            "value": self.value,
            "quality": self.quality,
        }


# TimescaleDB Hypertable - Migration'da manuel çalıştırılmalı
# 
# Production'da aşağıdaki SQL'leri migration olarak çalıştırın:
#
# -- Hypertable oluştur
# SELECT create_hypertable('device_telemetry', 'time', if_not_exists => TRUE);
#
# -- Compression policy (7 günden eski veriler sıkıştırılsın)
# ALTER TABLE device_telemetry SET (
#     timescaledb.compress,
#     timescaledb.compress_segmentby = 'device_id'
# );
# SELECT add_compression_policy('device_telemetry', INTERVAL '7 days');
#
# -- Retention policy (90 günden eski veriler silinsin)
# SELECT add_retention_policy('device_telemetry', INTERVAL '90 days');
