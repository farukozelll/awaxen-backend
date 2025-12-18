"""
Awaxen Models - Gateway.

Fiziksel bağlantı merkezi modeli.
"""
from datetime import datetime, timezone
import uuid

from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.extensions import db


def utcnow() -> datetime:
    """Timezone-aware UTC datetime döndür."""
    return datetime.now(timezone.utc)


class Gateway(db.Model):
    """
    Fiziksel Bağlantı Merkezi - Teltonika RUT956, Raspberry Pi.
    
    Sahadaki internet kapısı. Yerel cihazlar buraya bağlanır.
    """
    __tablename__ = "gateways"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id"), nullable=False, index=True)
    
    serial_number = db.Column(db.String(100), unique=True, index=True)
    model = db.Column(db.String(50))
    gateway_type = db.Column(db.String(50))  # teltonika, raspberry_pi, shelly_pro, custom
    
    ip_address = db.Column(db.String(45))
    mac_address = db.Column(db.String(17))
    
    status = db.Column(db.String(20), default="offline", index=True)
    last_seen = db.Column(db.DateTime(timezone=True))
    
    settings = db.Column(JSONB, default=dict)
    is_active = db.Column(db.Boolean, default=True, index=True)
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # İlişkiler
    devices = db.relationship("SmartDevice", backref="gateway", lazy="dynamic")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "serial_number": self.serial_number,
            "model": self.model,
            "gateway_type": self.gateway_type,
            "ip_address": self.ip_address,
            "status": self.status,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "settings": self.settings or {},
            "is_active": self.is_active,
        }
    
    def update_status(self, is_online: bool) -> None:
        """Gateway durumunu güncelle."""
        self.status = "online" if is_online else "offline"
        if is_online:
            self.last_seen = utcnow()
