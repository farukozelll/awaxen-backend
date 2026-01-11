"""
Billing Module - Business Logic Service

Wallet ve Transaction işlemleri.
AWX puan sistemi için kullanılır.

Wallet Türleri:
- COMPANY: Organizasyon cüzdanı (TL/USD)
- PERSONAL: Kullanıcı cüzdanı (AWX Puan - Ödül/Motivasyon)
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError, ValidationError
from src.core.logging import get_logger
from src.modules.billing.models import (
    Transaction,
    TransactionStatus,
    TransactionType,
    Wallet,
    WalletType,
)
from src.modules.billing.schemas import (
    TopUpRequest,
    WalletCreate,
    WalletUpdate,
)

logger = get_logger(__name__)


class BillingService:
    """Billing and wallet management service."""
    
    def __init__(self, db: AsyncSession, organization_id: uuid.UUID):
        self.db = db
        self.organization_id = organization_id
    
    # ============== Organization (COMPANY) Wallet Operations ==============
    
    async def get_wallet_by_id(self, wallet_id: uuid.UUID) -> Wallet | None:
        """Get COMPANY wallet by ID within organization."""
        stmt = select(Wallet).where(
            Wallet.id == wallet_id,
            Wallet.organization_id == self.organization_id,
            Wallet.wallet_type == WalletType.COMPANY,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_wallet_by_currency(self, currency: str) -> Wallet | None:
        """Get COMPANY wallet by currency within organization."""
        stmt = select(Wallet).where(
            Wallet.organization_id == self.organization_id,
            Wallet.wallet_type == WalletType.COMPANY,
            Wallet.currency == currency.upper(),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_default_wallet(self) -> Wallet | None:
        """Get default COMPANY wallet for organization (TRY currency)."""
        return await self.get_wallet_by_currency("TRY")
    
    async def list_wallets(self) -> Sequence[Wallet]:
        """List all COMPANY wallets for organization."""
        stmt = (
            select(Wallet)
            .where(
                Wallet.organization_id == self.organization_id,
                Wallet.wallet_type == WalletType.COMPANY,
            )
            .order_by(Wallet.currency)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def create_wallet(self, data: WalletCreate) -> Wallet:
        """Create a new COMPANY wallet for organization."""
        currency = data.currency.upper()
        
        existing = await self.get_wallet_by_currency(currency)
        if existing:
            raise ConflictError(f"Wallet with currency '{currency}' already exists")
        
        wallet = Wallet(
            wallet_type=WalletType.COMPANY,
            organization_id=self.organization_id,
            user_id=None,
            currency=currency,
            credit_limit=data.credit_limit,
            balance=Decimal("0.00"),
        )
        self.db.add(wallet)
        await self.db.commit()
        await self.db.refresh(wallet)
        
        logger.info(
            "Company wallet created",
            wallet_id=str(wallet.id),
            organization_id=str(self.organization_id),
            currency=currency,
        )
        return wallet
    
    async def update_wallet(self, wallet_id: uuid.UUID, data: WalletUpdate) -> Wallet:
        """Update a wallet."""
        wallet = await self.get_wallet_by_id(wallet_id)
        if not wallet:
            raise NotFoundError("Wallet", wallet_id)
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(wallet, field, value)
        
        await self.db.commit()
        await self.db.refresh(wallet)
        return wallet
    
    async def top_up_wallet(self, request: TopUpRequest) -> Transaction:
        """Add funds to wallet with row-level locking to prevent race conditions."""
        # Use FOR UPDATE to lock the row and prevent race conditions
        stmt = select(Wallet).where(
            Wallet.id == request.wallet_id,
            Wallet.organization_id == self.organization_id,
            Wallet.wallet_type == WalletType.COMPANY,
        ).with_for_update()
        result = await self.db.execute(stmt)
        wallet = result.scalar_one_or_none()
        
        if not wallet:
            raise NotFoundError("Wallet", request.wallet_id)
        
        if not wallet.is_active:
            raise ValidationError("Wallet is not active")
        
        # Update balance (now safe from race conditions)
        new_balance = wallet.balance + request.amount
        wallet.balance = new_balance
        
        # Create transaction
        transaction = Transaction(
            wallet_id=wallet.id,
            transaction_type=TransactionType.CREDIT,
            amount=request.amount,
            balance_after=new_balance,
            status=TransactionStatus.COMPLETED,
            reference=request.reference,
            description=request.description or "Wallet top-up",
        )
        self.db.add(transaction)
        
        await self.db.commit()
        await self.db.refresh(transaction)
        
        logger.info(
            "Wallet topped up",
            wallet_id=str(wallet.id),
            amount=str(request.amount),
            new_balance=str(new_balance),
        )
        return transaction
    
    async def debit_wallet(
        self,
        wallet_id: uuid.UUID,
        amount: Decimal,
        description: str,
        reference: str | None = None,
    ) -> Transaction:
        """Deduct funds from wallet with row-level locking to prevent race conditions."""
        # Use FOR UPDATE to lock the row and prevent race conditions
        stmt = select(Wallet).where(
            Wallet.id == wallet_id,
            Wallet.organization_id == self.organization_id,
            Wallet.wallet_type == WalletType.COMPANY,
        ).with_for_update()
        result = await self.db.execute(stmt)
        wallet = result.scalar_one_or_none()
        
        if not wallet:
            raise NotFoundError("Wallet", wallet_id)
        
        if not wallet.is_active:
            raise ValidationError("Wallet is not active")
        
        # Check available balance
        if wallet.available_balance < amount:
            raise ValidationError(
                f"Insufficient balance. Available: {wallet.available_balance}, Required: {amount}"
            )
        
        # Update balance (now safe from race conditions)
        new_balance = wallet.balance - amount
        wallet.balance = new_balance
        
        # Create transaction
        transaction = Transaction(
            wallet_id=wallet.id,
            transaction_type=TransactionType.DEBIT,
            amount=amount,
            balance_after=new_balance,
            status=TransactionStatus.COMPLETED,
            reference=reference,
            description=description,
        )
        self.db.add(transaction)
        
        await self.db.commit()
        await self.db.refresh(transaction)
        
        logger.info(
            "Wallet debited",
            wallet_id=str(wallet.id),
            amount=str(amount),
            new_balance=str(new_balance),
        )
        return transaction
    
    # ============== Transaction Operations ==============
    
    async def get_transaction_by_id(self, transaction_id: uuid.UUID) -> Transaction | None:
        """Get transaction by ID."""
        stmt = (
            select(Transaction)
            .join(Wallet)
            .where(
                Transaction.id == transaction_id,
                Wallet.organization_id == self.organization_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_transactions(
        self,
        wallet_id: uuid.UUID | None = None,
        transaction_type: TransactionType | None = None,
        limit: int = 100,
    ) -> Sequence[Transaction]:
        """List transactions with optional filters."""
        stmt = (
            select(Transaction)
            .join(Wallet)
            .where(Wallet.organization_id == self.organization_id)
        )
        
        if wallet_id:
            stmt = stmt.where(Transaction.wallet_id == wallet_id)
        if transaction_type:
            stmt = stmt.where(Transaction.transaction_type == transaction_type)
        
        stmt = stmt.order_by(Transaction.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    # ============== User (PERSONAL) Wallet Operations ==============
    
    async def get_user_wallet(self, user_id: uuid.UUID, currency: str = "AWX") -> Wallet | None:
        """Get PERSONAL wallet for a user."""
        stmt = select(Wallet).where(
            Wallet.user_id == user_id,
            Wallet.wallet_type == WalletType.PERSONAL,
            Wallet.currency == currency.upper(),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_or_create_user_wallet(self, user_id: uuid.UUID, currency: str = "AWX") -> Wallet:
        """Get or create PERSONAL wallet for a user."""
        wallet = await self.get_user_wallet(user_id, currency)
        if wallet:
            return wallet
        
        # Create new personal wallet
        wallet = Wallet(
            wallet_type=WalletType.PERSONAL,
            organization_id=None,
            user_id=user_id,
            currency=currency.upper(),
            balance=Decimal("0.00"),
            credit_limit=None,  # Personal wallets don't have credit limit
        )
        self.db.add(wallet)
        await self.db.commit()
        await self.db.refresh(wallet)
        
        logger.info(
            "Personal wallet created",
            wallet_id=str(wallet.id),
            user_id=str(user_id),
            currency=currency,
        )
        return wallet
    
    async def list_user_wallets(self, user_id: uuid.UUID) -> Sequence[Wallet]:
        """List all PERSONAL wallets for a user."""
        stmt = (
            select(Wallet)
            .where(
                Wallet.user_id == user_id,
                Wallet.wallet_type == WalletType.PERSONAL,
            )
            .order_by(Wallet.currency)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def add_reward_to_user(
        self,
        user_id: uuid.UUID,
        amount: Decimal,
        description: str,
        reference: str | None = None,
    ) -> Transaction:
        """
        Add AWX reward points to user's personal wallet with row-level locking.
        
        Bu metod Energy Core Loop'ta kullanılır:
        - Kullanıcı enerji tasarrufu önerisini onayladığında
        - Sistem tarafından otomatik ödül verildiğinde
        """
        # First ensure wallet exists
        wallet = await self.get_or_create_user_wallet(user_id, "AWX")
        
        # Then lock it for update to prevent race conditions
        stmt = select(Wallet).where(Wallet.id == wallet.id).with_for_update()
        result = await self.db.execute(stmt)
        wallet = result.scalar_one()
        
        if not wallet.is_active:
            raise ValidationError("User wallet is not active")
        
        # Update balance (now safe from race conditions)
        new_balance = wallet.balance + amount
        wallet.balance = new_balance
        
        # Create reward transaction
        transaction = Transaction(
            wallet_id=wallet.id,
            transaction_type=TransactionType.REWARD,
            amount=amount,
            balance_after=new_balance,
            status=TransactionStatus.COMPLETED,
            reference=reference,
            description=description,
        )
        self.db.add(transaction)
        
        await self.db.commit()
        await self.db.refresh(transaction)
        
        logger.info(
            "Reward added to user wallet",
            user_id=str(user_id),
            wallet_id=str(wallet.id),
            amount=str(amount),
            new_balance=str(new_balance),
        )
        return transaction
    
    async def debit_user_wallet(
        self,
        user_id: uuid.UUID,
        amount: Decimal,
        description: str,
        reference: str | None = None,
    ) -> Transaction:
        """
        Deduct AWX points from user's personal wallet with row-level locking.
        
        Bu metod kullanıcı puan harcadığında kullanılır:
        - Hediye çeki satın alma
        - Marketplace'de ürün alma
        """
        # Use FOR UPDATE to lock the row and prevent race conditions
        stmt = select(Wallet).where(
            Wallet.user_id == user_id,
            Wallet.wallet_type == WalletType.PERSONAL,
            Wallet.currency == "AWX",
        ).with_for_update()
        result = await self.db.execute(stmt)
        wallet = result.scalar_one_or_none()
        
        if not wallet:
            raise NotFoundError("User wallet not found")
        
        if not wallet.is_active:
            raise ValidationError("User wallet is not active")
        
        if wallet.balance < amount:
            raise ValidationError(
                f"Insufficient balance. Available: {wallet.balance}, Required: {amount}"
            )
        
        # Update balance (now safe from race conditions)
        new_balance = wallet.balance - amount
        wallet.balance = new_balance
        
        # Create debit transaction
        transaction = Transaction(
            wallet_id=wallet.id,
            transaction_type=TransactionType.DEBIT,
            amount=amount,
            balance_after=new_balance,
            status=TransactionStatus.COMPLETED,
            reference=reference,
            description=description,
        )
        self.db.add(transaction)
        
        await self.db.commit()
        await self.db.refresh(transaction)
        
        logger.info(
            "Points deducted from user wallet",
            user_id=str(user_id),
            wallet_id=str(wallet.id),
            amount=str(amount),
            new_balance=str(new_balance),
        )
        return transaction
    
    async def get_user_wallet_balance(self, user_id: uuid.UUID) -> dict:
        """Get user's AWX wallet balance summary."""
        wallet = await self.get_user_wallet(user_id, "AWX")
        
        if not wallet:
            return {
                "user_id": str(user_id),
                "currency": "AWX",
                "balance": "0.00",
                "has_wallet": False,
            }
        
        return {
            "user_id": str(user_id),
            "wallet_id": str(wallet.id),
            "currency": wallet.currency,
            "balance": str(wallet.balance),
            "is_active": wallet.is_active,
            "has_wallet": True,
        }
