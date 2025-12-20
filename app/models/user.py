"""
Awaxen Models - User.

Kullanıcı ve kullanıcı ayarları modelleri.
"""
from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.extensions import db


def utcnow() -> datetime:
    """Timezone-aware UTC datetime döndür."""
    return datetime.now(timezone.utc)


class User(db.Model):
    """
    Kullanıcı - Auth0 ile entegre.
    
    Her kullanıcı bir Organization'a bağlıdır.
    Rol, roles tablosundan gelir (RBAC).
    """
    __tablename__ = "users"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id"), index=True)
    
    auth0_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    full_name = db.Column(db.String(100))
    phone_number = db.Column(db.String(20))
    
    # Telegram entegrasyonu
    telegram_chat_id = db.Column(db.String(50), unique=True)
    telegram_username = db.Column(db.String(100))
    
    # RBAC - Rol ilişkisi
    role_id = db.Column(UUID(as_uuid=True), db.ForeignKey("roles.id"), index=True)
    role = db.relationship("Role", backref="users", lazy="joined")
    
    is_active = db.Column(db.Boolean, default=True, index=True)
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # İlişkiler
    notifications = db.relationship("Notification", backref="user", lazy="dynamic")
    settings = db.relationship("UserSettings", backref="user", uselist=False, lazy="joined")

    def to_dict(self, include_permissions: bool = False) -> dict:
        data = {
            "id": str(self.id),
            "organization_id": str(self.organization_id) if self.organization_id else None,
            "email": self.email,
            "full_name": self.full_name,
            "phone_number": self.phone_number,
            "telegram_username": self.telegram_username,
            "role": self.role.to_dict(include_permissions) if self.role else None,
            "role_code": self.role.code if self.role else None,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_permissions and self.role:
            data["permissions"] = [p.code for p in self.role.permissions]
        return data
    
    def has_permission(self, permission_code: str) -> bool:
        """Kullanıcının belirtilen yetkisi var mı?"""
        if not self.role:
            return False
        return self.role.has_permission(permission_code)
    
    def has_any_permission(self, *permission_codes: str) -> bool:
        """Kullanıcının belirtilen yetkilerden herhangi biri var mı?"""
        if not self.role:
            return False
        return any(self.role.has_permission(code) for code in permission_codes)
    
    def has_all_permissions(self, *permission_codes: str) -> bool:
        """Kullanıcının belirtilen tüm yetkileri var mı?"""
        if not self.role:
            return False
        return all(self.role.has_permission(code) for code in permission_codes)
    
    def is_admin(self) -> bool:
        """Kullanıcı admin mi?"""
        if not self.role:
            return False
        return self.role.code in ("super_admin", "admin")


class UserSettings(db.Model):
    """
    Kullanıcı Ayarları - Bildirim tercihleri, UI ayarları vb.
    """
    __tablename__ = "user_settings"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), unique=True, nullable=False)
    
    # Bildirim Kanalları
    telegram_enabled = db.Column(db.Boolean, default=False)
    email_enabled = db.Column(db.Boolean, default=True)
    push_enabled = db.Column(db.Boolean, default=False)
    
    # Bildirim Türleri
    price_alerts = db.Column(db.Boolean, default=True)
    device_alerts = db.Column(db.Boolean, default=True)
    automation_alerts = db.Column(db.Boolean, default=True)
    security_alerts = db.Column(db.Boolean, default=True)
    weekly_report = db.Column(db.Boolean, default=True)
    
    # UI Tercihleri
    language = db.Column(db.String(10), default="tr")
    theme = db.Column(db.String(20), default="system")
    primary_color = db.Column(db.String(20), default="#3B82F6")  # Tailwind blue-500
    secondary_color = db.Column(db.String(20), default="#10B981")  # Tailwind emerald-500
    dashboard_layout = db.Column(JSONB, default=dict)
    
    # Fiyat Uyarı Eşikleri
    price_alert_threshold_low = db.Column(db.Numeric(10, 2))
    price_alert_threshold_high = db.Column(db.Numeric(10, 2))
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "telegram_enabled": self.telegram_enabled,
            "email_enabled": self.email_enabled,
            "push_enabled": self.push_enabled,
            "price_alerts": self.price_alerts,
            "device_alerts": self.device_alerts,
            "automation_alerts": self.automation_alerts,
            "security_alerts": self.security_alerts,
            "weekly_report": self.weekly_report,
            "language": self.language,
            "theme": self.theme,
            "primary_color": self.primary_color,
            "secondary_color": self.secondary_color,
            "price_alert_threshold_low": float(self.price_alert_threshold_low) if self.price_alert_threshold_low else None,
            "price_alert_threshold_high": float(self.price_alert_threshold_high) if self.price_alert_threshold_high else None,
        }
    
    @classmethod
    def get_or_create(cls, user_id: uuid.UUID) -> "UserSettings":
        """Kullanıcı ayarlarını getir veya varsayılan oluştur."""
        settings = cls.query.filter_by(user_id=user_id).first()
        if not settings:
            settings = cls(user_id=user_id)
            db.session.add(settings)
            db.session.commit()
        return settings


class UserInvite(db.Model):
    """Organization user invitations."""
    __tablename__ = "user_invites"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id"), nullable=False, index=True)
    invited_by = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"))

    email = db.Column(db.String(255), nullable=False, index=True)
    role_code = db.Column(db.String(50), nullable=False, default="viewer")

    token = db.Column(db.String(128), unique=True, nullable=False, index=True)
    status = db.Column(db.String(20), default="pending", index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "invited_by": str(self.invited_by) if self.invited_by else None,
            "email": self.email,
            "role_code": self.role_code,
            "status": self.status,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "token": self.token,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def is_expired(self) -> bool:
        """Davet süresi dolmuş mu?"""
        if not self.expires_at:
            return True
        return datetime.now(timezone.utc) > self.expires_at
    
    def is_valid(self) -> bool:
        """Davet geçerli mi?"""
        return self.status == "pending" and not self.is_expired()
