"""
Energy Module - Database Models

Core loop models:
- Recommendation: Energy saving suggestions based on price/consumption
- Command: Actions sent to gateway/devices
- CommandProof: Verification that command was executed
- RewardLedger: AWX points for successful actions
- Streak: Gamification - consecutive saving streaks
"""
import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models import Base


class RecommendationStatus(str, Enum):
    """Recommendation lifecycle status."""
    CREATED = "created"
    NOTIFIED = "notified"
    APPROVED = "approved"
    DEFERRED = "deferred"
    REJECTED = "rejected"
    EXPIRED = "expired"


class RecommendationReason(str, Enum):
    """Why this recommendation was generated."""
    PRICE_HIGH = "price_high"
    ANOMALY = "anomaly"
    SCHEDULE = "schedule"
    PREDICTIVE = "predictive"
    USER_PATTERN = "user_pattern"


class RiskLevel(str, Enum):
    """Risk level for recommendations."""
    LOW = "low"         # Timing, standby - safe actions
    MEDIUM = "medium"   # HVAC setpoint changes
    HIGH = "high"       # Automation, power cut - requires explicit approval


class CommandStatus(str, Enum):
    """Command execution status."""
    QUEUED = "queued"
    SENT = "sent"
    ACKED = "acked"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class CommandAction(str, Enum):
    """Available command actions."""
    TURN_OFF = "turn_off"
    TURN_ON = "turn_on"
    ECO_MODE = "eco_mode"
    SET_TEMP = "set_temp"
    SET_POWER = "set_power"
    SCHEDULE = "schedule"


class ProofType(str, Enum):
    """Types of command execution proof."""
    STATE_CHANGED = "state_changed"
    POWER_DROP = "power_drop"
    BOTH = "both"


class RewardEventType(str, Enum):
    """Types of reward events."""
    SAVING_ACTION = "saving_action"
    DAILY_LOGIN = "daily_login"
    MAINTENANCE_JOB = "maintenance_job"
    STREAK_BONUS = "streak_bonus"
    REFERRAL = "referral"
    MANUAL_ADJUSTMENT = "manual_adjustment"


class StreakType(str, Enum):
    """Types of streaks for gamification."""
    DAILY_SAVING = "daily_saving"
    WEEKLY_SAVING = "weekly_saving"
    MONTHLY_SAVING = "monthly_saving"
    APPROVAL_STREAK = "approval_streak"


class Recommendation(Base):
    """
    Energy saving recommendation.
    
    Generated when:
    - EPİAŞ price is high
    - Consumption exceeds threshold
    - Controllable device is available
    
    User can: Approve, Defer, or Reject
    """
    __tablename__ = "recommendation"
    
    __table_args__ = (
        Index("idx_reco_asset_time", "asset_id", "created_at"),
        Index("idx_reco_status", "status"),
        Index("idx_reco_expires", "expires_at"),
    )
    
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("asset.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    target_device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("device.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    reason: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="price_high/anomaly/schedule/predictive",
    )
    
    # Estimated savings
    expected_saving_try: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Expected saving in TRY",
    )
    expected_saving_kwh: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4),
        nullable=True,
        comment="Expected saving in kWh",
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        default=RecommendationStatus.CREATED.value,
        nullable=False,
        index=True,
    )
    
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Risk level for user trust building
    risk_level: Mapped[str] = mapped_column(
        String(20),
        default="low",
        nullable=False,
        comment="low/medium/high - affects user approval flow",
    )
    
    # Additional context
    payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="Price window, consumption data, etc.",
    )
    
    # Relationships
    commands: Mapped[list["Command"]] = relationship(
        "Command",
        back_populates="recommendation",
        cascade="all, delete-orphan",
        # lazy="selectin" REMOVED - Performance: Load explicitly when needed
    )


class Command(Base):
    """
    Command sent to gateway/device.
    
    Created when user approves a recommendation.
    Dispatched via MQTT to gateway.
    """
    __tablename__ = "command"
    
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_command_idempotency"),
        Index("idx_command_gateway_time", "gateway_id", "created_at"),
        Index("idx_command_status", "status"),
    )
    
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recommendation.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    gateway_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gateway.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("device.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    action: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="turn_off/eco_mode/set_temp/etc.",
    )
    
    params: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="Action parameters (temperature, duration, etc.)",
    )
    
    status: Mapped[str] = mapped_column(
        String(20),
        default=CommandStatus.QUEUED.value,
        nullable=False,
        index=True,
    )
    
    # Idempotency key for retry safety
    idempotency_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )
    
    # Timestamps
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    acked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Error info
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Relationships
    recommendation: Mapped["Recommendation | None"] = relationship(
        "Recommendation",
        back_populates="commands",
    )
    
    proofs: Mapped[list["CommandProof"]] = relationship(
        "CommandProof",
        back_populates="command",
        cascade="all, delete-orphan",
        # lazy="selectin" REMOVED - Performance: Load explicitly when needed
    )


class CommandProof(Base):
    """
    Proof that a command was executed successfully.
    
    Collected from gateway after command execution.
    Required for reward distribution.
    """
    __tablename__ = "command_proof"
    
    __table_args__ = (
        Index("idx_proof_command", "command_id"),
    )
    
    command_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("command.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    proof_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="state_changed/power_drop/both",
    )
    
    proof_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Before/after state, power readings, timestamps",
    )
    
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Relationships
    command: Mapped["Command"] = relationship(
        "Command",
        back_populates="proofs",
    )


class RewardLedger(Base):
    """
    AWX points ledger.
    
    Records all point transactions (credits and debits).
    Points are earned through successful energy saving actions.
    """
    __tablename__ = "reward_ledger"
    
    __table_args__ = (
        UniqueConstraint(
            "event_type", "reference_type", "reference_id",
            name="uq_reward_event_ref"
        ),
        Index("idx_ledger_user_time", "user_id", "created_at"),
        Index("idx_ledger_asset", "asset_id"),
    )
    
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("asset.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    event_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="saving_action/daily_login/maintenance_job/streak_bonus",
    )
    
    # Points (positive = credit, negative = debit)
    amount_awx: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    
    # Optional expiration
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Reference to source event
    reference_type: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="command/job/streak",
    )
    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    
    # Description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Streak(Base):
    """
    User streaks for gamification.
    
    Tracks consecutive saving actions for bonus rewards.
    """
    __tablename__ = "streak"
    
    __table_args__ = (
        UniqueConstraint("user_id", "streak_type", name="uq_user_streak"),
        Index("idx_streak_user", "user_id"),
    )
    
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    streak_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="daily_saving/weekly_saving/approval_streak",
    )
    
    current_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    
    longest_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    
    last_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


# =============================================================================
# B) SAVING VERIFICATION - Tasarruf kanıtı doğrulama modeli
# =============================================================================

class VerificationMethod(str, Enum):
    """Methods for calculating savings."""
    BASELINE = "baseline"       # Compare to historical baseline
    PEER = "peer"               # Compare to similar devices/assets
    SEASONAL = "seasonal"       # Seasonal adjustment comparison
    PREDICTIVE = "predictive"   # ML-based prediction comparison


class SavingVerification(Base):
    """
    Saving verification for recommendations.
    
    Provides structured proof of energy savings with:
    - Baseline and comparison windows
    - Calculated savings (kWh and TRY)
    - Confidence score
    - Verification method
    
    Replaces unstructured command_proof JSONB for reporting.
    
    NOTE: recommendation_id is UNIQUE (one verification per recommendation).
    This is intentional for MVP simplicity. If re-verification is needed:
    - Option A: UPDATE existing record (loses history)
    - Option B: Change to UNIQUE(recommendation_id, verified_at) + is_latest flag
    For V2, consider adding verification history if algorithm updates require re-runs.
    """
    __tablename__ = "saving_verification"
    
    __table_args__ = (
        Index("idx_saving_verif_reco", "recommendation_id"),
        Index("idx_saving_verif_time", "verified_at"),
    )
    
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recommendation.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    
    # Baseline window (before action)
    baseline_window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Start of baseline measurement period",
    )
    baseline_window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="End of baseline measurement period",
    )
    baseline_kwh: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        comment="Energy consumption during baseline period",
    )
    
    # Comparison window (after action)
    compare_window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Start of comparison measurement period",
    )
    compare_window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="End of comparison measurement period",
    )
    compare_kwh: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        comment="Energy consumption during comparison period",
    )
    
    # Calculated savings
    saved_kwh: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        comment="Verified energy saving in kWh",
    )
    saved_try: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Verified saving in TRY (using applicable tariff)",
    )
    
    # Confidence and method
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Confidence score 0-100",
    )
    method: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="baseline/peer/seasonal/predictive",
    )
    
    # Verification timestamp
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    
    # Additional context
    verification_details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional verification data (weather, occupancy, etc.)",
    )
    
    # Relationship
    recommendation: Mapped["Recommendation"] = relationship(
        "Recommendation",
        backref="saving_verification",
    )


# =============================================================================
# C) ENERGY PRICING - EPİAŞ ve Tarife Modelleri
# =============================================================================

class MarketType(str, Enum):
    """Energy market types."""
    EPIAS_DAM = "epias_dam"     # Day-ahead market (GÖP)
    EPIAS_IDM = "epias_idm"     # Intraday market (GİP)
    EPIAS_BPM = "epias_bpm"     # Balancing power market (DGP)
    RETAIL = "retail"           # Retail tariff


class EnergyPrice(Base):
    """
    Energy price data from EPİAŞ and other sources.
    
    Stores hourly/sub-hourly price data for:
    - Day-ahead market (GÖP)
    - Intraday market (GİP)
    - Balancing power market (DGP)
    
    IMPORTANT: Consider making this a TimescaleDB hypertable:
        SELECT create_hypertable('energy_price', 'timestamp');
    """
    __tablename__ = "energy_price"
    
    __table_args__ = (
        UniqueConstraint("timestamp", "market", "region", name="uq_price_ts_market_region"),
        Index("idx_price_time", "timestamp"),
        Index("idx_price_market_time", "market", "timestamp"),
    )
    
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Price period start time",
    )
    
    market: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="epias_dam/epias_idm/epias_bpm/retail",
    )
    
    price_try_mwh: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Price in TRY per MWh",
    )
    
    # price_try_kwh is a GENERATED COLUMN in PostgreSQL
    # GENERATED ALWAYS AS (price_try_mwh / 1000) STORED
    # Do NOT set this field manually - it's computed from price_try_mwh
    price_try_kwh: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 6),
        nullable=True,  # Generated columns can't have NOT NULL in SQLAlchemy
        comment="Price in TRY per kWh (GENERATED from price_try_mwh / 1000)",
    )
    
    region: Mapped[str] = mapped_column(
        String(20),
        default="TR",
        nullable=False,
        comment="Price region (TR for national)",
    )
    
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Data source (epias_api, manual, etc.)",
    )
    
    # Additional market data
    volume_mwh: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
        comment="Trading volume in MWh",
    )
    
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        comment="Additional market data",
    )


class TariffType(str, Enum):
    """Tariff types."""
    SINGLE = "single"           # Single rate (tek zamanlı)
    TWO_PERIOD = "two_period"   # Day/night (çift zamanlı)
    THREE_PERIOD = "three_period"  # Peak/day/night (üç zamanlı)
    CUSTOM = "custom"           # Custom tariff structure


class TariffProfile(Base):
    """
    Tariff profile for organizations.
    
    Defines electricity tariff structure including:
    - Base rates for different periods
    - Taxes and fees
    - Demand charges
    """
    __tablename__ = "tariff_profile"
    
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_tariff_org_name"),
        Index("idx_tariff_org", "organization_id"),
    )
    
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Tariff profile name",
    )
    
    tariff_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="single/two_period/three_period/custom",
    )
    
    # Base rates (TRY/kWh)
    rate_peak: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 6),
        nullable=True,
        comment="Peak period rate (TRY/kWh)",
    )
    rate_day: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 6),
        nullable=True,
        comment="Day period rate (TRY/kWh)",
    )
    rate_night: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 6),
        nullable=True,
        comment="Night period rate (TRY/kWh)",
    )
    rate_single: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 6),
        nullable=True,
        comment="Single rate (TRY/kWh) for single tariff",
    )
    
    # Period definitions (hour ranges)
    peak_hours: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Peak hours definition {'start': 17, 'end': 22}",
    )
    day_hours: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Day hours definition {'start': 6, 'end': 17}",
    )
    night_hours: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Night hours definition {'start': 22, 'end': 6}",
    )
    
    # Taxes and fees (multipliers)
    distribution_fee: Mapped[Decimal] = mapped_column(
        Numeric(8, 6),
        default=Decimal("0"),
        nullable=False,
        comment="Distribution fee (TRY/kWh)",
    )
    tax_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=Decimal("0.20"),
        nullable=False,
        comment="Tax rate (e.g., 0.20 for 20%)",
    )
    
    # Demand charge
    demand_charge_try_kw: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Demand charge per kW",
    )
    
    # Validity
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
    )


class TariffAssignment(Base):
    """
    Tariff assignment to assets, zones, or devices.
    
    Priority order (highest wins): device > zone > asset
    
    Constraint: Only ONE active assignment per target at any time.
    Use valid_from/valid_to for time-based assignments.
    """
    __tablename__ = "tariff_assignment"
    
    __table_args__ = (
        Index("idx_tariff_assign_asset", "asset_id"),
        Index("idx_tariff_assign_zone", "zone_id"),
        Index("idx_tariff_assign_device", "device_id"),
        # Prevent duplicate active assignments for same target
        # Note: Partial unique index created in migration for active assignments
    )
    
    tariff_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tariff_profile.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Target: One of asset_id, zone_id, or device_id should be set
    # Priority: device > zone > asset
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("asset.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("zone.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("device.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    
    # Priority level (auto-calculated: device=30, zone=20, asset=10)
    priority: Mapped[int] = mapped_column(
        Integer,
        default=10,
        nullable=False,
        comment="Priority: device(30) > zone(20) > asset(10)",
    )
    
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Relationships
    tariff_profile: Mapped["TariffProfile"] = relationship(
        "TariffProfile",
        backref="assignments",
    )
