"""
Notification Service - 3 Kanallı Bildirim Sistemi

Kanallar:
1. In-App (Database) - Notification tablosu
2. FCM (Web Push) - Firebase Cloud Messaging
3. Telegram - Kritik alarmlar için

Kullanım:
    service = NotificationService(db)
    await service.send_notification(
        user_id=user.id,
        type=NotificationType.CRITICAL,
        title="🚨 Su Kaçağı!",
        message="Banyo sensörü su kaçağı tespit etti.",
        send_telegram=True,
    )
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.core.config import settings
from src.modules.notifications.models import (
    Notification,
    UserFCMToken,
    NotificationPreference,
    NotificationType,
    NotificationPriority,
)
from src.modules.notifications.schemas import (
    NotificationResponse,
    NotificationListResponse,
    NotificationCreateRequest,
    FCMTokenRegisterRequest,
    NotificationPreferenceResponse,
)

logger = get_logger(__name__)


class NotificationService:
    """
    3 Kanallı Bildirim Servisi.
    
    - In-App: Veritabanına kaydet (her zaman)
    - Push: FCM ile gönder (tercihe göre)
    - Telegram: Kritik alarmlar için (tercihe göre)
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self._fcm_app = None
        self._telegram_bot = None
    
    # ============== MAIN SEND METHOD ==============
    
    async def send_notification(
        self,
        user_id: uuid.UUID,
        title: str,
        message: str,
        type: NotificationType = NotificationType.INFO,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        organization_id: uuid.UUID | None = None,
        data: dict | None = None,
        source_type: str | None = None,
        source_id: uuid.UUID | None = None,
        send_push: bool = True,
        send_telegram: bool | None = None,
    ) -> Notification:
        """
        Bildirim gönder - 3 kanal.
        
        Args:
            user_id: Hedef kullanıcı
            title: Bildirim başlığı
            message: Bildirim mesajı
            type: Bildirim türü (CRITICAL, ACTIONABLE, INFO, etc.)
            priority: Öncelik (LOW, MEDIUM, HIGH, URGENT)
            organization_id: Organizasyon (opsiyonel)
            data: Ek veri (action buttons, deep links)
            source_type: Kaynak türü (device, gateway, invoice)
            source_id: Kaynak ID
            send_push: FCM Push gönder mi?
            send_telegram: Telegram gönder mi? (None = otomatik karar)
        
        Returns:
            Notification: Oluşturulan bildirim kaydı
        """
        channels_sent = ["in_app"]
        
        # 1. Veritabanına kaydet (her zaman)
        notification = Notification(
            user_id=user_id,
            organization_id=organization_id,
            type=type.value,
            priority=priority.value,
            title=title,
            message=message,
            data=data,
            source_type=source_type,
            source_id=source_id,
            is_read=False,
        )
        self.db.add(notification)
        await self.db.flush()
        
        # 2. Kullanıcı tercihlerini al
        preferences = await self._get_user_preferences(user_id)
        
        # 3. FCM Push gönder
        if send_push and preferences.push_enabled:
            try:
                success = await self._send_fcm_push(user_id, title, message, data)
                if success:
                    channels_sent.append("push")
            except Exception as e:
                logger.error("FCM push failed", user_id=str(user_id), error=str(e))
        
        # 4. Telegram gönder (CRITICAL veya açıkça istenirse)
        should_send_telegram = send_telegram if send_telegram is not None else (type == NotificationType.CRITICAL)
        
        if should_send_telegram and preferences.telegram_enabled:
            try:
                success = await self._send_telegram(user_id, title, message)
                if success:
                    channels_sent.append("telegram")
            except Exception as e:
                logger.error("Telegram send failed", user_id=str(user_id), error=str(e))
        
        # 5. Kanalları güncelle
        notification.channels_sent = channels_sent
        await self.db.commit()
        await self.db.refresh(notification)
        
        logger.info(
            "Notification sent",
            notification_id=str(notification.id),
            user_id=str(user_id),
            type=type.value,
            channels=channels_sent,
        )
        
        return notification
    
    # ============== IN-APP METHODS ==============
    
    async def get_notifications(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 10,
        unread_only: bool = False,
    ) -> NotificationListResponse:
        """Kullanıcının bildirimlerini getir."""
        
        # Base query
        stmt = select(Notification).where(Notification.user_id == user_id)
        
        if unread_only:
            stmt = stmt.where(Notification.is_read == False)
        
        # Total count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.db.scalar(count_stmt) or 0
        
        # Unread count
        unread_stmt = select(func.count()).where(
            Notification.user_id == user_id,
            Notification.is_read == False,
        )
        unread_count = await self.db.scalar(unread_stmt) or 0
        
        # Paginated results
        stmt = stmt.order_by(Notification.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        
        result = await self.db.execute(stmt)
        notifications = result.scalars().all()
        
        return NotificationListResponse(
            items=[NotificationResponse.model_validate(n) for n in notifications],
            total=total,
            page=page,
            page_size=page_size,
            has_more=(page * page_size) < total,
            unread_count=unread_count,
        )
    
    async def get_unread_count(self, user_id: uuid.UUID) -> int:
        """Okunmamış bildirim sayısını getir."""
        stmt = select(func.count()).where(
            Notification.user_id == user_id,
            Notification.is_read == False,
        )
        return await self.db.scalar(stmt) or 0
    
    async def mark_as_read(
        self,
        user_id: uuid.UUID,
        notification_ids: list[uuid.UUID],
    ) -> int:
        """Bildirimleri okundu olarak işaretle."""
        stmt = (
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.id.in_(notification_ids),
                Notification.is_read == False,
            )
            .values(
                is_read=True,
                read_at=datetime.now(timezone.utc),
            )
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount
    
    async def mark_all_as_read(self, user_id: uuid.UUID) -> int:
        """Tüm bildirimleri okundu olarak işaretle."""
        stmt = (
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read == False,
            )
            .values(
                is_read=True,
                read_at=datetime.now(timezone.utc),
            )
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount
    
    # ============== FCM TOKEN METHODS ==============
    
    async def register_fcm_token(
        self,
        user_id: uuid.UUID,
        request: FCMTokenRegisterRequest,
    ) -> UserFCMToken:
        """FCM token kaydet veya güncelle."""
        
        # Mevcut token var mı kontrol et
        stmt = select(UserFCMToken).where(UserFCMToken.token == request.fcm_token)
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            # Token başka kullanıcıya aitse, güncelle
            existing.user_id = user_id
            existing.device_type = request.device_type
            existing.device_name = request.device_name
            existing.is_active = True
            existing.failed_count = 0
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        
        # Yeni token oluştur
        token = UserFCMToken(
            user_id=user_id,
            token=request.fcm_token,
            device_type=request.device_type,
            device_name=request.device_name,
            is_active=True,
        )
        self.db.add(token)
        await self.db.commit()
        await self.db.refresh(token)
        
        logger.info("FCM token registered", user_id=str(user_id), device_type=request.device_type)
        return token
    
    async def get_user_fcm_tokens(self, user_id: uuid.UUID) -> list[str]:
        """Kullanıcının aktif FCM token'larını getir."""
        stmt = select(UserFCMToken.token).where(
            UserFCMToken.user_id == user_id,
            UserFCMToken.is_active == True,
        )
        result = await self.db.execute(stmt)
        return [row[0] for row in result.fetchall()]
    
    async def deactivate_fcm_token(self, token: str) -> None:
        """FCM token'ı deaktif et (geçersiz olduğunda)."""
        stmt = (
            update(UserFCMToken)
            .where(UserFCMToken.token == token)
            .values(is_active=False)
        )
        await self.db.execute(stmt)
        await self.db.commit()
    
    # ============== PREFERENCES METHODS ==============
    
    async def _get_user_preferences(self, user_id: uuid.UUID) -> NotificationPreference:
        """Kullanıcı tercihlerini getir veya varsayılan oluştur."""
        stmt = select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        result = await self.db.execute(stmt)
        prefs = result.scalar_one_or_none()
        
        if not prefs:
            # Varsayılan tercihler oluştur
            prefs = NotificationPreference(
                user_id=user_id,
                push_enabled=True,
                telegram_enabled=True,
                email_enabled=False,
            )
            self.db.add(prefs)
            await self.db.flush()
        
        return prefs
    
    async def get_preferences(self, user_id: uuid.UUID) -> NotificationPreferenceResponse:
        """Kullanıcı bildirim tercihlerini getir."""
        prefs = await self._get_user_preferences(user_id)
        return NotificationPreferenceResponse.model_validate(prefs)
    
    async def update_preferences(
        self,
        user_id: uuid.UUID,
        updates: dict,
    ) -> NotificationPreferenceResponse:
        """Kullanıcı bildirim tercihlerini güncelle."""
        prefs = await self._get_user_preferences(user_id)
        
        for key, value in updates.items():
            if value is not None and hasattr(prefs, key):
                setattr(prefs, key, value)
        
        await self.db.commit()
        await self.db.refresh(prefs)
        
        return NotificationPreferenceResponse.model_validate(prefs)
    
    # ============== FCM PUSH (Firebase) ==============
    
    async def _send_fcm_push(
        self,
        user_id: uuid.UUID,
        title: str,
        body: str,
        data: dict | None = None,
    ) -> bool:
        """
        FCM Push bildirimi gönder.
        
        Firebase Admin SDK kullanır.
        """
        tokens = await self.get_user_fcm_tokens(user_id)
        
        if not tokens:
            logger.debug("No FCM tokens for user", user_id=str(user_id))
            return False
        
        try:
            # Firebase Admin SDK import
            import firebase_admin
            from firebase_admin import messaging
            
            # Firebase app başlat (henüz başlatılmadıysa)
            if not self._fcm_app:
                try:
                    self._fcm_app = firebase_admin.get_app()
                except ValueError:
                    # App henüz başlatılmamış, config'den başlat
                    if hasattr(settings, 'firebase_credentials_path') and settings.firebase_credentials_path:
                        from firebase_admin import credentials
                        cred = credentials.Certificate(settings.firebase_credentials_path)
                        self._fcm_app = firebase_admin.initialize_app(cred)
                    else:
                        logger.warning("Firebase credentials not configured")
                        return False
            
            # Multicast mesaj oluştur
            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=data or {},
                tokens=tokens,
            )
            
            # Gönder
            response = messaging.send_multicast(message)
            
            logger.info(
                "FCM push sent",
                user_id=str(user_id),
                success_count=response.success_count,
                failure_count=response.failure_count,
            )
            
            # Başarısız token'ları deaktif et
            if response.failure_count > 0:
                for idx, resp in enumerate(response.responses):
                    if not resp.success:
                        await self.deactivate_fcm_token(tokens[idx])
            
            return response.success_count > 0
            
        except ImportError:
            logger.warning("firebase-admin not installed, skipping FCM push")
            return False
        except Exception as e:
            logger.error("FCM push error", error=str(e))
            return False
    
    # ============== TELEGRAM ==============
    
    async def _send_telegram(
        self,
        user_id: uuid.UUID,
        title: str,
        message: str,
    ) -> bool:
        """
        Telegram bildirimi gönder.
        
        Kullanıcının telegram_chat_id'si olmalı.
        """
        try:
            # Kullanıcının Telegram chat ID'sini al
            from src.modules.auth.models import User
            
            stmt = select(User.telegram_chat_id).where(User.id == user_id)
            result = await self.db.execute(stmt)
            chat_id = result.scalar_one_or_none()
            
            if not chat_id:
                logger.debug("No Telegram chat_id for user", user_id=str(user_id))
                return False
            
            # Telegram bot token
            bot_token = getattr(settings, 'telegram_bot_token', None)
            if not bot_token:
                logger.warning("Telegram bot token not configured")
                return False
            
            # python-telegram-bot veya httpx ile gönder
            import httpx
            
            text = f"🔔 *{title}*\n\n{message}"
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "Markdown",
                    },
                )
                
                if response.status_code == 200:
                    logger.info("Telegram message sent", user_id=str(user_id), chat_id=chat_id)
                    return True
                else:
                    logger.error("Telegram send failed", status=response.status_code, response=response.text)
                    return False
                    
        except Exception as e:
            logger.error("Telegram error", error=str(e))
            return False
    
    async def get_telegram_link(self, user_id: uuid.UUID) -> dict:
        """
        Telegram bağlantı linki oluştur.
        
        Deep link: https://t.me/AwaxenBot?start=USER_ID
        """
        from src.modules.auth.models import User
        
        # Kullanıcı bilgilerini al
        stmt = select(User.telegram_chat_id, User.telegram_username).where(User.id == user_id)
        result = await self.db.execute(stmt)
        row = result.first()
        
        bot_username = getattr(settings, 'telegram_bot_username', 'AwaxenBot')
        
        return {
            "link": f"https://t.me/{bot_username}?start={user_id}",
            "bot_username": bot_username,
            "is_connected": bool(row and row[0]),
            "telegram_username": row[1] if row else None,
        }
