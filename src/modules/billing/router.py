"""
Billing Module - API Router
"""
import uuid

from fastapi import APIRouter, status

from src.modules.billing.dependencies import BillingServiceDep
from src.modules.billing.models import InvoiceStatus, TransactionType
from src.modules.billing.schemas import (
    InvoiceCreate,
    InvoiceResponse,
    InvoiceUpdate,
    InvoiceWithTransactions,
    PaymentRequest,
    TopUpRequest,
    TransactionResponse,
    WalletCreate,
    WalletResponse,
    WalletUpdate,
    WalletWithTransactions,
)

router = APIRouter(prefix="/billing", tags=["billing"])


# ============== Wallets ==============

@router.get("/wallets", response_model=list[WalletResponse])
async def list_wallets(
    service: BillingServiceDep,
) -> list[WalletResponse]:
    """List all wallets for the organization."""
    wallets = await service.list_wallets()
    return [WalletResponse.model_validate(w) for w in wallets]


@router.get("/wallets/{wallet_id}", response_model=WalletWithTransactions)
async def get_wallet(
    wallet_id: uuid.UUID,
    service: BillingServiceDep,
) -> WalletWithTransactions:
    """Get wallet by ID with recent transactions."""
    from src.core.exceptions import NotFoundError
    
    wallet = await service.get_wallet_by_id(wallet_id)
    if not wallet:
        raise NotFoundError("Wallet", wallet_id)
    return WalletWithTransactions.model_validate(wallet)


@router.post(
    "/wallets",
    response_model=WalletResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_wallet(
    data: WalletCreate,
    service: BillingServiceDep,
) -> WalletResponse:
    """Create a new wallet."""
    wallet = await service.create_wallet(data)
    return WalletResponse.model_validate(wallet)


@router.patch("/wallets/{wallet_id}", response_model=WalletResponse)
async def update_wallet(
    wallet_id: uuid.UUID,
    data: WalletUpdate,
    service: BillingServiceDep,
) -> WalletResponse:
    """Update a wallet."""
    wallet = await service.update_wallet(wallet_id, data)
    return WalletResponse.model_validate(wallet)


@router.post("/wallets/top-up", response_model=TransactionResponse)
async def top_up_wallet(
    request: TopUpRequest,
    service: BillingServiceDep,
) -> TransactionResponse:
    """Add funds to a wallet."""
    transaction = await service.top_up_wallet(request)
    return TransactionResponse.model_validate(transaction)


# ============== Transactions ==============

@router.get("/transactions", response_model=list[TransactionResponse])
async def list_transactions(
    service: BillingServiceDep,
    wallet_id: uuid.UUID | None = None,
    transaction_type: TransactionType | None = None,
    limit: int = 100,
) -> list[TransactionResponse]:
    """List transactions with optional filters."""
    transactions = await service.list_transactions(
        wallet_id=wallet_id,
        transaction_type=transaction_type,
        limit=limit,
    )
    return [TransactionResponse.model_validate(t) for t in transactions]


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: uuid.UUID,
    service: BillingServiceDep,
) -> TransactionResponse:
    """Get transaction by ID."""
    from src.core.exceptions import NotFoundError
    
    transaction = await service.get_transaction_by_id(transaction_id)
    if not transaction:
        raise NotFoundError("Transaction", transaction_id)
    return TransactionResponse.model_validate(transaction)


# ============== Invoices ==============

@router.get("/invoices", response_model=list[InvoiceResponse])
async def list_invoices(
    service: BillingServiceDep,
    status: InvoiceStatus | None = None,
    limit: int = 100,
) -> list[InvoiceResponse]:
    """List invoices with optional filters."""
    invoices = await service.list_invoices(status=status, limit=limit)
    return [InvoiceResponse.model_validate(i) for i in invoices]


@router.get("/invoices/{invoice_id}", response_model=InvoiceWithTransactions)
async def get_invoice(
    invoice_id: uuid.UUID,
    service: BillingServiceDep,
) -> InvoiceWithTransactions:
    """Get invoice by ID with payment transactions."""
    from src.core.exceptions import NotFoundError
    
    invoice = await service.get_invoice_by_id(invoice_id)
    if not invoice:
        raise NotFoundError("Invoice", invoice_id)
    return InvoiceWithTransactions.model_validate(invoice)


@router.post(
    "/invoices",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invoice(
    data: InvoiceCreate,
    service: BillingServiceDep,
) -> InvoiceResponse:
    """Create a new invoice."""
    invoice = await service.create_invoice(data)
    return InvoiceResponse.model_validate(invoice)


@router.patch("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: uuid.UUID,
    data: InvoiceUpdate,
    service: BillingServiceDep,
) -> InvoiceResponse:
    """Update an invoice."""
    invoice = await service.update_invoice(invoice_id, data)
    return InvoiceResponse.model_validate(invoice)


@router.post("/invoices/pay", response_model=TransactionResponse)
async def pay_invoice(
    request: PaymentRequest,
    service: BillingServiceDep,
) -> TransactionResponse:
    """Pay an invoice from wallet."""
    transaction = await service.pay_invoice(request)
    return TransactionResponse.model_validate(transaction)


@router.post("/invoices/{invoice_id}/cancel", response_model=InvoiceResponse)
async def cancel_invoice(
    invoice_id: uuid.UUID,
    service: BillingServiceDep,
) -> InvoiceResponse:
    """Cancel an invoice."""
    invoice = await service.cancel_invoice(invoice_id)
    return InvoiceResponse.model_validate(invoice)
