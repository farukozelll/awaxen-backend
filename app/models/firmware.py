"""
Awaxen Models - Firmware & OTA Updates.

Gateway ve ESP32 cihazlar için uzaktan firmware güncelleme.
"""
from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.extensions import db
from app.models.base import TimestampMixin


def utcnow() -> datetime:
    """Timezone-aware UTC datetime döndür."""
    return datetime.now(timezone.utc)


class Firmware(db.Model):
    """
    Firmware versiyonu.
    
    Yüklenen .bin dosyaları ve metadata.
    """
    __tablename__ = "firmwares"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Versiyon bilgileri
    version = db.Column(db.String(50), nullable=False)  # 1.0.0, 1.2.3-beta
    version_code = db.Column(db.Integer, nullable=False)  # 100, 123 (karşılaştırma için)
    
    # Hedef cihaz tipi
    device_type = db.Column(db.String(50), nullable=False, index=True)  # gateway, esp32, shelly, etc.
    hardware_version = db.Column(db.String(50))  # v1, v2, esp32-wroom-32
    
    # Dosya bilgileri
    file_name = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer)  # bytes
    file_hash = db.Column(db.String(64))  # SHA256 hash
    file_url = db.Column(db.String(500), nullable=False)  # S3/MinIO URL
    
    # Metadata
    release_notes = db.Column(db.Text)
    changelog = db.Column(JSONB, default=list)  # [{"type": "fix", "description": "..."}]
    
    # Durum
    is_stable = db.Column(db.Boolean, default=False)  # Stable release mi?
    is_mandatory = db.Column(db.Boolean, default=False)  # Zorunlu güncelleme mi?
    is_active = db.Column(db.Boolean, default=True)
    
    # Rollout
    rollout_percentage = db.Column(db.Integer, default=100)  # Kademeli yayın için
    min_version_code = db.Column(db.Integer)  # Bu versiyondan yüksek olanlar güncelleyebilir
    
    # Yükleyen
    uploaded_by = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="SET NULL"))
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # İlişkiler
    uploader = db.relationship("User", backref="uploaded_firmwares")

    __table_args__ = (
        db.UniqueConstraint('device_type', 'version', name='uq_firmware_device_version'),
        db.Index('idx_firmware_device_active', 'device_type', 'is_active'),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "version": self.version,
            "version_code": self.version_code,
            "device_type": self.device_type,
            "hardware_version": self.hardware_version,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "file_hash": self.file_hash,
            "file_url": self.file_url,
            "release_notes": self.release_notes,
            "changelog": self.changelog or [],
            "is_stable": self.is_stable,
            "is_mandatory": self.is_mandatory,
            "is_active": self.is_active,
            "rollout_percentage": self.rollout_percentage,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class FirmwareUpdate(db.Model):
    """
    Firmware güncelleme kaydı.
    
    Hangi cihaza hangi firmware'in ne zaman yüklendiği.
    """
    __tablename__ = "firmware_updates"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Hedef
    device_id = db.Column(UUID(as_uuid=True), db.ForeignKey("smart_devices.id", ondelete="CASCADE"), index=True)
    gateway_id = db.Column(UUID(as_uuid=True), db.ForeignKey("gateways.id", ondelete="CASCADE"), index=True)
    
    firmware_id = db.Column(UUID(as_uuid=True), db.ForeignKey("firmwares.id", ondelete="SET NULL"), nullable=False)
    
    # Versiyon bilgileri
    from_version = db.Column(db.String(50))  # Önceki versiyon
    to_version = db.Column(db.String(50), nullable=False)  # Hedef versiyon
    
    # Durum
    status = db.Column(db.String(20), default="pending", index=True)
    # pending, downloading, installing, completed, failed, cancelled
    
    progress = db.Column(db.Integer, default=0)  # 0-100
    error_message = db.Column(db.Text)
    
    # Zamanlar
    scheduled_at = db.Column(db.DateTime(timezone=True))  # Zamanlanmış güncelleme
    started_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))
    
    # Tetikleyen
    triggered_by = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="SET NULL"))
    trigger_type = db.Column(db.String(20), default="manual")  # manual, auto, scheduled
    
    # Metadata
    extra_data = db.Column(JSONB, default=dict)  # Ek bilgiler
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # İlişkiler
    device = db.relationship("SmartDevice", backref=db.backref("firmware_updates", lazy="dynamic"))
    gateway = db.relationship("Gateway", backref=db.backref("firmware_updates", lazy="dynamic"))
    firmware = db.relationship("Firmware", backref="updates")
    triggered_by_user = db.relationship("User", backref="triggered_firmware_updates")

    __table_args__ = (
        db.Index('idx_fw_update_device_status', 'device_id', 'status'),
        db.Index('idx_fw_update_gateway_status', 'gateway_id', 'status'),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "device_id": str(self.device_id) if self.device_id else None,
            "gateway_id": str(self.gateway_id) if self.gateway_id else None,
            "firmware": self.firmware.to_dict() if self.firmware else None,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "status": self.status,
            "progress": self.progress,
            "error_message": self.error_message,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "trigger_type": self.trigger_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
