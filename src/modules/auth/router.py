"""
Kullanıcı Kimlik Doğrulama ve Profil Endpoint'leri - v9.0

Auth0 Entegrasyonu ile JWT tabanlı kimlik doğrulama.
REST Best Practice uyumlu resource-based API tasarımı.

Rol Hiyerarşisi:
1. admin - Sistem yöneticisi (tüm yetkiler, org+user oluşturma)
2. tenant - Organizasyon yöneticisi (kendi org'unda tam yetki)
3. user - Normal kullanıcı (salt okunur)
4. device - Cihaz/Telemetri erişimi

Endpoint'ler:
## Users
- GET   /api/v1/users/me                    - Kullanıcı profili, rol ve yetkiler
- PATCH /api/v1/users/me                    - Profil güncelleme
- PATCH /api/v1/users/me/onboarding         - Onboarding bilgilerini tamamla

## Auth
- POST /api/v1/auth/sync                    - Auth0 kullanıcısını DB'ye senkronize et

## Roles & Permissions & Modules
- GET  /api/v1/auth/roles                   - Mevcut rolleri listele
- GET  /api/v1/auth/permissions             - Mevcut yetkileri listele
- GET  /api/v1/auth/modules                 - Mevcut modülleri listele

## Admin Operations (Resource-based)
- POST /api/v1/admin/organizations                      - Yeni organizasyon oluştur
- POST /api/v1/admin/organizations/{org_id}/modules     - Organizasyona modül ata
- POST /api/v1/admin/organizations/{org_id}/invites     - Organizasyona kullanıcı davet et
- POST /api/v1/admin/users/{user_id}/roles              - Kullanıcıya rol ata
- POST /api/v1/admin/users/{user_id}/permissions        - Kullanıcıya yetki ata
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from src.modules.auth.dependencies import (
    AuthServiceDep,
    CurrentActiveUser,
    CurrentUser,
    require_permissions,
    require_role,
)
from src.modules.auth.models import Permission
from src.modules.auth.schemas import (
    AddUserToOrganizationRequest,
    AddUserToOrganizationResponse,
    AddUserToOrgDirectRequest,
    AddUserToOrgDirectResponse,
    AdminOrganizationDetailResponse,
    AdminOrganizationListResponse,
    AdminPermissionListResponse,
    AdminRoleListResponse,
    AdminUserListResponse,
    AssignPermissionsRequest,
    AssignRoleRequest,
    AssignRoleToUserRequest,
    AssignRoleToUserResponse,
    Auth0SyncRequest,
    Auth0SyncResponse,
    AvailableModulesResponse,
    AvailablePermissionsResponse,
    AvailableRolesResponse,
    CreateOrganizationStep1Request,
    CreateOrganizationStep1Response,
    CreateOrganizationStep2Request,
    CreateOrganizationStep2Response,
    CreateOrganizationWithUserRequest,
    CreateOrganizationWithUserResponse,
    MeResponse,
    OnboardingRequest,
    OnboardingResponse,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
)


# Auth0 Rol İsimleri -> Awaxen DB Rol Kodları Eşleşmesi
# Rol Hiyerarşisi:
# 1. admin - Sistem yöneticisi (tüm yetkiler)
# 2. tenant - Organizasyon yöneticisi
# 3. user - Normal kullanıcı (salt okunur)
# 4. device - Cihaz/Telemetri erişimi
AUTH0_ROLE_MAPPING = {
    # Admin (Sistem yöneticisi)
    "admin": "admin",
  
    # Tenant (Organizasyon yöneticisi)
    "tenant": "tenant",
    
    # User (Salt okunur)
    "user": "user",
    
    # Device (Telemetri erişimi)
    "device": "device",
}


router = APIRouter(prefix="/auth", tags=["Auth"])
users_router = APIRouter(prefix="/users", tags=["Users"])
admin_router = APIRouter(prefix="/admin", tags=["Admin"])


# ============================================================
# Users Router - GET /api/v1/users/me - Kullanıcı Profili
# ============================================================

@users_router.get(
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
# Users Router - PATCH /api/v1/users/me - Profil Güncelleme
# ============================================================

@users_router.patch(
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
- Varsayılan organizasyon (tenant rolüyle)

**Rol Eşleştirme:**
Auth0'dan gelen rol kodu, veritabanındaki roles tablosundan eşleştirilir:
- `admin` → `admin` (Sistem yöneticisi)
- `tenant` → `tenant` (Organizasyon yöneticisi)
- `user` → `user` (Normal kullanıcı)
- `device` → `device` (Telemetri erişimi)

**Kullanım:**
Frontend, Auth0'dan token aldıktan sonra bu endpoint'i çağırmalıdır.

```json
POST /api/v1/auth/sync
{
  "auth0_id": "google-oauth2|123456789",
  "email": "user@awaxen.com",
  "name": "Ahmet Yılmaz",
  "role": "tenant"
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


# ============================================================
# GET /api/v1/auth/roles - Mevcut Roller
# ============================================================

@router.get(
    "/roles",
    response_model=AvailableRolesResponse,
    summary="Mevcut Rolleri Listele",
    description="""
Sistemdeki tüm rolleri ve varsayılan yetkilerini listeler.

**Roller:**
- `admin` - Sistem yöneticisi (tüm yetkiler)
- `tenant` - Organizasyon yöneticisi
- `user` - Normal kullanıcı (salt okunur)
- `device` - Cihaz/Telemetri erişimi
    """,
)
async def get_available_roles(
    auth_service: AuthServiceDep,
) -> AvailableRolesResponse:
    """Sistemdeki tüm rolleri döner."""
    return auth_service.get_available_roles()


# ============================================================
# GET /api/v1/auth/permissions - Mevcut Yetkiler
# ============================================================

@router.get(
    "/permissions",
    response_model=AvailablePermissionsResponse,
    summary="Mevcut Yetkileri Listele",
    description="""
Sistemdeki tüm yetkileri listeler.

**Yetki Kategorileri:**
- `org:*` - Organizasyon yönetimi
- `user:*` - Kullanıcı yönetimi
- `role:*` - Rol yönetimi
- `asset:*` - Asset yönetimi
- `zone:*` - Zone yönetimi
- `device:*` - Cihaz yönetimi
- `telemetry:*` - Telemetri
- `gateway:*` - Gateway yönetimi
- `billing:*` - Faturalama
- `audit:*` - Denetim
    """,
)
async def get_available_permissions(
    auth_service: AuthServiceDep,
) -> AvailablePermissionsResponse:
    """Sistemdeki tüm yetkileri döner."""
    return auth_service.get_available_permissions()


# ============================================================
# Admin Endpoint'leri
# ============================================================

@router.post(
    "/admin/organizations",
    response_model=CreateOrganizationWithUserResponse,
    summary="Organizasyon ve Kullanıcı Oluştur (Admin)",
    description="""
**Sadece Admin rolü için.**

Yeni bir organizasyon ve kullanıcı birlikte oluşturur.
Kullanıcı belirtilen rolle organizasyona eklenir.

**İş Akışı:**
1. Organizasyon oluşturulur
2. Kullanıcı oluşturulur
3. Kullanıcı belirtilen rolle organizasyona eklenir
4. Kullanıcı Auth0 ile giriş yaptığında sync endpoint'i çağrılır

**Örnek İstek:**
```json
{
  "organization_name": "Acme Corp",
  "organization_slug": "acme-corp",
  "organization_email": "info@acme.com",
  "user_email": "admin@acme.com",
  "user_full_name": "Ahmet Yılmaz",
  "user_role": "tenant",
  "user_permissions": ["billing:manage"]
}
```
    """,
    responses={
        201: {"description": "Organizasyon ve kullanıcı oluşturuldu"},
        400: {"description": "Geçersiz veri"},
        403: {"description": "Yetkisiz - Admin rolü gerekli"},
        409: {"description": "Email veya slug zaten kullanımda"},
    },
    status_code=status.HTTP_201_CREATED,
)
async def create_organization_with_user(
    request: CreateOrganizationWithUserRequest,
    auth_service: AuthServiceDep,
    current_user: CurrentUser = None,  # Admin kontrolü için
) -> CreateOrganizationWithUserResponse:
    """Admin tarafından organizasyon ve kullanıcı oluştur."""
    # Admin kontrolü - şimdilik is_superuser ile
    if current_user and not current_user.is_superuser:
        # Kullanıcının admin rolü var mı kontrol et
        is_admin = False
        for membership in current_user.organization_memberships:
            if membership.role and membership.role.code == "admin":
                is_admin = True
                break
        if not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu işlem için admin yetkisi gerekli"
            )
    
    return await auth_service.create_organization_with_user(request)


@router.post(
    "/admin/assign-role",
    summary="Rol Ata (Admin/Tenant)",
    description="""
**Admin veya Tenant rolü için.**

Kullanıcıya belirtilen organizasyonda rol atar.
Admin tüm organizasyonlarda, Tenant sadece kendi organizasyonunda rol atayabilir.

**Örnek İstek:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "organization_id": "550e8400-e29b-41d4-a716-446655440001",
  "role_code": "user",
  "additional_permissions": ["device:control"]
}
```
    """,
    responses={
        200: {"description": "Rol atandı"},
        403: {"description": "Yetkisiz"},
        404: {"description": "Kullanıcı veya organizasyon bulunamadı"},
    },
)
async def assign_role(
    request: AssignRoleRequest,
    auth_service: AuthServiceDep,
    current_user: CurrentUser = None,
) -> dict:
    """Kullanıcıya rol ata."""
    # Yetki kontrolü
    if current_user:
        is_admin = current_user.is_superuser
        is_tenant_of_org = False
        
        for membership in current_user.organization_memberships:
            if membership.role:
                if membership.role.code == "admin":
                    is_admin = True
                if membership.role.code == "tenant" and membership.organization_id == request.organization_id:
                    is_tenant_of_org = True
        
        if not is_admin and not is_tenant_of_org:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu işlem için admin veya ilgili organizasyonun tenant yetkisi gerekli"
            )
    
    return await auth_service.assign_role(request)


@router.post(
    "/admin/assign-permissions",
    summary="Yetki Ata (Admin/Tenant)",
    description="""
**Admin veya Tenant rolü için.**

Kullanıcıya belirtilen organizasyonda ek yetkiler atar.
Mevcut rol yetkilerine eklenir.

**Örnek İstek:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "organization_id": "550e8400-e29b-41d4-a716-446655440001",
  "permissions": ["device:control", "telemetry:write"]
}
```
    """,
    responses={
        200: {"description": "Yetkiler atandı"},
        403: {"description": "Yetkisiz"},
        404: {"description": "Kullanıcı veya organizasyon bulunamadı"},
    },
)
async def assign_permissions(
    request: AssignPermissionsRequest,
    auth_service: AuthServiceDep,
    current_user: CurrentUser = None,
) -> dict:
    """Kullanıcıya yetki ata."""
    # Yetki kontrolü
    if current_user:
        is_admin = current_user.is_superuser
        is_tenant_of_org = False
        
        for membership in current_user.organization_memberships:
            if membership.role:
                if membership.role.code == "admin":
                    is_admin = True
                if membership.role.code == "tenant" and membership.organization_id == request.organization_id:
                    is_tenant_of_org = True
        
        if not is_admin and not is_tenant_of_org:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu işlem için admin veya ilgili organizasyonun tenant yetkisi gerekli"
            )
    
    return await auth_service.assign_permissions(request)


# ============================================================
# GET /api/v1/auth/modules - Mevcut Modüller
# ============================================================

@router.get(
    "/modules",
    response_model=AvailableModulesResponse,
    summary="Mevcut Modülleri Listele",
    description="""
Sistemdeki tüm modülleri ve permission'larını listeler.

**Modüller:**
- `core` - Temel özellikler (auth, org, user)
- `asset_management` - Asset ve Zone yönetimi
- `iot` - Gateway ve cihaz yönetimi
- `telemetry` - Telemetri verileri
- `energy` - EPİAŞ, Recommendation, Core Loop
- `rewards` - AWX puan sistemi, Ledger
- `billing` - Cüzdan ve işlemler
- `compliance` - KVKK/GDPR, Audit logs
- `notifications` - Push, Telegram, Email
- `dashboard` - Analitik ve raporlar
    """,
)
async def get_available_modules(
    auth_service: AuthServiceDep,
) -> AvailableModulesResponse:
    """Sistemdeki tüm modülleri döner."""
    return auth_service.get_available_modules()


# ============================================================
# Users Router - PATCH /api/v1/users/me/onboarding - Kullanıcı Onboarding
# ============================================================

@users_router.patch(
    "/me/onboarding",
    response_model=OnboardingResponse,
    summary="Kullanıcı Onboarding",
    description="""
Kullanıcı onboarding bilgilerini tamamlar.
Auth0 sync sonrası kullanıcı bu bilgileri doldurur.

**Bilgiler:**
- Kişisel: first_name, last_name, phone
- Telegram: telegram_username
- Adres: country, city, district, address, postal_code
- Bildirim ayarları: push, email, telegram, sms
- KVKK onayları: location, device_control, notifications, data_processing, marketing
- FCM token: Firebase push notification token

**Örnek İstek:**
```json
{
  "first_name": "Ahmet",
  "last_name": "Yılmaz",
  "phone": "+905551112233",
  "telegram_username": "ahmetyilmaz",
  "address": {
    "country": "Türkiye",
    "city": "İstanbul",
    "district": "Kadıköy"
  },
  "notification_settings": {
    "push_enabled": true,
    "telegram_enabled": true
  },
  "consent_settings": {
    "location": true,
    "device_control": true,
    "data_processing": true
  }
}
```
    """,
)
async def complete_onboarding(
    request: OnboardingRequest,
    current_user: CurrentActiveUser,
    auth_service: AuthServiceDep,
) -> OnboardingResponse:
    """Kullanıcı onboarding bilgilerini tamamla."""
    return await auth_service.complete_onboarding(current_user, request)


# ============================================================
# Admin Router - Resource-based Organization Management
# ============================================================

@admin_router.post(
    "/organizations",
    response_model=CreateOrganizationStep1Response,
    summary="Organizasyon Oluştur",
    description="""
**Sadece Admin rolü için.**

Yeni bir organizasyon (tenant) oluşturur.

**Sonraki adımlar:**
1. `POST /admin/organizations/{org_id}/modules` - Modül ata
2. `POST /admin/organizations/{org_id}/invites` - Kullanıcı davet et

**Örnek İstek:**
```json
{
  "name": "Acme Corp",
  "slug": "acme-corp",
  "description": "Acme Corporation",
  "email": "info@acme.com",
  "phone": "+905551112233"
}
```
    """,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(["admin"]))],
)
async def create_organization(
    request: CreateOrganizationStep1Request,
    auth_service: AuthServiceDep,
) -> CreateOrganizationStep1Response:
    """Yeni organizasyon oluştur."""
    return await auth_service.create_organization_step1(request)


@admin_router.post(
    "/organizations/{org_id}/modules",
    response_model=CreateOrganizationStep2Response,
    summary="Organizasyona Modül Ata",
    description="""
**Sadece Admin rolü için.**

Organizasyona hangi modüllerin aktif olacağını belirler.

**Not:** `core` modülü her zaman otomatik eklenir.

**Modüller:**
- `asset_management` - Asset ve Zone yönetimi
- `iot` - Gateway ve cihaz yönetimi
- `telemetry` - Telemetri verileri
- `energy` - EPİAŞ, Recommendation, Core Loop
- `rewards` - AWX puan sistemi
- `billing` - Cüzdan ve işlemler
- `compliance` - KVKK/GDPR
- `notifications` - Push, Telegram, Email
- `dashboard` - Analitik ve raporlar

**Örnek İstek:**
```json
{
  "modules": ["asset_management", "iot", "telemetry", "energy", "rewards"]
}
```
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def assign_organization_modules(
    org_id: str,
    request: CreateOrganizationStep2Request,
    auth_service: AuthServiceDep,
) -> CreateOrganizationStep2Response:
    """Organizasyona modül ata."""
    # org_id'yi request'e ekle
    request.organization_id = org_id
    return await auth_service.create_organization_step2(request)


@admin_router.post(
    "/organizations/{org_id}/invites",
    response_model=AddUserToOrganizationResponse,
    summary="Organizasyona Kullanıcı Davet Et",
    description="""
**Sadece Admin rolü için.**

Organizasyona kullanıcı davet eder.
Kullanıcı mail ile davet edilir ve Auth0 ile giriş yaptığında otomatik eklenir.

**Roller:**
- `tenant` - Organizasyon yöneticisi
- `user` - Normal kullanıcı

**Örnek İstek:**
```json
{
  "email": "user@acme.com",
  "full_name": "Mehmet Demir",
  "role": "tenant"
}
```
    """,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(["admin"]))],
)
async def invite_user_to_organization(
    org_id: str,
    request: AddUserToOrganizationRequest,
    auth_service: AuthServiceDep,
) -> AddUserToOrganizationResponse:
    """Organizasyona kullanıcı davet et."""
    # org_id'yi request'e ekle
    request.organization_id = org_id
    return await auth_service.add_user_to_organization(request)


# ============================================================
# Admin Router - GET Endpoints (Listeleme)
# ============================================================

@admin_router.get(
    "/organizations",
    response_model=AdminOrganizationListResponse,
    summary="Tüm Organizasyonları Listele",
    description="""
**Sadece Admin rolü için.**

Sistemdeki tüm organizasyonları listeler.

**Query Parametreleri:**
- `page` - Sayfa numarası (varsayılan: 1)
- `page_size` - Sayfa başına kayıt (varsayılan: 20, max: 100)
- `search` - İsim veya slug'da arama
- `is_active` - Aktif/pasif filtresi

**Dönen Bilgiler:**
- Organizasyon ID, isim, slug
- Kullanıcı sayısı
- Cihaz sayısı
- Aktif modüller
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_all_organizations(
    auth_service: AuthServiceDep,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    is_active: bool | None = None,
) -> AdminOrganizationListResponse:
    """Tüm organizasyonları listele."""
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
**Sadece Admin rolü için.**

Bir organizasyonun detaylı bilgilerini döner.

**Dönen Bilgiler:**
- Organizasyon bilgileri
- Kullanıcı listesi (rol bilgisiyle)
- Aktif modüller
- Cihaz, gateway, asset sayıları
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def get_organization_detail(
    org_id: str,
    auth_service: AuthServiceDep,
) -> AdminOrganizationDetailResponse:
    """Organizasyon detayını getir."""
    return await auth_service.get_organization_detail(org_id)


@admin_router.get(
    "/users",
    response_model=AdminUserListResponse,
    summary="Tüm Kullanıcıları Listele",
    description="""
**Sadece Admin rolü için.**

Platformdaki tüm kullanıcıları listeler.

**Query Parametreleri:**
- `page` - Sayfa numarası (varsayılan: 1)
- `page_size` - Sayfa başına kayıt (varsayılan: 20, max: 100)
- `search` - Email veya isimde arama
- `role` - Rol filtresi (admin, tenant, user, device)
- `organization_id` - Organizasyon filtresi
- `is_active` - Aktif/pasif filtresi
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_all_users(
    auth_service: AuthServiceDep,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    role: str | None = None,
    organization_id: str | None = None,
    is_active: bool | None = None,
) -> AdminUserListResponse:
    """Tüm kullanıcıları listele."""
    return await auth_service.list_all_users(
        page=page,
        page_size=page_size,
        search=search,
        role=role,
        organization_id=organization_id,
        is_active=is_active,
    )


@admin_router.get(
    "/roles",
    response_model=AdminRoleListResponse,
    summary="Tüm Rolleri Listele",
    description="""
**Sadece Admin rolü için.**

Sistemdeki tüm rolleri listeler.

**Roller:**
- `admin` - Sistem yöneticisi (tüm yetkiler)
- `tenant` - Organizasyon yöneticisi
- `user` - Normal kullanıcı (salt okunur)
- `device` - Cihaz/Telemetri erişimi
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_all_roles(
    auth_service: AuthServiceDep,
) -> AdminRoleListResponse:
    """Tüm rolleri listele."""
    return await auth_service.list_all_roles()


@admin_router.get(
    "/permissions",
    response_model=AdminPermissionListResponse,
    summary="Tüm Yetkileri Listele",
    description="""
**Sadece Admin rolü için.**

Sistemdeki tüm yetkileri (permissions) listeler.

**Yetki Formatı:** `resource:action`
Örnek: `device:read`, `user:create`, `billing:manage`
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_all_permissions(
    auth_service: AuthServiceDep,
) -> AdminPermissionListResponse:
    """Tüm yetkileri listele."""
    return await auth_service.list_all_permissions()


# ============================================================
# Admin Router - User Management
# ============================================================

@admin_router.post(
    "/users/{user_id}/assign-role",
    response_model=AssignRoleToUserResponse,
    summary="Kullanıcıya Rol Ata",
    description="""
**Sadece Admin rolü için.**

Bir kullanıcıya belirli bir organizasyonda rol atar.

**Roller:**
- `admin` - Sistem yöneticisi
- `tenant` - Organizasyon yöneticisi
- `user` - Normal kullanıcı
- `device` - Cihaz erişimi

**Örnek İstek:**
```json
{
  "role_code": "tenant",
  "organization_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Not:** `organization_id` boş bırakılırsa kullanıcının varsayılan organizasyonunda rol atanır.
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


@admin_router.post(
    "/organizations/{org_id}/users",
    response_model=AddUserToOrgDirectResponse,
    summary="Organizasyona Kullanıcı Ekle",
    description="""
**Sadece Admin rolü için.**

Bir organizasyona doğrudan kullanıcı ekler (davet olmadan).

**Kullanım Senaryoları:**
- Mevcut kullanıcıyı başka organizasyona transfer et
- Yeni kullanıcı oluşturup organizasyona ekle

**Örnek İstek (Mevcut Kullanıcı):**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "role_code": "user"
}
```

**Örnek İstek (Yeni Kullanıcı):**
```json
{
  "email": "newuser@example.com",
  "full_name": "Yeni Kullanıcı",
  "role_code": "tenant"
}
```
    """,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(["admin"]))],
)
async def add_user_to_organization_direct(
    org_id: str,
    request: AddUserToOrgDirectRequest,
    auth_service: AuthServiceDep,
) -> AddUserToOrgDirectResponse:
    """Organizasyona doğrudan kullanıcı ekle."""
    return await auth_service.add_user_to_organization_direct(org_id, request)
