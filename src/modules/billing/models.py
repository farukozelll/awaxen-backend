"""
Billing Module - Database Models
Wallets, Transactions, and Invoices for multi-tenant billing.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
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

from src.core.models import Base, TenantMixin

if TYPE_CHECKING:
    from src.modules.auth.models import Organization


class TransactionType(str, Enum):
    """Transaction type enumeration."""
    CREDIT = "credit"           # Money added to wallet
    DEBIT = "debit"             # Money deducted from wallet
    REFUND = "refund"           # Refund to wallet
    ADJUSTMENT = "adjustment"   # Manual adjustment


class TransactionStatus(str, Enum):
    """Transaction status enumeration."""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvoiceStatus(str, Enum):
    """Invoice status enumeration."""
    DRAFT = "draft"
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class Wallet(Base, TenantMixin):
    """
    Wallet model.
    Each organization has one or more wallets for different currencies.
    """
    __tablename__ = "wallet"
    
    __table_args__ = (
        UniqueConstraint("organization_id", "currency", name="uq_wallet_org_currency"),
        Index("ix_wallet_org", "organization_id"),
    )
    
    # Balance
    balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Currency
    currency: Mapped[str] = mapped_column(
        String(3),
        default="TRY",
        nullable=False,
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Credit limit (optional)
    credit_limit: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
        comment="Maximum negative balance allowed",
    )
    
    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="wallets",
    )
    
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="wallet",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    
    @property
    def available_balance(self) -> Decimal:
        """Get available balance including credit limit."""
        if self.credit_limit:
            return self.balance + self.credit_limit
        return self.balance


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
    
    # Related invoice (optional)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoice.id", ondelete="SET NULL"),
        nullable=True,
    )
    
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
    
    invoice: Mapped["Invoice | None"] = relationship(
        "Invoice",
        back_populates="transactions",
    )


class Invoice(Base, TenantMixin):
    """
    Invoice model.
    Billing invoices for organizations.
    """
    __tablename__ = "invoice"
    
    __table_args__ = (
        UniqueConstraint("organization_id", "invoice_number", name="uq_invoice_number"),
        Index("ix_invoice_org_status", "organization_id", "status"),
        Index("ix_invoice_due_date", "due_date"),
    )
    
    # Invoice number
    invoice_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    
    # Dates
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Amounts
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )
    
    # Currency
    currency: Mapped[str] = mapped_column(
        String(3),
        default="TRY",
        nullable=False,
    )
    
    # Status
    status: Mapped[InvoiceStatus] = mapped_column(
        String(20),
        default=InvoiceStatus.DRAFT,
        nullable=False,
        index=True,
    )
    
    # Payment
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Billing period
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    # Description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Line items stored as JSON
    line_items: Mapped[list[dict] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Invoice line items as JSON array",
    )
    
    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Relationships
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="invoice",
        lazy="selectin",
    )
    
    @property
    def is_paid(self) -> bool:
        """Check if invoice is fully paid."""
        return self.paid_amount >= self.total_amount
    
    @property
    def balance_due(self) -> Decimal:
        """Get remaining balance due."""
        return self.total_amount - self.paid_amount
