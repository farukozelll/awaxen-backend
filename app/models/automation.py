"""
Awaxen Models - Automation.

Otomasyon kuralları ve VPP modelleri.
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


# Valid trigger types for automation rules
VALID_TRIGGER_TYPES = {'price', 'time_range', 'sensor', 'always', 'schedule'}
VALID_ACTION_TYPES = {'turn_on', 'turn_off', 'toggle', 'set_power', 'notify'}
VALID_OPERATORS = {'<', '>', '<=', '>=', '==', '!='}


class Automation(db.Model):
    """
    Otomasyon Kuralı - Fiyat bazlı, zaman bazlı, sensör bazlı.
    
    Rules JSONB şeması:
    {
        "trigger": {"type": "price|time_range|sensor", ...},
        "conditions": [...],
        "action": {"type": "turn_on|turn_off|toggle|set_power", ...}
    }
    """
    __tablename__ = "automations"
    
    # Composite indexes
    __table_args__ = (
        db.Index('idx_automation_org_active', 'organization_id', 'is_active'),
        db.Index('idx_automation_org_priority', 'organization_id', 'priority'),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id = db.Column(UUID(as_uuid=True), db.ForeignKey("smart_assets.id", ondelete="SET NULL"), index=True)
    created_by = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    
    name = db.Column(db.String(100))
    description = db.Column(db.Text)
    
    is_active = db.Column(db.Boolean, default=True, index=True)
    priority = db.Column(db.Integer, default=100, index=True)
    rules = db.Column(JSONB, nullable=False)
    
    last_triggered_at = db.Column(db.DateTime(timezone=True))
    trigger_count = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # İlişkiler
    logs = db.relationship("AutomationLog", backref="automation", lazy="dynamic")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "asset_id": str(self.asset_id) if self.asset_id else None,
            "created_by": str(self.created_by) if self.created_by else None,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "priority": self.priority,
            "rules": self.rules,
            "last_triggered_at": self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            "trigger_count": self.trigger_count,
        }
    
    def increment_trigger_count(self) -> None:
        """Tetiklenme sayısını artır."""
        self.trigger_count = (self.trigger_count or 0) + 1
        self.last_triggered_at = utcnow()
    
    @validates('rules')
    def validate_rules(self, key: str, value: Any) -> Dict:
        """
        Rules JSONB alanını validate et.
        
        Geçerli şema:
        {
            "trigger": {"type": "price|time_range|sensor|always", ...},
            "conditions": [...],  # opsiyonel
            "action": {"type": "turn_on|turn_off|toggle|set_power", ...}
        }
        """
        if value is None:
            raise ValueError("rules cannot be null")
        
        if not isinstance(value, dict):
            raise ValueError("rules must be a JSON object")
        
        # Trigger kontrolü
        trigger = value.get('trigger')
        if not trigger:
            raise ValueError("rules must contain 'trigger'")
        
        trigger_type = trigger.get('type')
        if trigger_type and trigger_type not in VALID_TRIGGER_TYPES:
            raise ValueError(f"Invalid trigger type: {trigger_type}. Valid: {VALID_TRIGGER_TYPES}")
        
        # Action kontrolü
        action = value.get('action')
        if not action:
            raise ValueError("rules must contain 'action'")
        
        action_type = action.get('type')
        if action_type and action_type not in VALID_ACTION_TYPES:
            raise ValueError(f"Invalid action type: {action_type}. Valid: {VALID_ACTION_TYPES}")
        
        return value


class AutomationLog(db.Model):
    """Otomasyon Çalışma Geçmişi."""
    __tablename__ = "automation_logs"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id"), nullable=False, index=True)
    automation_id = db.Column(UUID(as_uuid=True), db.ForeignKey("automations.id"), nullable=False, index=True)
    
    triggered_at = db.Column(db.DateTime(timezone=True), default=utcnow, index=True)
    action_taken = db.Column(db.String(100))
    reason = db.Column(db.Text)
    
    status = db.Column(db.String(20), default="success", index=True)
    error_message = db.Column(db.Text)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "automation_id": str(self.automation_id),
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "action_taken": self.action_taken,
            "reason": self.reason,
            "status": self.status,
            "error_message": self.error_message,
        }


class VppRule(db.Model):
    """VPP Otomasyon Kuralları - İleri seviye enerji yönetimi."""
    __tablename__ = "vpp_rules"
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id"), nullable=False, index=True)
    device_id = db.Column(UUID(as_uuid=True), db.ForeignKey("smart_devices.id"), index=True)
    
    name = db.Column(db.String(100))
    description = db.Column(db.String(255))
    
    is_active = db.Column(db.Boolean, default=True, index=True)
    trigger = db.Column(JSONB, nullable=False)
    action = db.Column(JSONB, nullable=False)
    priority = db.Column(db.Integer, default=1)
    
    last_triggered_at = db.Column(db.DateTime(timezone=True))
    trigger_count = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "device_id": str(self.device_id) if self.device_id else None,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "trigger": self.trigger,
            "action": self.action,
            "priority": self.priority,
            "last_triggered_at": self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            "trigger_count": self.trigger_count,
        }
