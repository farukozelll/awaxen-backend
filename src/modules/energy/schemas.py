"""
Energy Module - Pydantic Schemas
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# === Recommendation Schemas ===

class RecommendationBase(BaseModel):
    """Base recommendation schema."""
    reason: str = Field(..., description="Reason: price_high/anomaly/schedule/predictive")
    expected_saving_try: Decimal | None = Field(None, description="Expected saving in TRY")
    expected_saving_kwh: Decimal | None = Field(None, description="Expected saving in kWh")


class RecommendationCreate(RecommendationBase):
    """Schema for creating a recommendation."""
    asset_id: UUID
    target_device_id: UUID | None = None
    expires_at: datetime | None = None
    payload: dict | None = None


class RecommendationResponse(RecommendationBase):
    """Recommendation response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    asset_id: UUID
    target_device_id: UUID | None
    status: str
    expires_at: datetime | None
    payload: dict | None
    created_at: datetime


class RecommendationListResponse(BaseModel):
    """List of recommendations response."""
    recommendations: list[RecommendationResponse]
    total: int


class RecommendationAction(BaseModel):
    """Schema for responding to a recommendation."""
    action: str = Field(..., description="approve/defer/reject")


# === Command Schemas ===

class CommandCreate(BaseModel):
    """Schema for creating a command."""
    recommendation_id: UUID | None = None
    gateway_id: UUID
    device_id: UUID
    action: str = Field(..., description="turn_off/turn_on/eco_mode/set_temp")
    params: dict | None = None


class CommandResponse(BaseModel):
    """Command response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    recommendation_id: UUID | None
    gateway_id: UUID
    device_id: UUID
    action: str
    params: dict | None
    status: str
    idempotency_key: str
    sent_at: datetime | None
    acked_at: datetime | None
    finished_at: datetime | None
    error: str | None
    created_at: datetime


class CommandResult(BaseModel):
    """Schema for command result from gateway."""
    command_id: UUID
    status: str = Field(..., description="success/failed")
    executed_at: datetime
    proof: dict | None = None
    error: str | None = None


# === Reward Schemas ===

class RewardLedgerResponse(BaseModel):
    """Reward ledger entry response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID
    asset_id: UUID | None
    event_type: str
    amount_awx: int
    expires_at: datetime | None
    reference_type: str | None
    reference_id: UUID | None
    description: str | None
    created_at: datetime


class RewardBalanceResponse(BaseModel):
    """User's reward balance."""
    user_id: UUID
    total_awx: int
    available_awx: int
    pending_awx: int


class RewardLedgerListResponse(BaseModel):
    """List of reward ledger entries."""
    entries: list[RewardLedgerResponse]
    total: int
    page: int
    page_size: int


# === Streak Schemas ===

class StreakResponse(BaseModel):
    """Streak response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID
    streak_type: str
    current_count: int
    longest_count: int
    last_date: datetime | None


class UserStreaksResponse(BaseModel):
    """All streaks for a user."""
    streaks: list[StreakResponse]
