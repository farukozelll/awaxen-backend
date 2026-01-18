"""
Referral Module - Database Models

Referral system for user acquisition:
- ReferralCampaign: Campaign definitions with reward rules
- ReferralConversion: Tracking referrer/referee conversions
"""
import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models import Base


class RewardType(str, Enum):
    """Types of rewards for referral campaigns."""
    BALANCE = "balance"       # TL balance credit
    AWX_POINT = "awx_point"   # AWX points
    DISCOUNT = "discount"     # Discount coupon


class ConversionStatus(str, Enum):
    """Status of referral conversion."""
    PENDING = "pending"       # Waiting for qualification
    QUALIFIED = "qualified"   # Met requirements, awaiting payment
    PAID = "paid"             # Reward distributed
    FRAUD = "fraud"           # Flagged as fraudulent
    EXPIRED = "expired"       # Campaign expired before qualification


class ReferralCampaign(Base):
    """
    Referral campaign definition.
    
    Defines reward structure for referral program:
    - Reward type (balance, points, discount)
    - Amounts for referrer and referee
    - Campaign validity period
    - Qualification rules
    """
    __tablename__ = "referral_campaign"
    
    __table_args__ = (
        Index("idx_campaign_active", "is_active"),
        Index("idx_campaign_dates", "start_date", "end_date"),
    )
    
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Campaign name (e.g., Standart Davet, Yaz Kampanyası)",
    )
    
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="URL-friendly campaign identifier",
    )
    
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )
    
    # Campaign validity period
    start_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Campaign start date (null = immediate)",
    )
    end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Campaign end date (null = no expiry)",
    )
    
    # Reward configuration
    reward_type: Mapped[str] = mapped_column(
        String(50),
        default=RewardType.BALANCE.value,
        nullable=False,
        comment="balance (TL), awx_point (Puan), discount (İndirim)",
    )
    
    referrer_reward_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0"),
        nullable=False,
        comment="Reward amount for referrer",
    )
    
    referee_reward_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0"),
        nullable=False,
        comment="Reward amount for referee (new user)",
    )
    
    # Qualification rules
    rules: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="Qualification rules: min_spend, min_days, etc.",
    )
    
    # Limits
    max_conversions: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Maximum total conversions for campaign",
    )
    max_per_referrer: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Maximum conversions per referrer",
    )
    
    # Relationships
    conversions: Mapped[list["ReferralConversion"]] = relationship(
        "ReferralConversion",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )


class ReferralConversion(Base):
    """
    Referral conversion tracking.
    
    Records each referral event:
    - Who referred (referrer)
    - Who was referred (referee)
    - Conversion status
    - Reward distribution tracking
    """
    __tablename__ = "referral_conversion"
    
    __table_args__ = (
        UniqueConstraint("referee_user_id", name="uq_conversion_referee"),
        Index("idx_conversion_referrer_status", "referrer_user_id", "status"),
        Index("idx_conversion_campaign", "campaign_id"),
    )
    
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("referral_campaign.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    referrer_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who made the referral",
    )
    
    referee_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="New user who was referred (can only be referred once)",
    )
    
    status: Mapped[str] = mapped_column(
        String(30),
        default=ConversionStatus.PENDING.value,
        nullable=False,
        index=True,
        comment="pending, qualified, paid, fraud, expired",
    )
    
    # Reward tracking - links to actual reward records
    reward_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wallet_transaction.id", ondelete="SET NULL"),
        nullable=True,
        comment="Wallet transaction ID for balance rewards",
    )
    
    reward_ledger_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reward_ledger.id", ondelete="SET NULL"),
        nullable=True,
        comment="Reward ledger ID for AWX point rewards",
    )
    
    # Qualification tracking
    qualified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When referee met qualification criteria",
    )
    
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When rewards were distributed",
    )
    
    # Security/fraud detection metadata
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        comment="IP matching, device info, fraud signals",
    )
    
    # Relationships
    campaign: Mapped["ReferralCampaign | None"] = relationship(
        "ReferralCampaign",
        back_populates="conversions",
    )
