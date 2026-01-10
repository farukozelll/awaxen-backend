"""
Auth Module - Pydantic Schemas (DTOs)
NEVER expose SQLAlchemy models directly in API responses.
Always map them to Pydantic Schemas using model_validate.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ============== Token Schemas ==============

class Token(BaseModel):
    """JWT Token response."""
    access_token: str
    token_type: str = "bearer"


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
    email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None


class OrganizationCreate(OrganizationBase):
    """Schema for creating an organization."""
    pass


class OrganizationUpdate(BaseModel):
    """Schema for updating an organization."""
    name: str | None = Field(None, min_length=2, max_length=255)
    description: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None
    is_active: bool | None = None


class OrganizationResponse(OrganizationBase):
    """Organization response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    is_active: bool
    created_at: datetime


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
    
    auth0_id ve email body'den veya header'dan gönderilebilir.
    """
    auth0_id: str | None = Field(
        None, 
        description="Auth0 kullanıcı ID'si (body veya X-Auth0-Id header)", 
        examples=["google-oauth2|123456789"]
    )
    email: EmailStr | None = Field(
        None, 
        description="Kullanıcı email adresi (body veya X-Auth0-Email header)"
    )
    name: str | None = Field(
        None, 
        description="Kullanıcı tam adı", 
        examples=["Ahmet Yılmaz"]
    )
    role: str | None = Field(
        None,
        description="Auth0'dan gelen rol kodu (admin, tenant, user, device)",
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


# ============== Admin Schemas ==============

class CreateOrganizationWithUserRequest(BaseModel):
    """
    Admin tarafından organizasyon ve kullanıcı birlikte oluşturma.
    Organizasyon oluşturulur ve belirtilen kullanıcı tenant rolüyle eklenir.
    """
    # Organizasyon bilgileri
    organization_name: str = Field(..., min_length=2, max_length=255, examples=["Acme Corp"])
    organization_slug: str | None = Field(
        None, 
        min_length=2, 
        max_length=100,
        pattern=r"^[a-z0-9-]+$",
        description="Otomatik oluşturulur eğer belirtilmezse",
        examples=["acme-corp"]
    )
    organization_description: str | None = Field(None, examples=["Acme Corporation"])
    organization_email: EmailStr | None = Field(None, examples=["info@acme.com"])
    organization_phone: str | None = Field(None, examples=["+905551112233"])
    organization_address: str | None = Field(None, examples=["Istanbul, Turkey"])
    
    # Kullanıcı bilgileri
    user_email: EmailStr = Field(..., examples=["admin@acme.com"])
    user_full_name: str | None = Field(None, examples=["Ahmet Yılmaz"])
    user_phone: str | None = Field(None, examples=["+905551112233"])
    user_role: str = Field(
        default="tenant",
        description="Kullanıcının rolü (tenant, user, device)",
        examples=["tenant"]
    )
    user_permissions: list[str] | None = Field(
        None,
        description="Ek yetkiler (rol yetkilerine eklenir)",
        examples=[["billing:manage"]]
    )


class CreateOrganizationWithUserResponse(BaseModel):
    """Organizasyon ve kullanıcı oluşturma yanıtı."""
    message: str
    organization: OrganizationResponse
    user: UserResponse
    role: RoleResponse


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
    role: str = Field(default="tenant", examples=["tenant", "user"])


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


class AddUserToOrgDirectRequest(BaseModel):
    """Organizasyona doğrudan kullanıcı ekleme isteği."""
    user_id: uuid.UUID | None = Field(None, description="Mevcut kullanıcı ID (opsiyonel)")
    email: EmailStr = Field(..., description="Kullanıcı email")
    full_name: str | None = None
    role_code: str = Field(default="user", examples=["tenant", "user"])


class AddUserToOrgDirectResponse(BaseModel):
    """Organizasyona doğrudan kullanıcı ekleme yanıtı."""
    message: str
    user: AdminUserListItem
    organization_id: uuid.UUID
    role: str


# Forward references
UserWithOrganizations.model_rebuild()
OrganizationWithMembers.model_rebuild()
Auth0SyncResponse.model_rebuild()
ProfileUpdateResponse.model_rebuild()
AdminOrganizationDetailResponse.model_rebuild()
