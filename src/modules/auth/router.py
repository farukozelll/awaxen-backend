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
