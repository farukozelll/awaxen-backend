"""
Notifications Module - API Router

3 Kanallı Bildirim Sistemi:
1. In-App (Database) - Çan ikonu
2. FCM (Web Push) - PWA bildirimleri  
3. Telegram - Kritik alarmlar

Endpoint'ler:
- GET  /api/v1/notifications - Bildirim listesi
- PATCH /api/v1/notifications/read - Bildirimleri okundu işaretle
- PATCH /api/v1/notifications/read-all - Tümünü okundu işaretle
- GET  /api/v1/notifications/unread-count - Okunmamış sayısı
- POST /api/v1/notifications/fcm-token - FCM token kaydet
- GET  /api/v1/notifications/preferences - Bildirim tercihleri
- PATCH /api/v1/notifications/preferences - Tercihleri güncelle
- GET  /api/v1/notifications/telegram/link - Telegram bağlantı linki
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.auth.dependencies import CurrentUser
from src.modules.notifications.schemas import (
    FCMTokenRegisterRequest,
    FCMTokenResponse,
    NotificationListResponse,
    NotificationMarkReadRequest,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdateRequest,
    TelegramLinkResponse,
)
from src.modules.notifications.service import NotificationService

router = APIRouter(prefix="/notifications", tags=["51. 🔔 Notifications"])


# ============== Dependencies ==============

async def get_notification_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationService:
    """Notification service dependency."""
    return NotificationService(db)


NotificationServiceDep = Annotated[NotificationService, Depends(get_notification_service)]


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="Bildirim Listesi",
    description="""
Kullanıcının bildirimlerini sayfalanmış olarak listeler.

## 📋 Parametreler

| Parametre | Tip | Default | Açıklama |
|-----------|-----|---------|----------|
| `page` | int | 1 | Sayfa numarası |
| `pageSize` | int | 10 | Sayfa başına bildirim (max: 50) |

## 🔐 Yetkilendirme

JWT token gerektirir.

## 📝 Örnek Kullanım

```bash
curl -X GET "https://api.awaxen.com/api/v1/notifications?page=1&pageSize=5" \\
  -H "Authorization: Bearer <jwt_token>"
```

## 📤 Örnek Yanıt

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "type": "warning",
      "title": "Cihaz Çevrimdışı",
      "message": "Shelly Pro 3EM cihazı 5 dakikadır çevrimdışı",
      "is_read": false,
      "created_at": "2024-01-04T12:00:00Z",
      "read_at": null
    }
  ],
  "total": 15,
  "page": 1,
  "page_size": 5,
  "has_more": true
}
```
    """,
    responses={
        200: {
            "description": "Bildirim listesi başarıyla döndürüldü",
            "content": {
                "application/json": {
                    "example": {
                        "items": [
                            {
                                "id": "550e8400-e29b-41d4-a716-446655440000",
                                "type": "warning",
                                "title": "Cihaz Çevrimdışı",
                                "message": "Shelly Pro 3EM cihazı 5 dakikadır çevrimdışı",
                                "is_read": False,
                                "created_at": "2024-01-04T12:00:00Z",
                                "read_at": None
                            }
                        ],
                        "total": 15,
                        "page": 1,
                        "page_size": 5,
                        "has_more": True
                    }
                }
            }
        },
        401: {"description": "Yetkisiz erişim"},
    },
)
async def list_notifications(
    current_user: CurrentUser,
    service: NotificationServiceDep,
    page: int = Query(default=1, ge=1, description="Sayfa numarası"),
    pageSize: int = Query(default=10, ge=1, le=50, alias="pageSize", description="Sayfa başına kayıt"),
    unread_only: bool = Query(default=False, alias="unreadOnly", description="Sadece okunmamışlar"),
) -> NotificationListResponse:
    """Kullanıcının bildirimlerini listeler."""
    return await service.get_notifications(
        user_id=current_user.id,
        page=page,
        page_size=pageSize,
        unread_only=unread_only,
    )


@router.patch(
    "/read",
    summary="Bildirimleri Okundu İşaretle",
    description="""
Belirtilen bildirimleri okundu olarak işaretler.

## 📥 Request Body

```json
{
  "notification_ids": [
    "550e8400-e29b-41d4-a716-446655440000",
    "550e8400-e29b-41d4-a716-446655440001"
  ]
}
```

## 📤 Örnek Yanıt

```json
{
  "message": "2 bildirim okundu olarak işaretlendi"
}
```
    """,
    responses={
        200: {
            "description": "Bildirimler okundu olarak işaretlendi",
            "content": {
                "application/json": {
                    "example": {"message": "2 bildirim okundu olarak işaretlendi"}
                }
            }
        },
        401: {"description": "Yetkisiz erişim"},
    },
)
async def mark_notifications_read(
    request: NotificationMarkReadRequest,
    current_user: CurrentUser,
    service: NotificationServiceDep,
) -> dict[str, str | int]:
    """Bildirimleri okundu olarak işaretle."""
    count = await service.mark_as_read(
        user_id=current_user.id,
        notification_ids=request.notification_ids,
    )
    return {"message": f"{count} bildirim okundu olarak işaretlendi", "count": count}


@router.get(
    "/unread-count",
    summary="Okunmamış Bildirim Sayısı",
    description="""
Kullanıcının okunmamış bildirim sayısını döner.

## 📝 Örnek Kullanım

```bash
curl -X GET "https://api.awaxen.com/api/v1/notifications/unread-count" \\
  -H "Authorization: Bearer <jwt_token>"
```

## 📤 Örnek Yanıt

```json
{
  "count": 5
}
```
    """,
    responses={
        200: {
            "description": "Okunmamış bildirim sayısı",
            "content": {
                "application/json": {
                    "example": {"count": 5}
                }
            }
        },
        401: {"description": "Yetkisiz erişim"},
    },
)
async def get_unread_count(
    current_user: CurrentUser,
    service: NotificationServiceDep,
) -> dict[str, int]:
    """Okunmamış bildirim sayısını döner."""
    count = await service.get_unread_count(current_user.id)
    return {"count": count}


# ============== FCM Token Endpoints ==============

@router.post(
    "/fcm-token",
    response_model=FCMTokenResponse,
    summary="FCM Token Kaydet",
    description="""
Firebase Cloud Messaging token'ı kaydet.

Frontend, kullanıcı bildirim izni verdikten sonra bu endpoint'i çağırmalı.

## 📥 Request Body

```json
{
  "fcm_token": "dGVzdC10b2tlbi0xMjM0NTY3ODkw...",
  "device_type": "web",
  "device_name": "Chrome on Windows"
}
```

## 📤 Örnek Yanıt

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "device_type": "web",
  "device_name": "Chrome on Windows",
  "is_active": true,
  "created_at": "2024-01-04T12:00:00Z"
}
```
    """,
)
async def register_fcm_token(
    request: FCMTokenRegisterRequest,
    current_user: CurrentUser,
    service: NotificationServiceDep,
) -> FCMTokenResponse:
    """FCM token kaydet."""
    token = await service.register_fcm_token(current_user.id, request)
    return FCMTokenResponse.model_validate(token)


# ============== Preferences Endpoints ==============

@router.get(
    "/preferences",
    response_model=NotificationPreferenceResponse,
    summary="Bildirim Tercihleri",
    description="""
Kullanıcının bildirim tercihlerini döner.

## 📤 Örnek Yanıt

```json
{
  "push_enabled": true,
  "telegram_enabled": true,
  "email_enabled": false,
  "quiet_hours_enabled": false,
  "quiet_hours_start": null,
  "quiet_hours_end": null
}
```
    """,
)
async def get_preferences(
    current_user: CurrentUser,
    service: NotificationServiceDep,
) -> NotificationPreferenceResponse:
    """Bildirim tercihlerini getir."""
    return await service.get_preferences(current_user.id)


@router.patch(
    "/preferences",
    response_model=NotificationPreferenceResponse,
    summary="Bildirim Tercihlerini Güncelle",
    description="""
Kullanıcının bildirim tercihlerini günceller.

## 📥 Request Body

```json
{
  "push_enabled": true,
  "telegram_enabled": false,
  "quiet_hours_enabled": true,
  "quiet_hours_start": "22:00",
  "quiet_hours_end": "08:00"
}
```
    """,
)
async def update_preferences(
    request: NotificationPreferenceUpdateRequest,
    current_user: CurrentUser,
    service: NotificationServiceDep,
) -> NotificationPreferenceResponse:
    """Bildirim tercihlerini güncelle."""
    return await service.update_preferences(
        user_id=current_user.id,
        updates=request.model_dump(exclude_unset=True),
    )


# ============== Telegram Endpoints ==============

@router.get(
    "/telegram/link",
    response_model=TelegramLinkResponse,
    summary="Telegram Bağlantı Linki",
    description="""
Telegram bot bağlantı linkini döner.

Kullanıcı bu linke tıklayarak Telegram botunu başlatabilir.
Bot başlatıldığında, kullanıcının chat_id'si otomatik kaydedilir.

## 📤 Örnek Yanıt

```json
{
  "link": "https://t.me/AwaxenBot?start=550e8400-e29b-41d4-a716-446655440000",
  "bot_username": "AwaxenBot",
  "is_connected": false,
  "telegram_username": null
}
```
    """,
)
async def get_telegram_link(
    current_user: CurrentUser,
    service: NotificationServiceDep,
) -> TelegramLinkResponse:
    """Telegram bağlantı linkini getir."""
    result = await service.get_telegram_link(current_user.id)
    return TelegramLinkResponse(**result)


@router.patch(
    "/read-all",
    summary="Tüm Bildirimleri Okundu İşaretle",
    description="Kullanıcının tüm bildirimlerini okundu olarak işaretler.",
)
async def mark_all_as_read(
    current_user: CurrentUser,
    service: NotificationServiceDep,
) -> dict[str, str | int]:
    """Tüm bildirimleri okundu olarak işaretle."""
    count = await service.mark_all_as_read(current_user.id)
    return {"message": f"{count} bildirim okundu olarak işaretlendi", "count": count}
