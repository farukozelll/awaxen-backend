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
    """JWT Token payload."""
    sub: str
    exp: datetime
    iat: datetime
    org_id: uuid.UUID | None = None


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
    İlk girişte kullanıcı, organizasyon ve cüzdan oluşturulur.
    
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
        description="Auth0'dan gelen rol kodu (super_admin, admin, operator, viewer, farmer)",
        examples=["admin"],
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
    code: str = Field(..., examples=["admin"])
    name: str = Field(..., examples=["Admin"])


class MeResponse(BaseModel):
    """
    Token'daki kullanıcının profil bilgisi.
    GET /api/auth/me yanıtı.
    """
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    auth0_id: str | None = Field(None, examples=["google-oauth2|123456789"])
    email: EmailStr
    full_name: str | None = Field(None, examples=["Ahmet Yılmaz"])
    phone: str | None = Field(None, alias="phone_number")
    telegram_username: str | None = None
    role: RoleInfo | None = None
    permissions: list[str] = Field(default_factory=list, examples=[["can_view_devices", "can_edit_devices"]])
    organization: OrganizationResponse | None = None
    is_active: bool = True
    created_at: datetime | None = None


# Forward references
UserWithOrganizations.model_rebuild()
OrganizationWithMembers.model_rebuild()
Auth0SyncResponse.model_rebuild()
ProfileUpdateResponse.model_rebuild()
