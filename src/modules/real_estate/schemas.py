"""
RealEstate Module - Pydantic Schemas (DTOs)
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.modules.real_estate.models import (
    AssetStatus, AssetType, LeaseStatus, ZoneType,
    AssetMembershipRelation, TenancyStatus,
)


# ============== Asset Schemas ==============

class AssetBase(BaseModel):
    """Base asset schema."""
    name: str = Field(..., min_length=1, max_length=255)
    code: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    asset_type: AssetType
    address: str | None = None
    latitude: Decimal | None = Field(None, ge=-90, le=90)
    longitude: Decimal | None = Field(None, ge=-180, le=180)
    area_sqm: Decimal | None = Field(None, ge=0)
    floor_number: int | None = None
    status: AssetStatus = AssetStatus.ACTIVE
    metadata_: dict | None = Field(None, alias="metadata")


class AssetCreate(AssetBase):
    """Schema for creating an asset."""
    parent_id: uuid.UUID | None = None


class AssetUpdate(BaseModel):
    """Schema for updating an asset."""
    name: str | None = Field(None, min_length=1, max_length=255)
    code: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    address: str | None = None
    latitude: Decimal | None = Field(None, ge=-90, le=90)
    longitude: Decimal | None = Field(None, ge=-180, le=180)
    area_sqm: Decimal | None = Field(None, ge=0)
    floor_number: int | None = None
    status: AssetStatus | None = None
    metadata_: dict | None = Field(None, alias="metadata")


class AssetResponse(AssetBase):
    """Asset response schema."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    
    id: uuid.UUID
    organization_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class AssetWithChildren(AssetResponse):
    """Asset with children list."""
    children: list["AssetResponse"] = []


class AssetHierarchy(AssetResponse):
    """Asset with full hierarchy (recursive)."""
    children: list["AssetHierarchy"] = []


class AssetTreeNode(BaseModel):
    """Simplified tree node for hierarchy display."""
    id: uuid.UUID
    name: str
    code: str
    asset_type: AssetType
    status: AssetStatus
    children_count: int = 0
    has_children: bool = False


# ============== Lease Schemas ==============

class LeaseBase(BaseModel):
    """Base lease schema."""
    tenant_name: str = Field(..., min_length=1, max_length=255)
    tenant_email: EmailStr | None = None
    tenant_phone: str | None = None
    tenant_id_number: str | None = None
    contract_number: str | None = None
    start_date: date
    end_date: date
    monthly_rent: Decimal = Field(..., gt=0)
    deposit_amount: Decimal | None = Field(None, ge=0)
    currency: str = Field(default="TRY", max_length=3)
    notes: str | None = None


class LeaseCreate(LeaseBase):
    """Schema for creating a lease."""
    asset_id: uuid.UUID
    status: LeaseStatus = LeaseStatus.DRAFT


class LeaseUpdate(BaseModel):
    """Schema for updating a lease."""
    tenant_name: str | None = Field(None, min_length=1, max_length=255)
    tenant_email: EmailStr | None = None
    tenant_phone: str | None = None
    tenant_id_number: str | None = None
    contract_number: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    monthly_rent: Decimal | None = Field(None, gt=0)
    deposit_amount: Decimal | None = Field(None, ge=0)
    currency: str | None = Field(None, max_length=3)
    status: LeaseStatus | None = None
    notes: str | None = None


class LeaseResponse(LeaseBase):
    """Lease response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    organization_id: uuid.UUID
    asset_id: uuid.UUID
    status: LeaseStatus
    signed_at: datetime | None = None
    terminated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class LeaseWithAsset(LeaseResponse):
    """Lease with asset details."""
    asset: AssetResponse


# ============== Zone Schemas ==============

class ZoneBase(BaseModel):
    """Base zone schema."""
    name: str = Field(..., min_length=1, max_length=100)
    zone_type: str = Field(default=ZoneType.ROOM.value)
    description: str | None = None


class ZoneCreate(ZoneBase):
    """Schema for creating a zone."""
    asset_id: uuid.UUID


class ZoneResponse(ZoneBase):
    """Zone response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    asset_id: uuid.UUID
    created_at: datetime


class ZoneListResponse(BaseModel):
    """List of zones response."""
    zones: list[ZoneResponse]
    total: int


# ============== Asset Membership Schemas ==============

class AssetMembershipCreate(BaseModel):
    """Schema for creating asset membership."""
    asset_id: uuid.UUID
    user_id: uuid.UUID
    relation: str = Field(..., description="owner/tenant/agent/operator_view")
    scopes: list[str] = Field(default_factory=list)


class AssetMembershipResponse(BaseModel):
    """Asset membership response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    asset_id: uuid.UUID
    user_id: uuid.UUID
    relation: str
    scopes: list[str]
    revoked_at: datetime | None
    created_at: datetime
    is_active: bool


# ============== Tenancy Schemas ==============

class TenancyCreate(BaseModel):
    """Schema for creating a tenancy."""
    asset_id: uuid.UUID
    tenant_user_id: uuid.UUID
    start_at: datetime
    handover_mode: str | None = None


class TenancyResponse(BaseModel):
    """Tenancy response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    asset_id: uuid.UUID
    tenant_user_id: uuid.UUID
    start_at: datetime
    end_at: datetime | None
    status: str
    handover_mode: str | None
    created_at: datetime
    is_active: bool


class TenancyListResponse(BaseModel):
    """List of tenancies response."""
    tenancies: list[TenancyResponse]
    total: int


# ============== Handover Schemas ==============

class HandoverTokenCreate(BaseModel):
    """Schema for creating a handover token."""
    asset_id: uuid.UUID
    expires_in_hours: int = Field(default=48, ge=1, le=168)


class HandoverTokenResponse(BaseModel):
    """Handover token response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    asset_id: uuid.UUID
    token: str
    expires_at: datetime
    used_at: datetime | None
    used_by_user_id: uuid.UUID | None
    created_at: datetime
    is_valid: bool


class HandoverClaim(BaseModel):
    """Schema for claiming a handover token."""
    token: str


class TenantInvite(BaseModel):
    """Schema for inviting a tenant."""
    email: EmailStr
    asset_id: uuid.UUID


# Forward references
AssetWithChildren.model_rebuild()
AssetHierarchy.model_rebuild()
