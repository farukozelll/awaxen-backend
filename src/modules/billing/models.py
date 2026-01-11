"""
Billing Module - Database Models

Wallet ve Transaction modelleri.
AWX puan sistemi için kullanılır.

Wallet Türleri:
- COMPANY: Organizasyon cüzdanı (TL/USD)
- PERSONAL: Kullanıcı cüzdanı (AWX Puan - Ödül/Motivasyon)

İlişkiler:
- COMPANY wallet -> organization_id (FK)
- PERSONAL wallet -> user_id (FK)
"""
import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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

if TYPE_CHECKING:
    from src.modules.auth.models import Organization, User


class WalletType(str, Enum):
    """Wallet type enumeration."""
    COMPANY = "company"      # Organizasyon cüzdanı (TL/USD - Fatura)
    PERSONAL = "personal"    # Kullanıcı cüzdanı (AWX Puan - Ödül)


class TransactionType(str, Enum):
    """Transaction type enumeration."""
    CREDIT = "credit"           # Money/points added to wallet
    DEBIT = "debit"             # Money/points deducted from wallet
    REFUND = "refund"           # Refund to wallet
    ADJUSTMENT = "adjustment"   # Manual adjustment
    REWARD = "reward"           # AWX reward for user actions
    TRANSFER = "transfer"       # Transfer between wallets


class TransactionStatus(str, Enum):
    """Transaction status enumeration."""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Wallet(Base):
    """
    Wallet model.
    
    İki tip cüzdan vardır:
    1. COMPANY (Organizasyon Cüzdanı):
       - Sahibi: Organization
       - Para birimi: TL, USD, EUR
       - Amaç: Fatura ödemeleri, abonelik ücretleri
       
    2. PERSONAL (Kullanıcı Cüzdanı):
       - Sahibi: User
       - Para birimi: AWX (Puan)
       - Amaç: Ödül puanları, motivasyon sistemi
    
    Constraint: wallet_type'a göre organization_id veya user_id dolu olmalı.
    """
    __tablename__ = "wallet"
    
    __table_args__ = (
        # Organizasyon başına currency unique (COMPANY wallet için)
        UniqueConstraint(
            "organization_id", "currency", 
            name="uq_wallet_org_currency",
        ),
        # Kullanıcı başına currency unique (PERSONAL wallet için)
        UniqueConstraint(
            "user_id", "currency",
            name="uq_wallet_user_currency",
        ),
        # wallet_type'a göre doğru FK dolu olmalı
        CheckConstraint(
            """
            (wallet_type = 'company' AND organization_id IS NOT NULL AND user_id IS NULL)
            OR
            (wallet_type = 'personal' AND user_id IS NOT NULL)
            """,
            name="ck_wallet_owner",
        ),
        Index("ix_wallet_org", "organization_id"),
        Index("ix_wallet_user", "user_id"),
        Index("ix_wallet_type", "wallet_type"),
    )
    
    # Primary Key (Base'den geliyor)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Wallet Type
    wallet_type: Mapped[WalletType] = mapped_column(
        String(20),
        default=WalletType.COMPANY,
        nullable=False,
        index=True,
        comment="company=Organizasyon, personal=Kullanıcı",
    )
    
    # Owner: Organization (COMPANY wallet için)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    
    # Owner: User (PERSONAL wallet için)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    
    # Balance
    balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Currency (TRY, USD, EUR for COMPANY; AWX for PERSONAL)
    currency: Mapped[str] = mapped_column(
        String(3),
        default="TRY",
        nullable=False,
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Credit limit (only for COMPANY wallets)
    credit_limit: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
        comment="Maximum negative balance allowed (only for COMPANY wallets)",
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=datetime.utcnow,
        nullable=True,
    )
    
    # Relationships
    organization: Mapped["Organization | None"] = relationship(
        "Organization",
        back_populates="wallets",
        foreign_keys=[organization_id],
    )
    
    user: Mapped["User | None"] = relationship(
        "User",
        back_populates="wallets",
        foreign_keys=[user_id],
    )
    
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="wallet",
        cascade="all, delete-orphan",
        # lazy="selectin" REMOVED - Performance issue: loads ALL transactions on every wallet query
        # Use explicit selectinload() in service when needed with pagination
    )
    
    @property
    def available_balance(self) -> Decimal:
        """Get available balance including credit limit."""
        if self.credit_limit and self.wallet_type == WalletType.COMPANY:
            return self.balance + self.credit_limit
        return self.balance
    
    @property
    def owner_id(self) -> uuid.UUID:
        """Get owner ID (organization or user)."""
        return self.organization_id if self.wallet_type == WalletType.COMPANY else self.user_id
    
    @property
    def owner_type(self) -> str:
        """Get owner type string."""
        return "organization" if self.wallet_type == WalletType.COMPANY else "user"


class Transaction(Base):
    """
    Transaction model.
    Records all wallet transactions.
    """
    __tablename__ = "transaction"
    
    __table_args__ = (
        Index("ix_transaction_wallet", "wallet_id"),
        Index("ix_transaction_type", "transaction_type"),
        Index("ix_transaction_created", "created_at"),
    )
    
    # Wallet reference
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wallet.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Transaction details
    transaction_type: Mapped[TransactionType] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )
    
    amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )
    
    # Balance after transaction
    balance_after: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )
    
    # Status
    status: Mapped[TransactionStatus] = mapped_column(
        String(20),
        default=TransactionStatus.COMPLETED,
        nullable=False,
    )
    
    # Reference
    reference: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="External reference (e.g., payment gateway ID)",
    )
    
    # Description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Metadata
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )
    
    # Relationships
    wallet: Mapped["Wallet"] = relationship(
        "Wallet",
        back_populates="transactions",
    )
    
