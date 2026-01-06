"""
Kullanıcı Kimlik Doğrulama ve Profil Endpoint'leri - v6.0

Auth0 Entegrasyonu ile JWT tabanlı kimlik doğrulama.

Endpoint'ler:
- GET  /api/v1/auth/me     - Kullanıcı profili, rol ve yetkiler
- PATCH /api/v1/auth/me    - Profil güncelleme (ad, telefon, telegram)
- POST /api/v1/auth/sync   - Auth0 kullanıcısını DB'ye senkronize et

NOT: /login ve /register endpoint'leri kaldırıldı.
     Kimlik doğrulama Auth0 üzerinden yapılmaktadır.
"""
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from src.modules.auth.dependencies import (
    AuthServiceDep,
    CurrentActiveUser,
    CurrentUser,
)
from src.modules.auth.schemas import (
    Auth0SyncRequest,
    Auth0SyncResponse,
    MeResponse,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
)


# Auth0 Rol İsimleri -> Awaxen DB Rol Kodları Eşleşmesi
# Rol Hiyerarşisi:
# 1. super_admin - Tam sistem yetkisi
# 2. admin - Organizasyon yönetimi
# 3. operator - Cihaz kontrolü
# 4. user - Salt okunur erişim
# 5. agent - Kiracı bulma, sözleşme yönetimi
AUTH0_ROLE_MAPPING = {
    # Super Admin
    "super_admin": "super_admin",
    "superadmin": "super_admin",
    # Admin
    "admin": "admin",
    "org_admin": "admin",
    # Operator
    "operator": "operator",
    "solar-user": "operator",
    "farmer-user": "operator",
    "farmer": "operator",
    # User (Salt okunur)
    "user": "user",
    "viewer": "user",
    "demo-user": "user",
    # Agent
    "agent": "agent",
    "property_manager": "agent",
}


router = APIRouter(prefix="/auth", tags=["Auth"])


# ============================================================
# GET /api/v1/auth/me - Kullanıcı Profili
# ============================================================

@router.get(
    "/me",
    response_model=MeResponse,
    summary="Kullanıcı Profili",
    description="""
Token'daki kullanıcının profil bilgisini döner.

**Dönen Bilgiler:**
- Kullanıcı ID ve Auth0 ID
- Email ve tam ad
- Telefon ve Telegram kullanıcı adı
- Rol bilgisi (kod ve isim)
- Yetki listesi (permissions)
- Varsayılan organizasyon bilgisi

**Kullanım:**
```
GET /api/v1/auth/me
Authorization: Bearer <jwt_token>
```
    """,
    responses={
        200: {
            "description": "Kullanıcı profili başarıyla döndürüldü",
            "content": {
                "application/json": {
                    "example": {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "auth0_id": "google-oauth2|123456789",
                        "email": "user@awaxen.com",
                        "full_name": "Ahmet Yılmaz",
                        "phone": "+905551112233",
                        "telegram_username": "ahmetyilmaz",
                        "role": {"code": "admin", "name": "Admin"},
                        "permissions": ["can_view_devices", "can_edit_devices"],
                        "organization": {
                            "id": "...",
                            "name": "Ahmet's Organization",
                            "slug": "ahmet-organization"
                        },
                        "is_active": True
                    }
                }
            }
        },
        401: {"description": "Yetkisiz erişim - Geçersiz veya eksik token"},
    },
)
async def get_my_profile(
    current_user: CurrentUser,
    auth_service: AuthServiceDep,
) -> MeResponse:
    """Token'daki kullanıcının profil bilgisini döner."""
    return await auth_service.get_me(current_user)


# ============================================================
# PATCH /api/v1/auth/me - Profil Güncelleme
# ============================================================

@router.patch(
    "/me",
    response_model=ProfileUpdateResponse,
    summary="Profil Güncelle",
    description="""
Token'daki kullanıcının profil bilgilerini günceller.

**Güncellenebilir Alanlar:**
- `full_name` - Tam ad
- `phone_number` - Telefon numarası (+905551112233 formatında)
- `telegram_username` - Telegram kullanıcı adı (@ olmadan)

**Örnek İstek:**
```json
{
  "full_name": "Faruk Özel",
  "phone_number": "+905551112233",
  "telegram_username": "farukozel"
}
```

**Not:** Sadece gönderilen alanlar güncellenir. Boş string gönderilirse alan temizlenir.
    """,
    responses={
        200: {
            "description": "Profil başarıyla güncellendi",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Profil güncellendi",
                        "user": {
                            "id": "...",
                            "full_name": "Faruk Özel",
                            "phone": "+905551112233",
                            "telegram_username": "farukozel"
                        }
                    }
                }
            }
        },
        400: {"description": "Geçersiz veri formatı"},
        401: {"description": "Yetkisiz erişim"},
    },
)
async def update_my_profile(
    request: ProfileUpdateRequest,
    current_user: CurrentActiveUser,
    auth_service: AuthServiceDep,
) -> ProfileUpdateResponse:
    """Token'daki kullanıcının profil bilgilerini güncelle."""
    return await auth_service.update_profile(current_user, request)


# ============================================================
# POST /api/v1/auth/sync - Auth0 Senkronizasyonu
# ============================================================

@router.post(
    "/sync",
    response_model=Auth0SyncResponse,
    summary="Auth0 Kullanıcı Senkronizasyonu",
    description="""
Auth0 kullanıcısını Postgres veritabanı ile senkronize eder (Upsert).

**İlk Girişte Otomatik Oluşturulur:**
- Kullanıcı kaydı
- Varsayılan organizasyon
- Cüzdan (Wallet)

**Rol Eşleştirme:**
Auth0'dan gelen rol kodu, veritabanındaki roles tablosundan eşleştirilir:
- `super_admin`, `superadmin` → `super_admin`
- `admin` → `admin`
- `farmer-user`, `farmer` → `farmer`
- `solar-user`, `operator` → `operator`
- `demo-user`, `viewer` → `viewer`

**Kullanım:**
Frontend, Auth0'dan token aldıktan sonra bu endpoint'i çağırmalıdır.

```json
POST /api/v1/auth/sync
{
  "auth0_id": "google-oauth2|123456789",
  "email": "user@awaxen.com",
  "name": "Ahmet Yılmaz",
  "role": "admin"
}
```

**Alternatif:** Header'lardan da veri gönderilebilir:
- `X-Auth0-Id`
- `X-Auth0-Email`
- `X-Auth0-Name`
    """,
    responses={
        200: {
            "description": "Mevcut kullanıcı güncellendi",
            "content": {
                "application/json": {
                    "example": {
                        "status": "synced",
                        "message": "Kullanıcı senkronize edildi",
                        "user": {"id": "...", "email": "user@awaxen.com"},
                        "organization": {"id": "...", "name": "..."}
                    }
                }
            }
        },
        201: {
            "description": "Yeni kullanıcı oluşturuldu",
            "content": {
                "application/json": {
                    "example": {
                        "status": "created",
                        "message": "Yeni kullanıcı oluşturuldu",
                        "user": {"id": "...", "email": "user@awaxen.com"},
                        "organization": {"id": "...", "name": "User's Organization"}
                    }
                }
            }
        },
        400: {"description": "Eksik parametre - auth0_id ve email zorunludur"},
    },
)
async def sync_auth0_user(
    request: Auth0SyncRequest,
    auth_service: AuthServiceDep,
    x_auth0_id: Annotated[str | None, Header(description="Auth0 kullanıcı ID'si")] = None,
    x_auth0_email: Annotated[str | None, Header(description="Kullanıcı email adresi")] = None,
    x_auth0_name: Annotated[str | None, Header(description="Kullanıcı tam adı")] = None,
) -> Auth0SyncResponse:
    """Auth0 kullanıcısını Postgres ile senkronize et (Upsert)."""
    
    # Header'lardan değerleri al (body öncelikli)
    auth0_id = request.auth0_id or x_auth0_id
    email = request.email or x_auth0_email
    name = request.name or x_auth0_name
    
    if not auth0_id or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="auth0_id ve email zorunludur"
        )
    
    # Rol eşleştirme
    role = request.role
    if role and role in AUTH0_ROLE_MAPPING:
        role = AUTH0_ROLE_MAPPING[role]
    
    # Yeni request oluştur
    sync_request = Auth0SyncRequest(
        auth0_id=auth0_id,
        email=email,
        name=name,
        role=role,
    )
    
    return await auth_service.sync_auth0_user(sync_request)
