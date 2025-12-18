"""
Awaxen Models - Notification.

Bildirim modeli.
"""
from datetime import datetime, timezone
import uuid

from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.extensions import db
from app.models.enums import NotificationStatus


def utcnow() -> datetime:
    """Timezone-aware UTC datetime döndür."""
    return datetime.now(timezone.utc)


class Notification(db.Model):
    """
    Kullanıcı Bildirimleri - Telegram, Push, Email, In-App.
    """
    __tablename__ = "notifications"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False, index=True)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id"), index=True)
    
    title = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    
    type = db.Column(db.String(30), default="info", index=True)
    channel = db.Column(db.String(20), default="in_app", index=True)
    
    status = db.Column(db.String(20), default=NotificationStatus.PENDING.value, index=True)
    is_read = db.Column(db.Boolean, default=False, index=True)
    
    reference_id = db.Column(db.String(100))
    reference_type = db.Column(db.String(50))
    
    data = db.Column(JSONB, default=dict)
    
    sent_at = db.Column(db.DateTime(timezone=True))
    read_at = db.Column(db.DateTime(timezone=True))
    error_message = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "organization_id": str(self.organization_id) if self.organization_id else None,
            "title": self.title,
            "message": self.message,
            "type": self.type,
            "channel": self.channel,
            "status": self.status,
            "is_read": self.is_read,
            "reference_id": self.reference_id,
            "reference_type": self.reference_type,
            "data": self.data or {},
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def mark_as_read(self) -> None:
        """Bildirimi okundu olarak işaretle."""
        self.is_read = True
        self.read_at = utcnow()
        self.status = NotificationStatus.READ.value
    
    def mark_as_sent(self) -> None:
        """Bildirimi gönderildi olarak işaretle."""
        self.sent_at = utcnow()
        self.status = NotificationStatus.SENT.value
    
    def mark_as_failed(self, error: str) -> None:
        """Bildirimi başarısız olarak işaretle."""
        self.status = NotificationStatus.FAILED.value
        self.error_message = error
