"""
Awaxen Models - Audit.

Denetim kaydı modeli.
"""
from datetime import datetime, timezone
import uuid

from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.extensions import db


def utcnow() -> datetime:
    """Timezone-aware UTC datetime döndür."""
    return datetime.now(timezone.utc)


class AuditLog(db.Model):
    """
    Denetim Kaydı - Kullanıcı işlemlerinin geçmişi.
    """
    __tablename__ = "audit_logs"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False, index=True)
    
    action = db.Column(db.String(100), nullable=False, index=True)
    resource_type = db.Column(db.String(50), index=True)
    resource_id = db.Column(db.String(100))
    
    details = db.Column(JSONB, default=dict)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, index=True)

    # İlişkiler
    user = db.relationship("User", backref="audit_logs", lazy="joined")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "user_id": str(self.user_id),
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "details": self.details or {},
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    @classmethod
    def log_action(
        cls,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        action: str,
        resource_type: str = None,
        resource_id: str = None,
        details: dict = None,
        ip_address: str = None,
        user_agent: str = None
    ) -> "AuditLog":
        """Yeni audit log kaydı oluştur."""
        log = cls(
            organization_id=organization_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.session.add(log)
        return log
