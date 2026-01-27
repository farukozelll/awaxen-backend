"""
Auth Module - API Endpoints (Best Practices)

REST API yapısı:
- /api/v1/auth/*     → Kimlik doğrulama (sync, login)
- /api/v1/users/*    → Kullanıcı profil işlemleri (me, onboarding)
- /api/v1/admin/*    → Admin işlemleri (org, user, role yönetimi)

Rol Hiyerarşisi:
1. admin  - Sistem yöneticisi (tüm yetkiler)
2. tenant - Organizasyon yöneticisi (kendi org'unda tam yetki)
3. user   - Normal kullanıcı (salt okunur)
4. device - Cihaz/Telemetri erişimi
"""

from fastapi import APIRouter, Header, HTTPException, status

from src.modules.auth.dependencies import (
    AuthServiceDep,
    CurrentActiveUser,
    CurrentUser,
)
from src.modules.auth.schemas import (
    Auth0SyncRequest,
    Auth0SyncResponse,
    AvailableModulesResponse,
    AvailablePermissionsResponse,
    AvailableRolesResponse,
    InvitationValidateResponse,
    MeResponse,
    OnboardingRequest,
    OnboardingResponse,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
)

# Auth0 Rol Eşleşmesi
AUTH0_ROLE_MAPPING = {
    "admin": "admin",
    "tenant": "tenant",
    "user": "user",
    "device": "device",
}


# ============================================================
# Router Tanımları
# ============================================================
# L7 Best Practice: Auth modülü SADECE kimlik doğrulama yapar.
# Admin işlemleri ayrı Admin modülünde (/api/v1/admin/*).
router = APIRouter(prefix="/auth", tags=["01. 🔐 Auth"])
users_router = APIRouter(prefix="/users", tags=["02. 👤 Profile"])


# ============================================================
# AUTH ROUTER - /api/v1/auth/*
# Kimlik doğrulama işlemleri
# ============================================================

@router.post(
    "/sync",
    response_model=Auth0SyncResponse,
    summary="Auth0 Senkronizasyonu",
    description="""
Auth0 kullanıcısını veritabanı ile senkronize eder.

**Güvenlik:** Bu endpoint sadece Auth0 token'ından alınan bilgileri kullanır.
Header spoofing'e karşı korumalıdır.

**İlk Girişte:**
- Kullanıcı kaydı oluşturulur
- Varsayılan organizasyon oluşturulur (tenant rolüyle)

**Sonraki Girişlerde:**
- Kullanıcı bilgileri güncellenir
- last_login güncellenir

**⚠️ ÖNERİ:** Production'da bu endpoint yerine Auth0 Post-Login Action
veya Webhook kullanarak backend-to-backend senkronizasyon yapılmalıdır.
Frontend'in inisiyatifine bırakmak "Zombie User" riski oluşturur.
    """,
)
async def sync_auth0_user(
    request: Auth0SyncRequest,
    auth_service: AuthServiceDep,
) -> Auth0SyncResponse:
    """Auth0 kullanıcısını senkronize et.
    
    GÜVENLİK: Frontend'den gelen role isteğini ez, None yap.
    Asla client input'tan gelen role güvenme.
    """
    if not request.auth0_id or not request.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="auth0_id ve email zorunludur"
        )
    
    # GÜVENLİK: Frontend'den gelen role isteğini ez, None yap.
    # Kullanıcı kendine admin rolü atayamaz.
    request.role = None
    
    return await auth_service.sync_auth0_user(request)


@router.post(
    "/webhook/auth0",
    summary="Auth0 Webhook (Backend-to-Backend)",
    description="""
**Auth0 Post-Login Action Webhook**

Bu endpoint Auth0 tarafından kullanıcı login olduğunda çağrılır.
Frontend'in inisiyatifine bırakmadan backend-to-backend senkronizasyon sağlar.

**Güvenlik:**
- `X-Auth0-Webhook-Secret` header'ı ile doğrulama yapılır
- Bu secret Auth0 Action'da ve backend'de aynı olmalıdır

**Auth0 Action Örneği:**
```javascript
exports.onExecutePostLogin = async (event, api) => {
  await axios.post('https://api.awaxen.com/api/v1/auth/webhook/auth0', {
    auth0_id: event.user.user_id,
    email: event.user.email,
    name: event.user.name,
    email_verified: event.user.email_verified,
  }, {
    headers: { 'X-Auth0-Webhook-Secret': 'your-secret-here' }
  });
};
```
    """,
)
async def auth0_webhook(
    request: Auth0SyncRequest,
    auth_service: AuthServiceDep,
    x_auth0_webhook_secret: str = Header(None, alias="X-Auth0-Webhook-Secret"),
) -> dict:
    """
    Auth0 Post-Login Action webhook handler.
    
    Bu endpoint frontend'den DEĞİL, Auth0 sunucusundan çağrılır.
    Zombie User problemini çözer.
    """
    from src.core.config import settings
    
    # Webhook secret doğrulama
    expected_secret = getattr(settings, 'auth0_webhook_secret', None)
    if expected_secret and x_auth0_webhook_secret != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret"
        )
    
    if not request.auth0_id or not request.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="auth0_id ve email zorunludur"
        )
    
    result = await auth_service.sync_auth0_user(request)
    
    return {
        "status": "synced",
        "user_id": str(result.user.id) if result.user else None,
        "is_new": result.is_new_user,
    }


@router.get(
    "/roles",
    response_model=AvailableRolesResponse,
    summary="Mevcut Roller",
    description="Sistemdeki tüm rolleri listeler.",
)
async def get_available_roles(auth_service: AuthServiceDep) -> AvailableRolesResponse:
    """Mevcut rolleri döner."""
    return auth_service.get_available_roles()


@router.get(
    "/permissions",
    response_model=AvailablePermissionsResponse,
    summary="Mevcut Yetkiler",
    description="Sistemdeki tüm yetkileri listeler.",
)
async def get_available_permissions(auth_service: AuthServiceDep) -> AvailablePermissionsResponse:
    """Mevcut yetkileri döner."""
    return auth_service.get_available_permissions()


@router.get(
    "/modules",
    response_model=AvailableModulesResponse,
    summary="Mevcut Modüller",
    description="Sistemdeki tüm modülleri listeler.",
)
async def get_available_modules(auth_service: AuthServiceDep) -> AvailableModulesResponse:
    """Mevcut modülleri döner."""
    return auth_service.get_available_modules()


# ============================================================
# USERS ROUTER - /api/v1/users/*
# Kullanıcı profil işlemleri
# ============================================================

@users_router.get(
    "/me",
    response_model=MeResponse,
    summary="Kullanıcı Profili",
    description="""
Token'daki kullanıcının profil bilgisini döner.

**Dönen Bilgiler:**
- Kullanıcı bilgileri (id, email, ad)
- Rol ve yetkiler
- Organizasyon bilgisi
- Aktif modüller
- Wallet bakiyesi (AWX)
- Onboarding durumu
    """,
)
async def get_my_profile(
    current_user: CurrentUser,
    auth_service: AuthServiceDep,
) -> MeResponse:
    """Kullanıcı profilini döner."""
    return await auth_service.get_me(current_user)


@users_router.patch(
    "/me",
    response_model=ProfileUpdateResponse,
    summary="Profil Güncelle",
    description="""
Kullanıcı profil bilgilerini günceller.

**Güncellenebilir Alanlar:**
- full_name
- phone_number
- telegram_username
    """,
)
async def update_my_profile(
    request: ProfileUpdateRequest,
    current_user: CurrentActiveUser,
    auth_service: AuthServiceDep,
) -> ProfileUpdateResponse:
    """Profil güncelle."""
    return await auth_service.update_profile(current_user, request)


@users_router.patch(
    "/me/onboarding",
    response_model=OnboardingResponse,
    summary="Onboarding Tamamla",
    description="""
Kullanıcı onboarding bilgilerini tamamlar.

**Bilgiler:**
- Kişisel: first_name, last_name, phone
- Adres: country, city, district
- Bildirim ayarları
- KVKK onayları
    """,
)
async def complete_onboarding(
    request: OnboardingRequest,
    current_user: CurrentActiveUser,
    auth_service: AuthServiceDep,
) -> OnboardingResponse:
    """Onboarding tamamla."""
    return await auth_service.complete_onboarding(current_user, request)


# ============================================================
# INVITATION ENDPOINTS
# ============================================================

@router.get(
    "/invitation/{token}",
    response_model=InvitationValidateResponse,
    summary="Davetiye Doğrula",
    description="""
Davetiye token'ını doğrular.

Frontend, kullanıcı davet linkine tıkladığında bu endpoint'i çağırır.
Geçerli ise organizasyon bilgisini gösterir.

**Akış:**
1. Kullanıcı linke tıklar: `https://app.awaxen.com/join?token=XYZ`
2. Frontend bu endpoint'i çağırır
3. Geçerli ise "Ülker Gıda'ya katılmak üzeresin" mesajı gösterilir
4. Kullanıcı Auth0 ile giriş yapar
5. /auth/sync sırasında davetiye otomatik tüketilir
    """,
)
async def validate_invitation(
    token: str,
    auth_service: AuthServiceDep,
) -> InvitationValidateResponse:
    """Davetiye token'ını doğrula (public endpoint)."""
    result = await auth_service.validate_invitation(token)
    return InvitationValidateResponse(**result)


# ============================================================
# NOT: Tenant endpoint'leri ayrı tenant_router.py'de.
# main.py'de ayrı olarak include edilir.
# Admin endpoint'leri ayrı Admin modülünde.
# /api/v1/admin/* -> src/modules/admin/router.py
# L7 Best Practice: Separation of Concerns
# ============================================================
