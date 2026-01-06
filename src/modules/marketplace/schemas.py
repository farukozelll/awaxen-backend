"""
Marketplace Module - Pydantic Schemas
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# === Alarm Schemas ===

class AlarmCreate(BaseModel):
    """Schema for creating an alarm."""
    asset_id: UUID
    device_id: UUID | None = None
    severity: str = Field(..., description="low/medium/high/critical")
    message: str
    metadata: dict | None = None


class AlarmResponse(BaseModel):
    """Alarm response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    asset_id: UUID
    device_id: UUID | None
    severity: str
    message: str
    status: str
    metadata: dict | None
    acknowledged_at: datetime | None
    acknowledged_by_user_id: UUID | None
    closed_at: datetime | None
    created_at: datetime


class AlarmListResponse(BaseModel):
    """List of alarms response."""
    alarms: list[AlarmResponse]
    total: int


# === Job Schemas ===

class JobCreate(BaseModel):
    """Schema for creating a job."""
    asset_id: UUID
    alarm_id: UUID | None = None
    category: str = Field(..., description="plumbing/electrical/hvac/appliance/general")
    title: str
    description: str | None = None
    urgency: str = Field(default="normal", description="low/normal/high/urgent")


class JobResponse(BaseModel):
    """Job response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    asset_id: UUID
    created_by_user_id: UUID | None
    alarm_id: UUID | None
    category: str
    title: str
    description: str | None
    urgency: str
    status: str
    assigned_operator_id: UUID | None
    assigned_at: datetime | None
    completed_at: datetime | None
    rating: int | None
    rating_comment: str | None
    created_at: datetime


class JobListResponse(BaseModel):
    """List of jobs response."""
    jobs: list[JobResponse]
    total: int
    page: int
    page_size: int


# === Job Offer Schemas ===

class JobOfferCreate(BaseModel):
    """Schema for creating a job offer."""
    job_id: UUID
    price_estimate: Decimal | None = None
    currency: str = Field(default="TRY")
    eta_minutes: int | None = None
    message: str | None = None


class JobOfferResponse(BaseModel):
    """Job offer response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    job_id: UUID
    operator_user_id: UUID
    price_estimate: Decimal | None
    currency: str
    eta_minutes: int | None
    message: str | None
    status: str
    created_at: datetime


class JobOfferListResponse(BaseModel):
    """List of job offers response."""
    offers: list[JobOfferResponse]
    total: int


# === Job Proof Schemas ===

class JobProofCreate(BaseModel):
    """Schema for creating a job proof."""
    job_id: UUID
    proof_type: str = Field(..., description="gateway_qr/photo/device_ok/signature")
    proof_payload: dict


class JobProofResponse(BaseModel):
    """Job proof response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    job_id: UUID
    proof_type: str
    proof_payload: dict
    uploaded_by_user_id: UUID | None
    verified_at: datetime | None
    created_at: datetime


# === Job Actions ===

class JobAssign(BaseModel):
    """Schema for assigning a job."""
    offer_id: UUID


class JobRate(BaseModel):
    """Schema for rating a completed job."""
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None
