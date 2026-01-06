"""
Notification Module - Database Models

3 Kanallı Bildirim Sistemi:
1. In-App (Database) - Notification tablosu
2. FCM (Web Push) - UserFCMToken tablosu
3. Telegram - User.telegram_chat_id (auth modülünde)
"""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models import Base


class NotificationType(str, Enum):
    """
    Bildirim türleri - Öncelik ve kanal belirleme için.
    
    CRITICAL: Push + Telegram (Acil durumlar)
    ACTIONABLE: Push with buttons (Eylem gerektiren)
    INFO: Sadece In-App (Düşük öncelik)
    SYSTEM: Push (Sistem bildirimleri)
    WARNING: Push (Uyarılar)
    SUCCESS: In-App (Başarı mesajları)
    """
    CRITICAL = "critical"      # 🚨 Su kaçağı, yangın
    ACTIONABLE = "actionable"  # ⚡ Elektrik pahalı, kapatayım mı?
    INFO = "info"              # 📝 Aylık rapor hazır
    SYSTEM = "system"          # 🔑 Anahtar devredildi
    WARNING = "warning"        # ⚠️ Cihaz çevrimdışı
    SUCCESS = "success"        # ✅ İşlem başarılı


class NotificationPriority(str, Enum):
    """Bildirim önceliği."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class NotificationChannel(str, Enum):
    """Bildirim kanalları."""
    IN_APP = "in_app"
    PUSH = "push"
    TELEGRAM = "telegram"
    EMAIL = "email"


class Notification(Base):
    """
    In-App bildirim modeli.
    
    Tüm bildirimler burada saklanır (geçmiş için).
    Push ve Telegram bildirimleri de burada loglanır.
    """
    __tablename__ = "notification"
    
    __table_args__ = (
        Index("idx_notification_user_read", "user_id", "is_read", "created_at"),
        Index("idx_notification_user_type", "user_id", "type"),
    )
    
    # İlişkiler
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
    
    # Bildirim içeriği
    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=NotificationType.INFO.value,
    )
    
    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=NotificationPriority.MEDIUM.value,
    )
    
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Ek veri (action buttons, deep links, etc.)
    data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Action buttons, deep links, metadata",
    )
    
    # Durum
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Hangi kanallardan gönderildi
    channels_sent: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
        comment="['in_app', 'push', 'telegram']",
    )
    
    # İlgili kaynak (opsiyonel)
    source_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="device, gateway, invoice, etc.",
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )


class UserFCMToken(Base):
    """
    Kullanıcı FCM (Firebase Cloud Messaging) token'ları.
    
    Bir kullanıcının birden fazla cihazı olabilir (web, mobile).
    Her cihaz için ayrı token saklanır.
    """
    __tablename__ = "user_fcm_token"
    
    __table_args__ = (
        Index("idx_fcm_token_user", "user_id"),
    )
    
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # FCM Token
    token: Mapped[str] = mapped_column(
        String(500),
        unique=True,
        nullable=False,
    )
    
    # Cihaz bilgisi
    device_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="web",
        comment="web, android, ios",
    )
    
    device_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Chrome on Windows, Safari on iPhone",
    )
    
    # Token durumu
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Token geçersiz olduğunda
    failed_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
        comment="Consecutive failed sends",
    )


class NotificationPreference(Base):
    """
    Kullanıcı bildirim tercihleri.
    
    Hangi tür bildirimleri hangi kanallardan almak istiyor?
    """
    __tablename__ = "notification_preference"
    
    __table_args__ = (
        Index("idx_notif_pref_user", "user_id"),
    )
    
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    
    # Kanal tercihleri
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Tür bazlı tercihler (JSON)
    type_preferences: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment='{"critical": ["push", "telegram"], "info": ["in_app"]}',
    )
    
    # Sessiz saatler
    quiet_hours_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quiet_hours_start: Mapped[str | None] = mapped_column(
        String(5),
        nullable=True,
        comment="HH:MM format, e.g., 22:00",
    )
    quiet_hours_end: Mapped[str | None] = mapped_column(
        String(5),
        nullable=True,
        comment="HH:MM format, e.g., 08:00",
    )
