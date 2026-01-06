"""
Billing Module - Pydantic Schemas (DTOs)
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from src.modules.billing.models import InvoiceStatus, TransactionStatus, TransactionType


# ============== Wallet Schemas ==============

class WalletBase(BaseModel):
    """Base wallet schema."""
    currency: str = Field(default="TRY", max_length=3)
    credit_limit: Decimal | None = Field(None, ge=0)


class WalletCreate(WalletBase):
    """Schema for creating a wallet."""
    pass


class WalletUpdate(BaseModel):
    """Schema for updating a wallet."""
    is_active: bool | None = None
    credit_limit: Decimal | None = Field(None, ge=0)


class WalletResponse(WalletBase):
    """Wallet response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    organization_id: uuid.UUID
    balance: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WalletWithTransactions(WalletResponse):
    """Wallet with recent transactions."""
    transactions: list["TransactionResponse"] = []


# ============== Transaction Schemas ==============

class TransactionBase(BaseModel):
    """Base transaction schema."""
    transaction_type: TransactionType
    amount: Decimal = Field(..., gt=0)
    description: str | None = None
    reference: str | None = None
    metadata_: dict | None = Field(None, alias="metadata")


class TransactionCreate(TransactionBase):
    """Schema for creating a transaction."""
    wallet_id: uuid.UUID
    invoice_id: uuid.UUID | None = None


class TransactionResponse(TransactionBase):
    """Transaction response schema."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    
    id: uuid.UUID
    wallet_id: uuid.UUID
    balance_after: Decimal
    status: TransactionStatus
    invoice_id: uuid.UUID | None = None
    created_at: datetime


# ============== Invoice Schemas ==============

class InvoiceLineItem(BaseModel):
    """Invoice line item schema."""
    description: str
    quantity: Decimal = Field(default=Decimal("1"))
    unit_price: Decimal
    amount: Decimal
    tax_rate: Decimal = Field(default=Decimal("0"))


class InvoiceBase(BaseModel):
    """Base invoice schema."""
    invoice_number: str = Field(..., max_length=50)
    issue_date: date
    due_date: date
    subtotal: Decimal = Field(..., ge=0)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    total_amount: Decimal = Field(..., ge=0)
    currency: str = Field(default="TRY", max_length=3)
    description: str | None = None
    notes: str | None = None
    period_start: date | None = None
    period_end: date | None = None


class InvoiceCreate(InvoiceBase):
    """Schema for creating an invoice."""
    line_items: list[InvoiceLineItem] | None = None
    status: InvoiceStatus = InvoiceStatus.DRAFT


class InvoiceUpdate(BaseModel):
    """Schema for updating an invoice."""
    issue_date: date | None = None
    due_date: date | None = None
    subtotal: Decimal | None = Field(None, ge=0)
    tax_amount: Decimal | None = Field(None, ge=0)
    discount_amount: Decimal | None = Field(None, ge=0)
    total_amount: Decimal | None = Field(None, ge=0)
    status: InvoiceStatus | None = None
    description: str | None = None
    notes: str | None = None
    line_items: list[InvoiceLineItem] | None = None


class InvoiceResponse(InvoiceBase):
    """Invoice response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    organization_id: uuid.UUID
    status: InvoiceStatus
    paid_at: datetime | None = None
    paid_amount: Decimal
    line_items: list[dict] | None = None
    created_at: datetime
    updated_at: datetime


class InvoiceWithTransactions(InvoiceResponse):
    """Invoice with payment transactions."""
    transactions: list[TransactionResponse] = []


# ============== Payment Schemas ==============

class PaymentRequest(BaseModel):
    """Request to pay an invoice."""
    invoice_id: uuid.UUID
    amount: Decimal = Field(..., gt=0)
    reference: str | None = None


class TopUpRequest(BaseModel):
    """Request to top up wallet."""
    wallet_id: uuid.UUID
    amount: Decimal = Field(..., gt=0)
    reference: str | None = None
    description: str | None = None


# Forward references
WalletWithTransactions.model_rebuild()
