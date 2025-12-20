"""
Awaxen Models - Organization.

SaaS Tenant modeli.
"""
from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.extensions import db
from app.models.enums import OrganizationType, SubscriptionStatus


def utcnow() -> datetime:
    """Timezone-aware UTC datetime döndür."""
    return datetime.now(timezone.utc)


class Organization(db.Model):
    """
    SaaS Tenant - Ev, Tarım İşletmesi veya Fabrika.
    
    Tüm veriler organization_id ile izole edilir (Multi-tenancy).
    """
    __tablename__ = "organizations"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(100), unique=True, index=True)
    
    type = db.Column(db.String(50), default=OrganizationType.HOME.value, index=True)
    
    timezone = db.Column(db.String(50), default="Europe/Istanbul")
    location = db.Column(JSONB, default=dict)
    
    subscription_status = db.Column(db.String(20), default=SubscriptionStatus.ACTIVE.value, index=True)
    subscription_plan = db.Column(db.String(50), default="free")
    
    settings = db.Column(JSONB, default=dict)
    
    # Electricity pricing for savings calculation (TL/kWh)
    electricity_price_kwh = db.Column(db.Numeric(10, 4), default=2.5)
    currency = db.Column(db.String(10), default="TRY")
    
    is_active = db.Column(db.Boolean, default=True, index=True)
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Composite index for common queries
    __table_args__ = (
        db.Index('idx_org_type_active', 'type', 'is_active'),
        db.Index('idx_org_subscription', 'subscription_status', 'subscription_plan'),
    )

    # İlişkiler - CASCADE DELETE ile orphan record önleme
    users = db.relationship("User", backref="organization", lazy="dynamic", 
                           cascade="all, delete-orphan", passive_deletes=True)
    gateways = db.relationship("Gateway", backref="organization", lazy="dynamic",
                              cascade="all, delete-orphan", passive_deletes=True)
    integrations = db.relationship("Integration", backref="organization", lazy="dynamic",
                                  cascade="all, delete-orphan", passive_deletes=True)
    devices = db.relationship("SmartDevice", backref="organization", lazy="dynamic",
                             cascade="all, delete-orphan", passive_deletes=True)
    assets = db.relationship("SmartAsset", backref="organization", lazy="dynamic",
                            cascade="all, delete-orphan", passive_deletes=True)
    automations = db.relationship("Automation", backref="organization", lazy="dynamic",
                                 cascade="all, delete-orphan", passive_deletes=True)
    audit_logs = db.relationship("AuditLog", backref="organization", lazy="dynamic",
                                cascade="all, delete-orphan", passive_deletes=True)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "slug": self.slug,
            "type": self.type,
            "timezone": self.timezone,
            "location": self.location or {},
            "subscription_status": self.subscription_status,
            "subscription_plan": self.subscription_plan,
            "electricity_price_kwh": float(self.electricity_price_kwh) if self.electricity_price_kwh else 2.5,
            "currency": self.currency,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def get_active_user_count(self) -> int:
        """Aktif kullanıcı sayısını döndür."""
        return self.users.filter_by(is_active=True).count()
    
    def get_active_device_count(self) -> int:
        """Aktif cihaz sayısını döndür."""
        return self.devices.filter_by(is_active=True).count()
