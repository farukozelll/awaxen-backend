"""
Compliance Module - Database Models
Consent (KVKK/GDPR) and Audit Logs for compliance tracking.
"""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.models import Base


class ConsentType(str, Enum):
    """Consent types for KVKK/GDPR compliance."""
    LOCATION = "location"
    DEVICE_CONTROL = "device_control"
    NOTIFICATIONS = "notifications"
    TELEGRAM = "telegram"
    DATA_PROCESSING = "data_processing"
    MARKETING = "marketing"
    ANALYTICS = "analytics"


class Consent(Base):
    """
    KVKK/GDPR Consent tracking.
    
    Records user consent for various data processing activities.
    Each consent type is versioned and timestamped.
    """
    __tablename__ = "consent"
    
    __table_args__ = (
        Index("idx_consent_user", "user_id"),
        Index("idx_consent_user_type", "user_id", "consent_type"),
        Index("idx_consent_org", "organization_id"),
    )
    
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    
    consent_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Consent version (e.g., v1.0, 2026-01)",
    )
    
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=dict,
        comment="IP address, user agent, etc.",
    )
    
    @property
    def is_active(self) -> bool:
        """Check if consent is currently active."""
        return self.accepted_at is not None and self.revoked_at is None


class AuditLog(Base):
    """
    Audit log for compliance and security tracking.
    
    Records all significant actions in the system.
    """
    __tablename__ = "audit_log"
    
    __table_args__ = (
        Index("idx_audit_org_time", "organization_id", "created_at"),
        Index("idx_audit_actor", "actor_user_id"),
        Index("idx_audit_entity", "entity_type", "entity_id"),
        Index("idx_audit_action", "action"),
    )
    
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="e.g., command.dispatch, handover.wipe, device.create",
    )
    
    entity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="asset, gateway, device, command, etc.",
    )
    
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    
    payload_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 hash of payload for integrity",
    )
    
    payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
    )
    
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
    )
    
    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
