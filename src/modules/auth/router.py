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
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from src.modules.auth.dependencies import (
    AuthServiceDep,
    CurrentActiveUser,
    CurrentUser,
    require_role,
)
from src.modules.auth.schemas import (
    AddUserToOrganizationRequest,
    AddUserToOrganizationResponse,
    AdminOrganizationDetailResponse,
    AdminOrganizationListResponse,
    AdminRoleListResponse,
    AdminUserListResponse,
    AssignRoleToUserRequest,
    AssignRoleToUserResponse,
    Auth0SyncRequest,
    Auth0SyncResponse,
    AvailableModulesResponse,
    AvailablePermissionsResponse,
    AvailableRolesResponse,
    CreateOrganizationStep2Request,
    CreateOrganizationStep2Response,
    CreateOrganizationWithUserRequest,
    CreateOrganizationWithUserResponse,
    MeResponse,
    OnboardingRequest,
    OnboardingResponse,
    OrganizationModulesUpdate,
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
router = APIRouter(prefix="/auth", tags=["Auth"])
users_router = APIRouter(prefix="/users", tags=["Users"])
admin_router = APIRouter(prefix="/admin", tags=["Admin"])


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
    
    NOT: auth0_id ve email SADECE request body'den alınır.
    Header'lardan almak güvenlik açığı oluşturur (Header Spoofing).
    Production'da bu bilgiler Auth0 token'ından decode edilmelidir.
    """
    if not request.auth0_id or not request.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="auth0_id ve email zorunludur"
        )
    
    role = request.role
    if role and role in AUTH0_ROLE_MAPPING:
        role = AUTH0_ROLE_MAPPING[role]
    
    sync_request = Auth0SyncRequest(
        auth0_id=request.auth0_id,
        email=request.email,
        name=request.name,
        role=role,
    )
    
    return await auth_service.sync_auth0_user(sync_request)


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
# ADMIN ROUTER - /api/v1/admin/*
# Admin işlemleri (Organization, User, Role yönetimi)
# ============================================================

# ---------- Organization CRUD ----------

@admin_router.post(
    "/organizations",
    response_model=CreateOrganizationWithUserResponse,
    summary="Organizasyon Oluştur (Tab 1)",
    description="""
**Sadece Admin için.**

Yeni organizasyon ve ilk kullanıcı (tenant owner) oluşturur.

**Tab 1 Akışı:**
1. Organization bilgileri (name, type, adres, koordinat)
2. İlk kullanıcı bilgileri (first_name, last_name, email, phone)
3. Kullanıcı otomatik tenant rolüyle eklenir

**Sonraki Adım:** Tab 2 - Modül ataması
    """,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(["admin"]))],
)
async def create_organization(
    request: CreateOrganizationWithUserRequest,
    auth_service: AuthServiceDep,
) -> CreateOrganizationWithUserResponse:
    """Organizasyon ve ilk kullanıcı oluştur."""
    return await auth_service.create_organization_with_user(request)


@admin_router.post(
    "/organizations/{org_id}/modules",
    response_model=CreateOrganizationStep2Response,
    summary="Modül Ata (Tab 2)",
    description="""
**Sadece Admin için.**

Organizasyona aktif modülleri atar.

**Modüller:**
- core (otomatik eklenir)
- asset_management, iot, energy, rewards, billing, compliance, notifications, dashboard
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def assign_organization_modules(
    org_id: str,
    request: OrganizationModulesUpdate,
    auth_service: AuthServiceDep,
) -> CreateOrganizationStep2Response:
    """Organizasyona modül ata."""
    step2_request = CreateOrganizationStep2Request(
        organization_id=org_id,
        modules=request.modules,
    )
    return await auth_service.create_organization_step2(step2_request)


@admin_router.get(
    "/organizations",
    response_model=AdminOrganizationListResponse,
    summary="Organizasyonları Listele",
    description="""
**Sadece Admin için.**

Tüm organizasyonları listeler.

**Filtreler:** search, is_active
**Sayfalama:** page, page_size
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_organizations(
    auth_service: AuthServiceDep,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    is_active: bool | None = None,
) -> AdminOrganizationListResponse:
    """Organizasyonları listele."""
    return await auth_service.list_all_organizations(
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
    )


@admin_router.get(
    "/organizations/{org_id}",
    response_model=AdminOrganizationDetailResponse,
    summary="Organizasyon Detayı",
    description="""
**Sadece Admin için.**

Organizasyon detayını döner.

**Dönen Bilgiler:**
- Organizasyon bilgileri
- Kullanıcı listesi
- Aktif modüller
- Wallet özeti
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def get_organization(
    org_id: str,
    auth_service: AuthServiceDep,
) -> AdminOrganizationDetailResponse:
    """Organizasyon detayı."""
    return await auth_service.get_organization_detail(org_id)


@admin_router.delete(
    "/organizations/{org_id}",
    summary="Organizasyon Sil",
    description="""
**Sadece Admin için.**

Organizasyonu siler.

**Silme Türleri:**
- `hard_delete=false` (varsayılan): Soft delete - organizasyon devre dışı bırakılır (is_active=False)
- `hard_delete=true`: Hard delete - organizasyon ve tüm ilişkili veriler kalıcı olarak silinir

**⚠️ DİKKAT:** Hard delete işlemi geri alınamaz!
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def delete_organization(
    org_id: str,
    auth_service: AuthServiceDep,
    hard_delete: bool = False,
):
    """Organizasyonu sil (Admin only)."""
    import uuid
    return await auth_service.delete_organization(
        org_id=uuid.UUID(org_id),
        hard_delete=hard_delete,
    )


@admin_router.get(
    "/organizations/{org_id}/stats",
    summary="Organizasyon İstatistikleri",
    description="""
**Admin veya Tenant için.**

Organizasyon istatistiklerini döner.
    """,
)
async def get_organization_stats(
    org_id: str,
    auth_service: AuthServiceDep,
    current_user: CurrentUser = None,
):
    """Organizasyon istatistikleri."""
    if current_user:
        is_admin = current_user.is_superuser or any(
            m.role and m.role.code == "admin" 
            for m in current_user.organization_memberships
        )
        is_tenant_of_org = any(
            m.role and m.role.code == "tenant" and str(m.organization_id) == org_id
            for m in current_user.organization_memberships
        )
        
        if not is_admin and not is_tenant_of_org:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Yetkisiz erişim"
            )
    
    return await auth_service.get_organization_stats(org_id)


# ---------- Organization Users ----------

@admin_router.get(
    "/organizations/{org_id}/users",
    response_model=AdminUserListResponse,
    summary="Organizasyon Kullanıcıları",
    description="""
**Admin veya Tenant için.**

Organizasyondaki kullanıcıları listeler.
    """,
)
async def list_organization_users(
    org_id: str,
    auth_service: AuthServiceDep,
    current_user: CurrentUser = None,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> AdminUserListResponse:
    """Organizasyon kullanıcılarını listele."""
    if current_user:
        is_admin = current_user.is_superuser or any(
            m.role and m.role.code == "admin" 
            for m in current_user.organization_memberships
        )
        is_tenant_of_org = any(
            m.role and m.role.code == "tenant" and str(m.organization_id) == org_id
            for m in current_user.organization_memberships
        )
        
        if not is_admin and not is_tenant_of_org:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Yetkisiz erişim"
            )
    
    return await auth_service.list_organization_users(
        organization_id=org_id,
        page=page,
        page_size=page_size,
        search=search,
        role=role,
        is_active=is_active,
    )


@admin_router.post(
    "/organizations/{org_id}/users",
    response_model=AddUserToOrganizationResponse,
    summary="Kullanıcı Davet Et",
    description="""
**Sadece Admin için.**

Organizasyona kullanıcı davet eder.
    """,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(["admin"]))],
)
async def invite_user_to_organization(
    org_id: str,
    request: AddUserToOrganizationRequest,
    auth_service: AuthServiceDep,
) -> AddUserToOrganizationResponse:
    """Kullanıcı davet et."""
    request.organization_id = org_id
    return await auth_service.add_user_to_organization(request)


# ---------- User Management ----------

@admin_router.post(
    "/users/{user_id}/role",
    response_model=AssignRoleToUserResponse,
    summary="Kullanıcıya Rol Ata",
    description="""
**Sadece Admin için.**

Kullanıcıya belirli bir organizasyonda rol atar.
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def assign_role_to_user(
    user_id: str,
    request: AssignRoleToUserRequest,
    auth_service: AuthServiceDep,
) -> AssignRoleToUserResponse:
    """Kullanıcıya rol ata."""
    return await auth_service.assign_role_to_user(user_id, request)


# ---------- Roles & Permissions (Admin) ----------

@admin_router.get(
    "/roles",
    response_model=AdminRoleListResponse,
    summary="Rolleri Listele",
    description="Sistemdeki tüm rolleri listeler.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_roles(auth_service: AuthServiceDep) -> AdminRoleListResponse:
    """Rolleri listele."""
    return await auth_service.list_all_roles()


# ============== L7 Enterprise Admin Endpoints ==============

@admin_router.patch(
    "/organizations/{org_id}/suspend",
    summary="Organizasyonu Askıya Al",
    description="""
**Sadece Admin için.**

Organizasyonu askıya alır. Kullanıcılar giriş yapamaz ama veriler silinmez.

**Kullanım Senaryoları:**
- Faturasını ödemeyen müşteri
- TOS (Kullanım Şartları) ihlali
- Güvenlik soruşturması
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def suspend_organization(
    org_id: str,
    auth_service: AuthServiceDep,
    reason: str | None = None,
):
    """Organizasyonu askıya al."""
    import uuid
    return await auth_service.suspend_organization(
        org_id=uuid.UUID(org_id),
        reason=reason,
    )


@admin_router.patch(
    "/organizations/{org_id}/reactivate",
    summary="Organizasyonu Yeniden Aktifleştir",
    description="""
**Sadece Admin için.**

Askıya alınmış organizasyonu yeniden aktifleştirir.
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def reactivate_organization(
    org_id: str,
    auth_service: AuthServiceDep,
):
    """Organizasyonu yeniden aktifleştir."""
    import uuid
    return await auth_service.reactivate_organization(
        org_id=uuid.UUID(org_id),
    )


@admin_router.post(
    "/organizations/{org_id}/transfer-ownership",
    summary="Organizasyon Sahipliğini Devret",
    description="""
**Sadece Admin için.**

Organizasyon sahipliğini (Tenant Admin yetkisini) başka bir kullanıcıya devreder.

**Kullanım Senaryoları:**
- Şirketin IT müdürü işten ayrıldı
- Organizasyon satıldı/devredildi
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def transfer_organization_ownership(
    org_id: str,
    new_owner_user_id: str,
    auth_service: AuthServiceDep,
):
    """Organizasyon sahipliğini devret."""
    import uuid
    return await auth_service.transfer_organization_ownership(
        org_id=uuid.UUID(org_id),
        new_owner_user_id=uuid.UUID(new_owner_user_id),
    )


@admin_router.get(
    "/users",
    response_model=AdminUserListResponse,
    summary="Tüm Kullanıcıları Listele (Global)",
    description="""
**Sadece Admin için.**

Sistemdeki TÜM kullanıcıları (hangi organizasyonda olursa olsun) listeler.

**Filtreler:** search (email, ad, telefon), status, is_active
**Sayfalama:** page, page_size
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_all_users_global(
    auth_service: AuthServiceDep,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    status: str | None = None,
    is_active: bool | None = None,
) -> AdminUserListResponse:
    """Tüm kullanıcıları listele (Global Search)."""
    return await auth_service.list_all_users_global(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        is_active=is_active,
    )


@admin_router.post(
    "/users/{user_id}/revoke-sessions",
    summary="Kullanıcı Oturumlarını Sonlandır",
    description="""
**Sadece Admin için.**

Kullanıcının tüm aktif oturumlarını (token'larını) iptal eder.

**Kullanım Senaryoları:**
- Kullanıcı hesabı hacklendiğinde
- Cihaz çalındığında
- Güvenlik ihlali şüphesinde
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def revoke_user_sessions(
    user_id: str,
    auth_service: AuthServiceDep,
):
    """Kullanıcı oturumlarını sonlandır."""
    import uuid
    return await auth_service.revoke_user_sessions(
        user_id=uuid.UUID(user_id),
    )


@admin_router.post(
    "/users/{user_id}/ban",
    summary="Kullanıcıyı Yasakla",
    description="""
**Sadece Admin için.**

Kullanıcıyı sistemden kalıcı olarak yasaklar.
Tüm oturumları sonlandırılır ve giriş yapması engellenir.
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def ban_user(
    user_id: str,
    auth_service: AuthServiceDep,
    reason: str | None = None,
):
    """Kullanıcıyı yasakla."""
    import uuid
    return await auth_service.ban_user(
        user_id=uuid.UUID(user_id),
        reason=reason,
    )
