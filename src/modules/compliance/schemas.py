"""
Compliance Module - Pydantic Schemas
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConsentBase(BaseModel):
    """Base consent schema."""
    consent_type: str = Field(..., description="Type of consent: location/device_control/notifications/telegram/data_processing")
    version: str = Field(..., description="Consent version (e.g., v1.0)")


class ConsentAccept(ConsentBase):
    """Schema for accepting consent."""
    metadata: dict | None = Field(default=None, description="Additional metadata (IP, user agent)")


class ConsentResponse(ConsentBase):
    """Consent response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID
    organization_id: UUID | None
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    is_active: bool


class ConsentListResponse(BaseModel):
    """List of consents response."""
    consents: list[ConsentResponse]
    total: int


class AuditLogResponse(BaseModel):
    """Audit log response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    organization_id: UUID | None
    actor_user_id: UUID | None
    action: str
    entity_type: str
    entity_id: UUID | None
    payload: dict | None
    ip_address: str | None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    """List of audit logs response."""
    logs: list[AuditLogResponse]
    total: int
    page: int
    page_size: int
