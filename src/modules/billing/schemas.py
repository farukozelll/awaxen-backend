"""
Billing Module - Pydantic Schemas (DTOs)

Wallet ve Transaction şemaları.
AWX puan sistemi için kullanılır.

Wallet Türleri:
- COMPANY: Organizasyon cüzdanı (TL/USD)
- PERSONAL: Kullanıcı cüzdanı (AWX Puan - Ödül/Motivasyon)
"""
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from src.modules.billing.models import TransactionStatus, TransactionType, WalletType


# ============== Wallet Schemas ==============

class WalletBase(BaseModel):
    """Base wallet schema."""
    currency: str = Field(default="TRY", max_length=3)
    credit_limit: Decimal | None = Field(None, ge=0)


class WalletCreate(WalletBase):
    """Schema for creating a COMPANY wallet."""
    pass


class WalletUpdate(BaseModel):
    """Schema for updating a wallet."""
    is_active: bool | None = None
    credit_limit: Decimal | None = Field(None, ge=0)


class WalletResponse(WalletBase):
    """Wallet response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    wallet_type: WalletType = WalletType.COMPANY
    organization_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    balance: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None


class WalletWithTransactions(WalletResponse):
    """Wallet with recent transactions."""
    transactions: list["TransactionResponse"] = []


# ============== User Wallet Schemas ==============

class UserWalletResponse(BaseModel):
    """User's personal wallet response."""
    model_config = ConfigDict(from_attributes=True)
    
    user_id: uuid.UUID
    wallet_id: uuid.UUID | None = None
    currency: str = "AWX"
    balance: str = "0.00"
    is_active: bool = True
    has_wallet: bool = False


class RewardRequest(BaseModel):
    """Request to add reward to user wallet."""
    user_id: uuid.UUID
    amount: Decimal = Field(..., gt=0)
    description: str
    reference: str | None = None


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


class TransactionResponse(TransactionBase):
    """Transaction response schema."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    
    id: uuid.UUID
    wallet_id: uuid.UUID
    balance_after: Decimal
    status: TransactionStatus
    created_at: datetime


# ============== Top Up Schemas ==============

class TopUpRequest(BaseModel):
    """Request to top up wallet."""
    wallet_id: uuid.UUID
    amount: Decimal = Field(..., gt=0)
    reference: str | None = None
    description: str | None = None


# Forward references
WalletWithTransactions.model_rebuild()
