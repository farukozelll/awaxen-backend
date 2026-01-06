"""
Notification Schemas - 3 Kanallı Bildirim Sistemi

Kanallar:
1. In-App (Database) - Çan ikonu
2. FCM (Web Push) - PWA bildirimleri
3. Telegram - Kritik alarmlar
"""
import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict


# ============== Enums ==============

class NotificationType(str, Enum):
    """
    Bildirim türleri.
    
    CRITICAL: Push + Telegram (Acil durumlar)
    ACTIONABLE: Push with buttons (Eylem gerektiren)
    INFO: Sadece In-App (Düşük öncelik)
    SYSTEM: Push (Sistem bildirimleri)
    WARNING: Push (Uyarılar)
    SUCCESS: In-App (Başarı mesajları)
    """
    CRITICAL = "critical"
    ACTIONABLE = "actionable"
    INFO = "info"
    SYSTEM = "system"
    WARNING = "warning"
    SUCCESS = "success"


class NotificationPriority(str, Enum):
    """Bildirim önceliği."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


# ============== Notification Schemas ==============

class NotificationResponse(BaseModel):
    """Bildirim yanıtı."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    type: str = Field(default="info", description="Bildirim türü")
    priority: str = Field(default="medium", description="Öncelik")
    title: str
    message: str
    data: dict | None = Field(default=None, description="Ek veri (action buttons, deep links)")
    is_read: bool = False
    created_at: datetime
    read_at: datetime | None = None
    source_type: str | None = Field(default=None, description="Kaynak türü (device, gateway)")
    source_id: uuid.UUID | None = None


class NotificationListResponse(BaseModel):
    """Bildirim listesi yanıtı."""
    items: list[NotificationResponse] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 10
    has_more: bool = False
    unread_count: int = Field(default=0, description="Okunmamış bildirim sayısı")


class NotificationMarkReadRequest(BaseModel):
    """Bildirim okundu işaretleme isteği."""
    notification_ids: list[uuid.UUID] = Field(default_factory=list)


class NotificationCreateRequest(BaseModel):
    """Bildirim oluşturma isteği (internal use)."""
    user_id: uuid.UUID
    organization_id: uuid.UUID | None = None
    type: NotificationType = NotificationType.INFO
    priority: NotificationPriority = NotificationPriority.MEDIUM
    title: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1)
    data: dict | None = None
    source_type: str | None = None
    source_id: uuid.UUID | None = None
    
    # Hangi kanallardan gönderilsin
    send_push: bool = True
    send_telegram: bool = False  # Sadece CRITICAL için True


# ============== FCM Token Schemas ==============

class FCMTokenRegisterRequest(BaseModel):
    """FCM token kayıt isteği."""
    fcm_token: str = Field(..., min_length=10, description="Firebase Cloud Messaging token")
    device_type: str = Field(default="web", description="web, android, ios")
    device_name: str | None = Field(default=None, description="Chrome on Windows")


class FCMTokenResponse(BaseModel):
    """FCM token yanıtı."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    device_type: str
    device_name: str | None
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None


# ============== Notification Preferences ==============

class NotificationPreferenceResponse(BaseModel):
    """Bildirim tercihleri yanıtı."""
    model_config = ConfigDict(from_attributes=True)
    
    push_enabled: bool = True
    telegram_enabled: bool = True
    email_enabled: bool = False
    type_preferences: dict | None = Field(
        default=None,
        description='{"critical": ["push", "telegram"], "info": ["in_app"]}'
    )
    quiet_hours_enabled: bool = False
    quiet_hours_start: str | None = Field(default=None, description="HH:MM format")
    quiet_hours_end: str | None = Field(default=None, description="HH:MM format")


class NotificationPreferenceUpdateRequest(BaseModel):
    """Bildirim tercihleri güncelleme isteği."""
    push_enabled: bool | None = None
    telegram_enabled: bool | None = None
    email_enabled: bool | None = None
    type_preferences: dict | None = None
    quiet_hours_enabled: bool | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None


# ============== Telegram Integration ==============

class TelegramLinkResponse(BaseModel):
    """Telegram bağlantı linki yanıtı."""
    link: str = Field(..., description="Telegram deep link")
    bot_username: str
    is_connected: bool = False
    telegram_username: str | None = None
