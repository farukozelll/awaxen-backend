"""
Billing Module - Business Logic Service
"""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.exceptions import ConflictError, NotFoundError, ValidationError
from src.core.logging import get_logger
from src.modules.billing.models import (
    Invoice,
    InvoiceStatus,
    Transaction,
    TransactionStatus,
    TransactionType,
    Wallet,
)
from src.modules.billing.schemas import (
    InvoiceCreate,
    InvoiceUpdate,
    PaymentRequest,
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
    
    # ============== Wallet Operations ==============
    
    async def get_wallet_by_id(self, wallet_id: uuid.UUID) -> Wallet | None:
        """Get wallet by ID within organization."""
        stmt = select(Wallet).where(
            Wallet.id == wallet_id,
            Wallet.organization_id == self.organization_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_wallet_by_currency(self, currency: str) -> Wallet | None:
        """Get wallet by currency within organization."""
        stmt = select(Wallet).where(
            Wallet.organization_id == self.organization_id,
            Wallet.currency == currency.upper(),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_wallets(self) -> Sequence[Wallet]:
        """List all wallets for organization."""
        stmt = (
            select(Wallet)
            .where(Wallet.organization_id == self.organization_id)
            .order_by(Wallet.currency)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def create_wallet(self, data: WalletCreate) -> Wallet:
        """Create a new wallet."""
        currency = data.currency.upper()
        
        existing = await self.get_wallet_by_currency(currency)
        if existing:
            raise ConflictError(f"Wallet with currency '{currency}' already exists")
        
        wallet = Wallet(
            organization_id=self.organization_id,
            currency=currency,
            credit_limit=data.credit_limit,
            balance=Decimal("0.00"),
        )
        self.db.add(wallet)
        await self.db.commit()
        await self.db.refresh(wallet)
        
        logger.info(
            "Wallet created",
            wallet_id=str(wallet.id),
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
        """Add funds to wallet."""
        wallet = await self.get_wallet_by_id(request.wallet_id)
        if not wallet:
            raise NotFoundError("Wallet", request.wallet_id)
        
        if not wallet.is_active:
            raise ValidationError("Wallet is not active")
        
        # Update balance
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
        invoice_id: uuid.UUID | None = None,
        reference: str | None = None,
    ) -> Transaction:
        """Deduct funds from wallet."""
        wallet = await self.get_wallet_by_id(wallet_id)
        if not wallet:
            raise NotFoundError("Wallet", wallet_id)
        
        if not wallet.is_active:
            raise ValidationError("Wallet is not active")
        
        # Check available balance
        if wallet.available_balance < amount:
            raise ValidationError(
                f"Insufficient balance. Available: {wallet.available_balance}, Required: {amount}"
            )
        
        # Update balance
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
            invoice_id=invoice_id,
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
    
    # ============== Invoice Operations ==============
    
    async def get_invoice_by_id(self, invoice_id: uuid.UUID) -> Invoice | None:
        """Get invoice by ID within organization."""
        stmt = (
            select(Invoice)
            .options(selectinload(Invoice.transactions))
            .where(
                Invoice.id == invoice_id,
                Invoice.organization_id == self.organization_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_invoice_by_number(self, invoice_number: str) -> Invoice | None:
        """Get invoice by number within organization."""
        stmt = select(Invoice).where(
            Invoice.invoice_number == invoice_number,
            Invoice.organization_id == self.organization_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_invoices(
        self,
        status: InvoiceStatus | None = None,
        limit: int = 100,
    ) -> Sequence[Invoice]:
        """List invoices with optional filters."""
        stmt = select(Invoice).where(Invoice.organization_id == self.organization_id)
        
        if status:
            stmt = stmt.where(Invoice.status == status)
        
        stmt = stmt.order_by(Invoice.issue_date.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def create_invoice(self, data: InvoiceCreate) -> Invoice:
        """Create a new invoice."""
        existing = await self.get_invoice_by_number(data.invoice_number)
        if existing:
            raise ConflictError(f"Invoice '{data.invoice_number}' already exists")
        
        # Convert line items to dict
        line_items = None
        if data.line_items:
            line_items = [item.model_dump() for item in data.line_items]
        
        invoice = Invoice(
            organization_id=self.organization_id,
            invoice_number=data.invoice_number,
            issue_date=data.issue_date,
            due_date=data.due_date,
            subtotal=data.subtotal,
            tax_amount=data.tax_amount,
            discount_amount=data.discount_amount,
            total_amount=data.total_amount,
            currency=data.currency,
            status=data.status,
            description=data.description,
            notes=data.notes,
            period_start=data.period_start,
            period_end=data.period_end,
            line_items=line_items,
        )
        self.db.add(invoice)
        await self.db.commit()
        await self.db.refresh(invoice)
        
        logger.info(
            "Invoice created",
            invoice_id=str(invoice.id),
            number=invoice.invoice_number,
            total=str(invoice.total_amount),
        )
        return invoice
    
    async def update_invoice(self, invoice_id: uuid.UUID, data: InvoiceUpdate) -> Invoice:
        """Update an invoice."""
        invoice = await self.get_invoice_by_id(invoice_id)
        if not invoice:
            raise NotFoundError("Invoice", invoice_id)
        
        # Cannot update paid invoices
        if invoice.status == InvoiceStatus.PAID:
            raise ValidationError("Cannot update a paid invoice")
        
        update_data = data.model_dump(exclude_unset=True)
        
        # Convert line items
        if "line_items" in update_data and update_data["line_items"]:
            update_data["line_items"] = [
                item.model_dump() if hasattr(item, "model_dump") else item
                for item in update_data["line_items"]
            ]
        
        for field, value in update_data.items():
            setattr(invoice, field, value)
        
        await self.db.commit()
        await self.db.refresh(invoice)
        return invoice
    
    async def pay_invoice(self, request: PaymentRequest) -> Transaction:
        """Pay an invoice from wallet."""
        invoice = await self.get_invoice_by_id(request.invoice_id)
        if not invoice:
            raise NotFoundError("Invoice", request.invoice_id)
        
        if invoice.status == InvoiceStatus.PAID:
            raise ValidationError("Invoice is already paid")
        
        if invoice.status == InvoiceStatus.CANCELLED:
            raise ValidationError("Cannot pay a cancelled invoice")
        
        # Get wallet for invoice currency
        wallet = await self.get_wallet_by_currency(invoice.currency)
        if not wallet:
            raise ValidationError(f"No wallet found for currency {invoice.currency}")
        
        # Validate payment amount
        remaining = invoice.balance_due
        if request.amount > remaining:
            raise ValidationError(
                f"Payment amount ({request.amount}) exceeds balance due ({remaining})"
            )
        
        # Debit wallet
        transaction = await self.debit_wallet(
            wallet_id=wallet.id,
            amount=request.amount,
            description=f"Payment for invoice {invoice.invoice_number}",
            invoice_id=invoice.id,
            reference=request.reference,
        )
        
        # Update invoice
        invoice.paid_amount += request.amount
        if invoice.paid_amount >= invoice.total_amount:
            invoice.status = InvoiceStatus.PAID
            invoice.paid_at = datetime.now(timezone.utc)
        
        await self.db.commit()
        
        logger.info(
            "Invoice payment processed",
            invoice_id=str(invoice.id),
            amount=str(request.amount),
            status=invoice.status,
        )
        return transaction
    
    async def cancel_invoice(self, invoice_id: uuid.UUID) -> Invoice:
        """Cancel an invoice."""
        invoice = await self.get_invoice_by_id(invoice_id)
        if not invoice:
            raise NotFoundError("Invoice", invoice_id)
        
        if invoice.status == InvoiceStatus.PAID:
            raise ValidationError("Cannot cancel a paid invoice")
        
        invoice.status = InvoiceStatus.CANCELLED
        await self.db.commit()
        await self.db.refresh(invoice)
        
        logger.info("Invoice cancelled", invoice_id=str(invoice_id))
        return invoice
