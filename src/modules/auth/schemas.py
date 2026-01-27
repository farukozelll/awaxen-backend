"""
Auth Module - Pydantic Schemas (DTOs)
NEVER expose SQLAlchemy models directly in API responses.
Always map them to Pydantic Schemas using model_validate.
"""
import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ============== Enums ==============

class OrganizationType(str, Enum):
    """Organizasyon/Tesis tipi."""
    VILLA = "villa"
    HOUSE = "house"
    APARTMENT = "apartment"
    STUDIO = "studio"
    FLAT_1_1 = "flat_1_1"
    FLAT_2_1 = "flat_2_1"
    FLAT_3_1 = "flat_3_1"
    FLAT_4_1 = "flat_4_1"
    OFFICE = "office"
    FACTORY = "factory"
    WAREHOUSE = "warehouse"
    FARM = "farm"
    GREENHOUSE = "greenhouse"
    SHOP = "shop"
    HOTEL = "hotel"
    HOSPITAL = "hospital"
    SCHOOL = "school"
    OTHER = "other"


# ============== Token Schemas ==============

class Token(BaseModel):
    """JWT Token response."""
    access_token: str
    token_type: str = "bearer"  # noqa: S105


class TokenPayload(BaseModel):
    """JWT Token payload - rol ve permission bilgilerini içerir."""
    sub: str
    exp: datetime
    iat: datetime
    org_id: uuid.UUID | None = None
    role: str | None = None  # admin, tenant, user, device
    permissions: list[str] = []


# ============== User Schemas ==============

class UserBase(BaseModel):
    """Base user schema."""
    email: EmailStr
    full_name: str | None = None
    phone: str | None = None


class UserCreate(UserBase):
    """Schema for creating a user."""
    password: str = Field(..., min_length=8, max_length=100)


class UserUpdate(BaseModel):
    """Schema for updating a user."""
    email: EmailStr | None = None
    full_name: str | None = None
    phone: str | None = None
    password: str | None = Field(None, min_length=8, max_length=100)
    is_active: bool | None = None


class UserResponse(UserBase):
    """User response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login: datetime | None = None


class UserWithOrganizations(UserResponse):
    """User with organization memberships."""
    organizations: list["OrganizationMembershipResponse"] = []


# ============== Organization Schemas ==============

class OrganizationBase(BaseModel):
    """Base organization schema."""
    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=100)
    description: str | None = None
    organization_type: OrganizationType | None = None
    company_size: int | None = None
    email: EmailStr | None = None
    phone: str | None = None
    # Detaylı adres
    city: str | None = None
    district: str | None = None
    neighborhood: str | None = None
    street: str | None = None
    postal_code: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    address: str | None = None  # Legacy


class OrganizationCreate(OrganizationBase):
    """Schema for creating an organization."""
    pass


class OrganizationUpdate(BaseModel):
    """Schema for updating an organization."""
    name: str | None = Field(None, min_length=2, max_length=255)
    description: str | None = None
    organization_type: OrganizationType | None = None
    company_size: int | None = None
    email: EmailStr | None = None
    phone: str | None = None
    city: str | None = None
    district: str | None = None
    neighborhood: str | None = None
    street: str | None = None
    postal_code: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    address: str | None = None
    is_active: bool | None = None


class OrganizationWalletSummary(BaseModel):
    """Organizasyonun wallet özeti."""
    wallet_count: int = Field(default=0, description="Wallet sayısı")
    balances: dict[str, str] = Field(default_factory=dict, description="Para birimi bazında bakiyeler")
    total_balance_try: str = Field(default="0.00", description="Toplam TRY bakiyesi")


class OrganizationResponse(OrganizationBase):
    """Organization response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    is_active: bool
    created_at: datetime


class OrganizationDetailResponse(OrganizationResponse):
    """Organization detail with wallet summary."""
    wallet_summary: OrganizationWalletSummary | None = Field(
        None,
        description="Organizasyonun wallet özeti (COMPANY wallets)"
    )


class OrganizationWithMembers(OrganizationResponse):
    """Organization with member list."""
    members: list["OrganizationMemberResponse"] = []


# ============== Role Schemas ==============

class RoleBase(BaseModel):
    """Base role schema."""
    name: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-z_]+$")
    description: str | None = None
    permissions: list[str] = []


class RoleCreate(RoleBase):
    """Schema for creating a role."""
    pass


class RoleUpdate(BaseModel):
    """Schema for updating a role."""
    name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = None
    permissions: list[str] | None = None


class RoleResponse(RoleBase):
    """Role response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    is_system: bool
    created_at: datetime


# ============== Membership Schemas ==============

class OrganizationMembershipResponse(BaseModel):
    """User's membership in an organization."""
    model_config = ConfigDict(from_attributes=True)
    
    organization_id: uuid.UUID
    organization_name: str
    role: RoleResponse | None = None
    is_default: bool
    joined_at: datetime


class OrganizationMemberResponse(BaseModel):
    """Member of an organization."""
    model_config = ConfigDict(from_attributes=True)
    
    user_id: uuid.UUID
    user_email: str
    user_full_name: str | None = None
    role: RoleResponse | None = None
    joined_at: datetime


class AddMemberRequest(BaseModel):
    """Request to add a member to an organization."""
    user_id: uuid.UUID
    role_id: uuid.UUID | None = None


class UpdateMemberRoleRequest(BaseModel):
    """Request to update a member's role."""
    role_id: uuid.UUID | None = None


# ============== Auth Schemas ==============

class LoginRequest(BaseModel):
    """Login request schema."""
    email: EmailStr
    password: str


class RegisterRequest(UserCreate):
    """Registration request schema."""
    organization_name: str | None = Field(
        None,
        min_length=2,
        max_length=255,
        description="Optional: Create an organization during registration",
    )


class ChangePasswordRequest(BaseModel):
    """Change password request."""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)


# ============== Auth0 Sync Schemas ==============

class Auth0SyncRequest(BaseModel):
    """
    Auth0 kullanıcısını Postgres ile senkronize et.
    İlk girişte kullanıcı ve organizasyon oluşturulur.
    
    NOT: Role bilgisi frontend'den gönderilmemeli (güvenlik riski - spoofing).
    Backend, Auth0 token'ından veya DB'den role belirler.
    """
    auth0_id: str | None = Field(
        None, 
        description="Auth0 kullanıcı ID'si", 
        examples=["google-oauth2|123456789"]
    )
    email: EmailStr | None = Field(
        None, 
        description="Kullanıcı email adresi"
    )
    name: str | None = Field(
        None, 
        description="Kullanıcı tam adı", 
        examples=["Ahmet Yılmaz"]
    )
    email_verified: bool = Field(
        default=False,
        description="Auth0'dan gelen email doğrulama durumu",
    )
    role: str | None = Field(
        None,
        description="Auth0 token'dan gelen rol (backend-to-backend için, frontend gönderemez)",
        examples=["tenant"],
    )


class Auth0SyncResponse(BaseModel):
    """Auth0 sync response."""
    status: str = Field(..., examples=["synced", "created"])
    message: str
    user: "MeResponse"
    organization: OrganizationResponse | None = None


class ProfileUpdateRequest(BaseModel):
    """Kullanıcı profil güncelleme isteği."""
    full_name: str | None = Field(None, examples=["Faruk Özel"])
    phone_number: str | None = Field(None, examples=["+905551112233"])
    telegram_username: str | None = Field(None, examples=["farukozel"])


class ProfileUpdateResponse(BaseModel):
    """Profil güncelleme yanıtı."""
    message: str
    user: "MeResponse"


class RoleInfo(BaseModel):
    """Rol bilgisi."""
    code: str = Field(..., examples=["tenant"])
    name: str = Field(..., examples=["Tenant"])


class MeResponse(BaseModel):
    """
    Token'daki kullanıcının profil bilgisi.
    GET /api/auth/me yanıtı.
    
    Frontend bu bilgileri kullanarak:
    - Sidebar'da modülleri gösterir
    - Onboarding tamamlanmadıysa wizard'a yönlendirir
    - Permissions'a göre UI elementlerini gösterir/gizler
    - Wallet bakiyesini header'da gösterir
    """
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    auth0_id: str | None = Field(None, examples=["google-oauth2|123456789"])
    email: EmailStr
    full_name: str | None = Field(None, examples=["Ahmet Yılmaz"])
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = Field(None, alias="phone_number")
    telegram_username: str | None = None
    
    # Rol ve yetkiler
    role: RoleInfo | None = None
    permissions: list[str] = Field(default_factory=list, examples=[["asset:read", "device:read", "telemetry:read"]])
    
    # Organizasyon ve modüller
    organization: OrganizationResponse | None = None
    modules: list[str] = Field(
        default_factory=list, 
        description="Organizasyonun aktif modülleri - sidebar'da gösterilecek",
        examples=[["core", "asset_management", "iot", "energy"]]
    )
    
    # Wallet bilgisi (AWX Puan)
    wallet: "UserWalletInfo | None" = Field(
        None,
        description="Kullanıcının AWX puan cüzdanı"
    )
    
    # Onboarding durumu
    onboarding_completed: bool = Field(
        default=False,
        description="Onboarding tamamlandı mı? False ise wizard'a yönlendir"
    )
    onboarding_step: int | None = Field(
        None,
        description="Mevcut onboarding adımı"
    )
    
    is_active: bool = True
    created_at: datetime | None = None


class UserWalletInfo(BaseModel):
    """Kullanıcının AWX wallet özeti."""
    balance: str = Field(default="0.00", description="AWX bakiyesi")
    currency: str = Field(default="AWX", description="Para birimi")
    has_wallet: bool = Field(default=False, description="Wallet var mı?")


# ============== Admin Schemas ==============

class CreateOrganizationWithUserRequest(BaseModel):
    """
    Organizasyon, kullanıcı ve modülleri tek seferde oluşturma (Atomic Transaction).
    
    Akış:
    1. Organizasyon oluşturulur
    2. Modüller atanır
    3. Kullanıcı oluşturulur (hayalet - Auth0 kaydı yok)
    4. Davetiye oluşturulur ve hoşgeldin maili gönderilir
    5. In-app bildirim oluşturulur
    """
    # ===== Organizasyon bilgileri =====
    organization_name: str = Field(..., min_length=2, max_length=255, examples=["Acme Corp"])
    organization_slug: str | None = Field(
        None, 
        min_length=2, 
        max_length=100,
        pattern=r"^[a-z0-9-]+$",
        description="Otomatik oluşturulur eğer belirtilmezse",
        examples=["acme-corp"]
    )
    organization_type: OrganizationType | None = Field(
        None,
        description="Tesis tipi (villa, apartment, factory, vb.)",
        examples=["villa"]
    )
    company_size: int | None = Field(
        None,
        ge=0,
        description="Çalışan sayısı veya m2 büyüklüğü",
        examples=[100]
    )
    organization_description: str | None = Field(None, examples=["Acme Corporation"])
    organization_email: EmailStr | None = Field(None, examples=["info@acme.com"])
    organization_phone: str | None = Field(None, examples=["+905551112233"])
    
    # ===== Detaylı adres (hava durumu için gerekli) =====
    city: str | None = Field(None, description="Şehir", examples=["İstanbul"])
    district: str | None = Field(None, description="İlçe", examples=["Kadıköy"])
    neighborhood: str | None = Field(None, description="Mahalle", examples=["Caferağa"])
    street: str | None = Field(None, description="Sokak/Cadde ve kapı no", examples=["Moda Cad. No:15"])
    postal_code: str | None = Field(None, description="Posta kodu", examples=["34710"])
    country: str = Field(default="Türkiye", description="Ülke", examples=["Türkiye"])
    
    # ===== Koordinatlar (hava durumu API için) =====
    latitude: float | None = Field(None, description="Enlem", examples=[40.9833])
    longitude: float | None = Field(None, description="Boylam", examples=[29.0333])
    
    # ===== Modüller (Atomic - tek seferde) =====
    modules: list[str] = Field(
        default_factory=lambda: ["core", "asset_management", "iot", "telemetry", "dashboard", "notifications"],
        description="Aktif edilecek modül kodları",
        examples=[["core", "iot", "energy", "billing", "telemetry", "dashboard"]]
    )
    
    # ===== İlk kullanıcı (Tenant) bilgileri =====
    user_first_name: str = Field(..., min_length=1, max_length=100, examples=["Ahmet"])
    user_last_name: str = Field(..., min_length=1, max_length=100, examples=["Yılmaz"])
    user_email: EmailStr = Field(..., examples=["admin@acme.com"])
    user_phone: str | None = Field(None, examples=["+905551112233"])
    user_role: str = Field(
        default="tenant",
        description="Kullanıcının rolü (varsayılan: tenant)",
        examples=["tenant"]
    )
    
    # ===== Bildirim ayarları =====
    send_welcome_email: bool = Field(
        default=True,
        description="Kullanıcıya hoşgeldin maili gönderilsin mi?"
    )


class OrganizationModulesUpdate(BaseModel):
    """
    Tab 2: Organizasyon modüllerini güncelle.
    Tab 1'den dönen organization_id ile çağrılır.
    """
    modules: list[str] = Field(
        ...,
        description="Aktif edilecek modül kodları",
        examples=[["core", "iot", "energy", "billing"]]
    )


class CreateOrganizationWithUserResponse(BaseModel):
    """Organizasyon ve kullanıcı oluşturma yanıtı."""
    message: str
    organization: OrganizationResponse
    user: UserResponse
    role: RoleResponse
    modules: list[str] = Field(default_factory=list, description="Atanan modüller")
    invitation_sent: bool = Field(default=False, description="Davetiye maili gönderildi mi?")


class AssignRoleRequest(BaseModel):
    """Kullanıcıya rol atama isteği."""
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role_code: str = Field(..., examples=["tenant"])
    additional_permissions: list[str] | None = Field(
        None,
        description="Rol yetkilerine ek yetkiler",
        examples=[["billing:manage"]]
    )


class AssignPermissionsRequest(BaseModel):
    """Kullanıcıya yetki atama isteği."""
    user_id: uuid.UUID
    organization_id: uuid.UUID
    permissions: list[str] = Field(..., examples=[["device:control", "telemetry:write"]])


class AvailablePermissionsResponse(BaseModel):
    """Sistemdeki tüm yetkiler."""
    permissions: list[dict] = Field(
        ...,
        examples=[[
            {"code": "asset:read", "description": "Asset görüntüleme"},
            {"code": "device:control", "description": "Cihaz kontrolü"}
        ]]
    )


class AvailableRolesResponse(BaseModel):
    """Sistemdeki tüm roller."""
    roles: list[dict] = Field(
        ...,
        examples=[[
            {"code": "admin", "name": "Admin", "description": "Sistem yöneticisi"},
            {"code": "tenant", "name": "Tenant", "description": "Organizasyon yöneticisi"}
        ]]
    )


# ============== Module Schemas ==============

class ModuleInfo(BaseModel):
    """Modül bilgisi."""
    code: str = Field(..., examples=["iot"])
    name: str = Field(..., examples=["IoT"])
    description: str | None = Field(None, examples=["Gateway ve cihaz yönetimi"])
    permissions: list[str] = Field(default_factory=list)


class AvailableModulesResponse(BaseModel):
    """Sistemdeki tüm modüller."""
    modules: list[ModuleInfo]


class AssignModulesRequest(BaseModel):
    """Organizasyona modül atama isteği."""
    organization_id: uuid.UUID
    modules: list[str] = Field(
        ..., 
        description="Atanacak modül kodları",
        examples=[["core", "asset_management", "iot", "energy"]]
    )


class OrganizationModuleResponse(BaseModel):
    """Organizasyona atanmış modül."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    module_code: str
    is_active: bool
    activated_at: datetime


class OrganizationWithModulesResponse(BaseModel):
    """Organizasyon ve modülleri."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    name: str
    slug: str
    modules: list[OrganizationModuleResponse] = Field(default_factory=list)


# ============== Onboarding Schemas ==============

class NotificationSettings(BaseModel):
    """Bildirim ayarları."""
    push_enabled: bool = True
    email_enabled: bool = True
    telegram_enabled: bool = False
    sms_enabled: bool = False


class ConsentSettings(BaseModel):
    """KVKK/GDPR onay ayarları."""
    location: bool = False
    device_control: bool = False
    notifications: bool = True
    data_processing: bool = True
    marketing: bool = False


class AddressInfo(BaseModel):
    """Adres bilgileri."""
    country: str | None = Field(None, examples=["Türkiye"])
    city: str | None = Field(None, examples=["İstanbul"])
    district: str | None = Field(None, examples=["Kadıköy"])
    address: str | None = Field(None, examples=["Caferağa Mah. Moda Cad. No:1"])
    postal_code: str | None = Field(None, examples=["34710"])


class OnboardingRequest(BaseModel):
    """
    Kullanıcı onboarding bilgileri.
    Auth0 sync sonrası kullanıcı bu bilgileri doldurur.
    """
    # Kişisel bilgiler
    first_name: str | None = Field(None, min_length=2, max_length=100, examples=["Ahmet"])
    last_name: str | None = Field(None, min_length=2, max_length=100, examples=["Yılmaz"])
    phone: str | None = Field(None, examples=["+905551112233"])
    
    # Telegram
    telegram_username: str | None = Field(None, examples=["ahmetyilmaz"])
    
    # Adres
    address: AddressInfo | None = None
    
    # Bildirim ayarları
    notification_settings: NotificationSettings | None = None
    
    # KVKK onayları
    consent_settings: ConsentSettings | None = None
    
    # Firebase Push Token
    fcm_token: str | None = Field(None, max_length=500)


class OnboardingResponse(BaseModel):
    """Onboarding yanıtı."""
    message: str
    onboarding_completed: bool
    onboarding_step: int | None
    user: MeResponse


# ============== Admin Organization Creation Flow ==============

class CreateOrganizationStep1Request(BaseModel):
    """
    Step 1: Organizasyon oluştur.
    Admin UI'dan organizasyon bilgilerini girer.
    """
    name: str = Field(..., min_length=2, max_length=255, examples=["Acme Corp"])
    slug: str | None = Field(
        None,
        min_length=2,
        max_length=100,
        pattern=r"^[a-z0-9-]+$",
        examples=["acme-corp"]
    )
    description: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None


class CreateOrganizationStep1Response(BaseModel):
    """Step 1 yanıtı - Organizasyon oluşturuldu."""
    message: str
    organization: OrganizationResponse


class CreateOrganizationStep2Request(BaseModel):
    """
    Step 2: Organizasyona modül ata.
    Admin organizasyona hangi modüllerin aktif olacağını seçer.
    """
    organization_id: uuid.UUID
    modules: list[str] = Field(
        ...,
        description="Atanacak modül kodları",
        examples=[["core", "asset_management", "iot", "telemetry", "energy", "rewards"]]
    )


class CreateOrganizationStep2Response(BaseModel):
    """Step 2 yanıtı - Modüller atandı."""
    message: str
    organization: OrganizationWithModulesResponse


class AddUserToOrganizationRequest(BaseModel):
    """
    Organizasyona kullanıcı ekle.
    Admin birden fazla kullanıcı ekleyebilir.
    """
    organization_id: uuid.UUID
    email: EmailStr
    full_name: str | None = None
    phone: str | None = None
    role_code: str = Field(default="user", examples=["tenant", "user"])


class AddUserToOrganizationResponse(BaseModel):
    """Kullanıcı ekleme yanıtı."""
    message: str
    user: UserResponse
    organization: OrganizationResponse
    role: str


# ============== Admin List Schemas ==============

class AdminOrganizationListItem(BaseModel):
    """Admin için organizasyon listesi item'ı."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    name: str
    slug: str
    email: EmailStr | None = None
    is_active: bool
    created_at: datetime
    user_count: int = 0
    device_count: int = 0
    modules: list[str] = []


class AdminOrganizationListResponse(BaseModel):
    """Admin için organizasyon listesi yanıtı."""
    organizations: list[AdminOrganizationListItem]
    total: int
    page: int
    page_size: int


class AdminOrganizationDetailResponse(BaseModel):
    """Admin için organizasyon detay yanıtı."""
    organization: OrganizationResponse
    users: list["AdminUserListItem"] = []
    modules: list[str] = []
    device_count: int = 0
    gateway_count: int = 0
    asset_count: int = 0
    wallet_summary: "OrganizationWalletSummary | None" = None


class AdminUserListItem(BaseModel):
    """Admin için kullanıcı listesi item'ı."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    email: EmailStr
    full_name: str | None = None
    phone: str | None = None
    is_active: bool
    created_at: datetime
    last_login: datetime | None = None
    role: RoleInfo | None = None
    organization: OrganizationResponse | None = None


class AdminUserListResponse(BaseModel):
    """Admin için kullanıcı listesi yanıtı."""
    users: list[AdminUserListItem]
    total: int
    page: int
    page_size: int


class AdminRoleListResponse(BaseModel):
    """Admin için rol listesi yanıtı."""
    roles: list[RoleResponse]
    total: int


class AdminPermissionListResponse(BaseModel):
    """Admin için permission listesi yanıtı."""
    permissions: list[str]
    total: int


class AssignRoleToUserRequest(BaseModel):
    """Kullanıcıya rol atama isteği."""
    role_code: str = Field(..., examples=["admin", "tenant", "user", "device"])
    organization_id: uuid.UUID | None = Field(
        None, 
        description="Hangi organizasyonda rol atanacak. Boş ise varsayılan org."
    )


class AssignRoleToUserResponse(BaseModel):
    """Kullanıcıya rol atama yanıtı."""
    message: str
    user_id: uuid.UUID
    role: RoleInfo
    organization_id: uuid.UUID


# ============== Module Management Schemas ==============

class ModuleUpdateItem(BaseModel):
    """Tek bir modül güncelleme bilgisi."""
    module_code: str = Field(..., examples=["iot"])
    is_active: bool = Field(True, description="Modül aktif mi?")
    trial_ends_at: datetime | None = Field(None, description="Deneme süresi bitiş tarihi")
    settings: dict | None = Field(None, description="Modül ayarları")


class OrganizationModulesUpdateRequest(BaseModel):
    """
    Organizasyon modüllerini güncelleme isteği (PUT).
    Upsell ve Feature Flagging için kullanılır.
    """
    modules: list[ModuleUpdateItem] = Field(
        ...,
        description="Güncellenecek modüller listesi",
        examples=[[
            {"module_code": "iot", "is_active": True},
            {"module_code": "energy", "is_active": True, "trial_ends_at": "2024-02-15T00:00:00Z"},
            {"module_code": "billing", "is_active": False}
        ]]
    )


class OrganizationModulesUpdateResponse(BaseModel):
    """Modül güncelleme yanıtı."""
    message: str
    organization_id: uuid.UUID
    updated_modules: list[OrganizationModuleResponse]
    active_modules: list[str]


# ============== Impersonation Schemas ==============

class ImpersonateUserRequest(BaseModel):
    """Kullanıcı taklit etme isteği (opsiyonel parametreler)."""
    reason: str | None = Field(None, description="Taklit etme nedeni (audit log için)")
    duration_minutes: int = Field(60, ge=5, le=480, description="Token geçerlilik süresi (dakika)")


class ImpersonateUserResponse(BaseModel):
    """Kullanıcı taklit etme yanıtı."""
    message: str
    impersonated_user: UserResponse
    access_token: str
    expires_at: datetime
    admin_user_id: uuid.UUID


# =============================================================================
# INVITATION SCHEMAS
# =============================================================================

class InvitationCreateRequest(BaseModel):
    """
    Kullanıcı davet etme isteği.
    
    Tenant Admin, kendi organizasyonuna kullanıcı davet edebilir.
    Sadece 'user' veya 'device' rolü atayabilir (güvenlik).
    """
    email: EmailStr = Field(..., description="Davet edilecek kullanıcının email adresi")
    role: str = Field(
        "user",
        pattern="^(user|device)$",
        description="Atanacak rol (tenant sadece user/device atayabilir)",
    )
    message: str | None = Field(
        None,
        max_length=500,
        description="Davetiye ile gönderilecek kişisel mesaj",
    )
    expires_hours: int = Field(
        48,
        ge=1,
        le=168,
        description="Davetiye geçerlilik süresi (saat, max 7 gün)",
    )


class InvitationResponse(BaseModel):
    """Davetiye bilgisi."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    email: str
    role_code: str
    organization_id: uuid.UUID
    organization_name: str | None = None
    invited_by_email: str | None = None
    is_used: bool
    expires_at: datetime
    created_at: datetime
    message: str | None = None


class InvitationListResponse(BaseModel):
    """Davetiye listesi."""
    items: list[InvitationResponse]
    total: int


class InvitationValidateResponse(BaseModel):
    """
    Davetiye doğrulama yanıtı.
    
    Frontend, kullanıcı linke tıkladığında bu endpoint'i çağırır.
    Geçerli ise organizasyon bilgisini gösterir.
    """
    valid: bool
    message: str
    organization_name: str | None = None
    organization_slug: str | None = None
    role: str | None = None
    email: str | None = None
    expires_at: datetime | None = None


class InvitationAcceptRequest(BaseModel):
    """
    Davetiye kabul etme isteği.
    
    NOT: Bu endpoint normalde kullanılmaz.
    Davetiye, /auth/sync sırasında otomatik olarak tüketilir.
    Bu endpoint, manuel kabul için (edge case).
    """
    token: str = Field(..., description="Davetiye token'ı")


# Forward references
UserWithOrganizations.model_rebuild()
OrganizationWithMembers.model_rebuild()
Auth0SyncResponse.model_rebuild()
ProfileUpdateResponse.model_rebuild()
AdminOrganizationDetailResponse.model_rebuild()
