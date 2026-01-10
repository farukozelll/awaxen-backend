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


class RewardDistributeRequest(BaseModel):
    """Internal reward distribution request."""
    user_id: UUID
    amount_awx: int = Field(..., gt=0, description="AWX puan miktarı (pozitif)")
    event_type: str = Field(..., description="saving_action/daily_login/streak_bonus/referral")
    asset_id: UUID | None = None
    reference_type: str | None = None
    reference_id: UUID | None = None
    description: str | None = None


class RewardDistributeResponse(BaseModel):
    """Reward distribution response."""
    message: str
    entry: RewardLedgerResponse
    new_balance: int


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


# === EPİAŞ Price Schemas ===

class EpiasPrice(BaseModel):
    """EPİAŞ electricity price for a time slot."""
    timestamp: datetime
    price_try_kwh: Decimal = Field(..., description="Price in TRY per kWh")
    is_high: bool = Field(default=False, description="Is this a high price window?")


class EpiasPriceWindow(BaseModel):
    """High price window information."""
    start_time: datetime
    end_time: datetime
    avg_price_try_kwh: Decimal
    peak_price_try_kwh: Decimal


class EpiasPriceResponse(BaseModel):
    """EPİAŞ price data response."""
    current_price: EpiasPrice
    next_24h: list[EpiasPrice] = Field(default_factory=list)
    high_price_windows: list[EpiasPriceWindow] = Field(default_factory=list)
    threshold_try_kwh: Decimal = Field(..., description="Price threshold for recommendations")


class EpiasPriceHistoryRequest(BaseModel):
    """Request for historical EPİAŞ prices."""
    start_time: datetime
    end_time: datetime


class EpiasPriceHistoryResponse(BaseModel):
    """Historical EPİAŞ price data."""
    prices: list[EpiasPrice]
    avg_price: Decimal
    min_price: Decimal
    max_price: Decimal


# === Core Loop Schemas ===

class RecommendationTriggerRequest(BaseModel):
    """
    Manuel recommendation tetikleme isteği.
    Normalde sistem otomatik tetikler ama test için manuel de tetiklenebilir.
    """
    asset_id: UUID
    reason: str = Field(default="price_high", description="price_high/anomaly/schedule")
    force: bool = Field(default=False, description="Force even if conditions not met")


class RecommendationTriggerResponse(BaseModel):
    """Recommendation tetikleme yanıtı."""
    triggered: bool
    message: str
    recommendation: RecommendationResponse | None = None


class ApproveRecommendationRequest(BaseModel):
    """Recommendation onaylama isteği."""
    recommendation_id: UUID


class ApproveRecommendationResponse(BaseModel):
    """Recommendation onaylama yanıtı."""
    message: str
    recommendation: RecommendationResponse
    command: CommandResponse | None = None


class CoreLoopStatusResponse(BaseModel):
    """Core loop durumu."""
    asset_id: UUID
    current_price: EpiasPrice | None = None
    active_recommendations: int = 0
    pending_commands: int = 0
    total_savings_today_try: Decimal = Decimal("0")
    total_awx_today: int = 0
