"""
Awaxen Models - Integration.

Bulut entegrasyon modeli.
"""
from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.extensions import db
from app.utils.encryption import encrypt_token, decrypt_token


def utcnow() -> datetime:
    """Timezone-aware UTC datetime döndür."""
    return datetime.now(timezone.utc)


class Integration(db.Model):
    """
    Bulut Entegrasyonu - Shelly Cloud, Tesla, Tapo, Tuya.
    
    OAuth token'ları şifreli saklanır.
    """
    __tablename__ = "integrations"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id"), nullable=False, index=True)
    
    provider = db.Column(db.String(50), nullable=False, index=True)
    
    # Şifreli Tokenlar
    _access_token = db.Column("access_token", db.Text)
    _refresh_token = db.Column("refresh_token", db.Text)
    
    expires_at = db.Column(db.DateTime(timezone=True))
    provider_data = db.Column(JSONB, default=dict)
    
    status = db.Column(db.String(20), default="active", index=True)
    last_sync_at = db.Column(db.DateTime(timezone=True))
    
    is_active = db.Column(db.Boolean, default=True, index=True)
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # İlişkiler
    devices = db.relationship("SmartDevice", backref="integration", lazy="dynamic")

    # Token encryption properties
    @property
    def access_token(self) -> Optional[str]:
        if self._access_token:
            try:
                return decrypt_token(self._access_token)
            except Exception:
                return None
        return None

    @access_token.setter
    def access_token(self, value: Optional[str]) -> None:
        if value:
            self._access_token = encrypt_token(value)
        else:
            self._access_token = None

    @property
    def refresh_token(self) -> Optional[str]:
        if self._refresh_token:
            try:
                return decrypt_token(self._refresh_token)
            except Exception:
                return None
        return None

    @refresh_token.setter
    def refresh_token(self, value: Optional[str]) -> None:
        if value:
            self._refresh_token = encrypt_token(value)
        else:
            self._refresh_token = None

    def to_dict(self, include_tokens: bool = False) -> dict:
        data = {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "provider": self.provider,
            "status": self.status,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "provider_data": self.provider_data or {},
            "is_active": self.is_active,
        }
        if include_tokens:
            data["access_token"] = self.access_token
            data["refresh_token"] = self.refresh_token
            data["has_access_token"] = bool(self._access_token)
            data["has_refresh_token"] = bool(self._refresh_token)
        return data
    
    def is_token_expired(self) -> bool:
        """Token süresi dolmuş mu?"""
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) > self.expires_at
    
    def update_sync_time(self) -> None:
        """Son senkronizasyon zamanını güncelle."""
        self.last_sync_at = utcnow()
