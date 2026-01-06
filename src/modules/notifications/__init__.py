"""
Notifications Module - 3 Kanallı Bildirim Sistemi

Kanallar:
1. In-App (Database) - Çan ikonu
2. FCM (Web Push) - PWA bildirimleri
3. Telegram - Kritik alarmlar
"""
from src.modules.notifications.router import router
from src.modules.notifications.service import NotificationService
from src.modules.notifications.models import (
    Notification,
    UserFCMToken,
    NotificationPreference,
    NotificationType,
    NotificationPriority,
)

__all__ = [
    "router",
    "NotificationService",
    "Notification",
    "UserFCMToken",
    "NotificationPreference",
    "NotificationType",
    "NotificationPriority",
]
