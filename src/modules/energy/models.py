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
        lazy="selectin",
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
        lazy="selectin",
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
