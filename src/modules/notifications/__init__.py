"""
Notifications Module - 3 Kanallı Bildirim Sistemi

Kanallar:
1. In-App (Database) - Çan ikonu
2. FCM (Web Push) - PWA bildirimleri
3. Telegram - Kritik alarmlar
"""
from src.modules.notifications.models import (
    Notification,
    NotificationPreference,
    NotificationPriority,
    NotificationType,
    UserFCMToken,
)
from src.modules.notifications.router import router
from src.modules.notifications.service import NotificationService

__all__ = [
    "Notification",
    "NotificationPreference",
    "NotificationPriority",
    "NotificationService",
    "NotificationType",
    "UserFCMToken",
    "router",
]
