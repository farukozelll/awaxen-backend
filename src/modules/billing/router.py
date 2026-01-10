"""
Billing Module - API Router

Endpoint'ler:
## User Endpoints (Kendi organizasyonu için)
- GET  /api/v1/billing/wallets              - Organizasyonun wallet'larını listele
- GET  /api/v1/billing/wallets/{wallet_id}  - Wallet detayı
- POST /api/v1/billing/wallets              - Yeni wallet oluştur
- POST /api/v1/billing/wallets/top-up       - Wallet'a para yükle

## Admin Endpoints (Tüm sistem için)
- GET  /api/v1/admin/wallets                              - Tüm wallet'ları listele
- GET  /api/v1/admin/organizations/{org_id}/wallets       - Organizasyonun wallet'ları
- GET  /api/v1/admin/organizations/{org_id}/wallet-summary - Organizasyon wallet özeti
- GET  /api/v1/admin/transactions                         - Tüm transaction'ları listele
"""
import uuid
from decimal import Decimal

from fastapi import APIRouter, status, Depends, Query
from sqlalchemy import select, func

from src.modules.billing.dependencies import BillingServiceDep
from src.modules.billing.models import InvoiceStatus, TransactionType, Wallet, Transaction
from src.modules.auth.dependencies import require_role, get_db_session
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

router = APIRouter(prefix="/billing", tags=["Billing"])
admin_router = APIRouter(prefix="/admin", tags=["Admin - Billing"])


# ============== User Personal Wallet (AWX) ==============

@router.get(
    "/my-wallet",
    summary="Kendi AWX Cüzdanım",
    description="""
Kullanıcının kişisel AWX puan cüzdanını döner.

**Dönen Bilgiler:**
- Cüzdan ID
- AWX bakiyesi
- Aktif durumu
    """,
)
async def get_my_wallet(
    service: BillingServiceDep,
):
    """Kullanıcının kendi AWX cüzdanını getir."""
    from src.modules.auth.dependencies import CurrentUser
    from fastapi import Depends
    
    # Note: Bu endpoint'e current_user dependency eklenecek
    # Şimdilik service üzerinden organization context'ten user_id alınamıyor
    # Bu endpoint tenant context yerine user context gerektirir
    return {
        "message": "Bu endpoint user context gerektirir. /users/me endpoint'inden wallet bilgisi alınabilir.",
        "alternative": "/api/v1/users/me",
    }


# ============== Organization (Company) Wallet Endpoints ==============

@router.get("/wallets", response_model=list[WalletResponse])
async def list_wallets(
    service: BillingServiceDep,
) -> list[WalletResponse]:
    """Organizasyonun wallet'larını listele."""
    wallets = await service.list_wallets()
    return [WalletResponse.model_validate(w) for w in wallets]


@router.get("/wallets/{wallet_id}", response_model=WalletWithTransactions)
async def get_wallet(
    wallet_id: uuid.UUID,
    service: BillingServiceDep,
) -> WalletWithTransactions:
    """Wallet detayını getir."""
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
    """Yeni wallet oluştur."""
    wallet = await service.create_wallet(data)
    return WalletResponse.model_validate(wallet)


@router.patch("/wallets/{wallet_id}", response_model=WalletResponse)
async def update_wallet(
    wallet_id: uuid.UUID,
    data: WalletUpdate,
    service: BillingServiceDep,
) -> WalletResponse:
    """Wallet güncelle."""
    wallet = await service.update_wallet(wallet_id, data)
    return WalletResponse.model_validate(wallet)


@router.post("/wallets/top-up", response_model=TransactionResponse)
async def top_up_wallet(
    request: TopUpRequest,
    service: BillingServiceDep,
) -> TransactionResponse:
    """Wallet'a para yükle."""
    transaction = await service.top_up_wallet(request)
    return TransactionResponse.model_validate(transaction)


# ============== User Transaction Endpoints ==============

@router.get("/transactions", response_model=list[TransactionResponse])
async def list_transactions(
    service: BillingServiceDep,
    wallet_id: uuid.UUID | None = None,
    transaction_type: TransactionType | None = None,
    limit: int = Query(default=100, le=500),
) -> list[TransactionResponse]:
    """Transaction'ları listele."""
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
    """Transaction detayını getir."""
    from src.core.exceptions import NotFoundError
    
    transaction = await service.get_transaction_by_id(transaction_id)
    if not transaction:
        raise NotFoundError("Transaction", transaction_id)
    return TransactionResponse.model_validate(transaction)


# ============== User Invoice Endpoints ==============

@router.get("/invoices", response_model=list[InvoiceResponse])
async def list_invoices(
    service: BillingServiceDep,
    status: InvoiceStatus | None = None,
    limit: int = Query(default=100, le=500),
) -> list[InvoiceResponse]:
    """Faturaları listele."""
    invoices = await service.list_invoices(status=status, limit=limit)
    return [InvoiceResponse.model_validate(i) for i in invoices]


@router.get("/invoices/{invoice_id}", response_model=InvoiceWithTransactions)
async def get_invoice(
    invoice_id: uuid.UUID,
    service: BillingServiceDep,
) -> InvoiceWithTransactions:
    """Fatura detayını getir."""
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
    """Yeni fatura oluştur."""
    invoice = await service.create_invoice(data)
    return InvoiceResponse.model_validate(invoice)


@router.patch("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: uuid.UUID,
    data: InvoiceUpdate,
    service: BillingServiceDep,
) -> InvoiceResponse:
    """Fatura güncelle."""
    invoice = await service.update_invoice(invoice_id, data)
    return InvoiceResponse.model_validate(invoice)


@router.post("/invoices/pay", response_model=TransactionResponse)
async def pay_invoice(
    request: PaymentRequest,
    service: BillingServiceDep,
) -> TransactionResponse:
    """Fatura öde."""
    transaction = await service.pay_invoice(request)
    return TransactionResponse.model_validate(transaction)


@router.post("/invoices/{invoice_id}/cancel", response_model=InvoiceResponse)
async def cancel_invoice(
    invoice_id: uuid.UUID,
    service: BillingServiceDep,
) -> InvoiceResponse:
    """Fatura iptal et."""
    invoice = await service.cancel_invoice(invoice_id)
    return InvoiceResponse.model_validate(invoice)


# ============== Admin Wallet Endpoints ==============

@admin_router.get(
    "/wallets",
    response_model=list[WalletResponse],
    summary="Tüm Wallet'ları Listele",
    description="""
**Sadece Admin rolü için.**

Sistemdeki tüm wallet'ları listeler (tüm organizasyonlar).

**Query Parametreleri:**
- `page` - Sayfa numarası (varsayılan: 1)
- `page_size` - Sayfa başına kayıt (varsayılan: 20, max: 100)
- `currency` - Para birimi filtresi (AWX, TRY, USD)
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def admin_list_all_wallets(
    db = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, le=100),
    currency: str | None = None,
):
    """Tüm wallet'ları listele (Admin)."""
    stmt = select(Wallet)
    
    if currency:
        stmt = stmt.where(Wallet.currency == currency.upper())
    
    # Pagination
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size).order_by(Wallet.organization_id, Wallet.currency)
    
    result = await db.execute(stmt)
    wallets = result.scalars().all()
    
    return [WalletResponse.model_validate(w) for w in wallets]


@admin_router.get(
    "/organizations/{org_id}/wallets",
    response_model=list[WalletResponse],
    summary="Organizasyon Wallet'larını Listele",
    description="""
**Sadece Admin rolü için.**

Belirtilen organizasyonun tüm wallet'larını listeler.
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def admin_get_organization_wallets(
    org_id: str,
    db = Depends(get_db_session),
):
    """Organizasyonun wallet'larını getir (Admin)."""
    from src.core.exceptions import NotFoundError
    
    try:
        org_uuid = uuid.UUID(org_id)
    except ValueError:
        raise NotFoundError("Organization", org_id)
    
    stmt = select(Wallet).where(Wallet.organization_id == org_uuid).order_by(Wallet.currency)
    result = await db.execute(stmt)
    wallets = result.scalars().all()
    
    return [WalletResponse.model_validate(w) for w in wallets]


@admin_router.get(
    "/organizations/{org_id}/wallet-summary",
    summary="Organizasyon Wallet Özeti",
    description="""
**Sadece Admin rolü için.**

Belirtilen organizasyonun wallet özetini döner.

**Dönen Bilgiler:**
- Toplam bakiye (para birimi bazında)
- Wallet sayısı
- Son işlemler
- Toplam giriş/çıkış
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def admin_get_organization_wallet_summary(
    org_id: str,
    db = Depends(get_db_session),
):
    """Organizasyonun wallet özetini getir (Admin)."""
    from src.core.exceptions import NotFoundError
    from datetime import datetime, timedelta, timezone
    
    try:
        org_uuid = uuid.UUID(org_id)
    except ValueError:
        raise NotFoundError("Organization", org_id)
    
    # Wallet'ları getir
    wallet_stmt = select(Wallet).where(Wallet.organization_id == org_uuid)
    wallet_result = await db.execute(wallet_stmt)
    wallets = wallet_result.scalars().all()
    
    if not wallets:
        return {
            "organization_id": org_id,
            "wallet_count": 0,
            "balances": {},
            "total_credit": "0.00",
            "total_debit": "0.00",
            "recent_transactions": [],
        }
    
    # Bakiye özeti
    balances = {}
    wallet_ids = []
    for w in wallets:
        balances[w.currency] = str(w.balance)
        wallet_ids.append(w.id)
    
    # Son 30 gün transaction'ları
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    
    # Toplam credit
    credit_stmt = (
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .where(
            Transaction.wallet_id.in_(wallet_ids),
            Transaction.transaction_type == TransactionType.CREDIT,
            Transaction.created_at >= thirty_days_ago,
        )
    )
    credit_result = await db.execute(credit_stmt)
    total_credit = credit_result.scalar() or Decimal("0")
    
    # Toplam debit
    debit_stmt = (
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .where(
            Transaction.wallet_id.in_(wallet_ids),
            Transaction.transaction_type == TransactionType.DEBIT,
            Transaction.created_at >= thirty_days_ago,
        )
    )
    debit_result = await db.execute(debit_stmt)
    total_debit = debit_result.scalar() or Decimal("0")
    
    # Son 10 transaction
    recent_stmt = (
        select(Transaction)
        .where(Transaction.wallet_id.in_(wallet_ids))
        .order_by(Transaction.created_at.desc())
        .limit(10)
    )
    recent_result = await db.execute(recent_stmt)
    recent_transactions = recent_result.scalars().all()
    
    return {
        "organization_id": org_id,
        "wallet_count": len(wallets),
        "balances": balances,
        "total_credit_30d": str(total_credit),
        "total_debit_30d": str(total_debit),
        "recent_transactions": [
            {
                "id": str(t.id),
                "type": t.transaction_type.value,
                "amount": str(t.amount),
                "description": t.description,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in recent_transactions
        ],
    }


@admin_router.get(
    "/wallets/{wallet_id}",
    response_model=WalletWithTransactions,
    summary="Wallet Detayı",
    description="""
**Sadece Admin rolü için.**

Herhangi bir wallet'ın detayını getirir.
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def admin_get_wallet(
    wallet_id: str,
    db = Depends(get_db_session),
) -> WalletWithTransactions:
    """Wallet detayını getir (Admin)."""
    from src.core.exceptions import NotFoundError
    from sqlalchemy.orm import selectinload
    
    try:
        wallet_uuid = uuid.UUID(wallet_id)
    except ValueError:
        raise NotFoundError("Wallet", wallet_id)
    
    stmt = (
        select(Wallet)
        .options(selectinload(Wallet.transactions))
        .where(Wallet.id == wallet_uuid)
    )
    result = await db.execute(stmt)
    wallet = result.scalar_one_or_none()
    
    if not wallet:
        raise NotFoundError("Wallet", wallet_id)
    
    return WalletWithTransactions.model_validate(wallet)


@admin_router.get(
    "/transactions",
    response_model=list[TransactionResponse],
    summary="Tüm Transaction'ları Listele",
    description="""
**Sadece Admin rolü için.**

Sistemdeki tüm transaction'ları listeler.

**Query Parametreleri:**
- `wallet_id` - Belirli bir wallet'ın transaction'ları
- `organization_id` - Belirli bir organizasyonun transaction'ları
- `transaction_type` - İşlem tipi (credit, debit)
- `page` - Sayfa numarası
- `page_size` - Sayfa başına kayıt
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def admin_list_all_transactions(
    db = Depends(get_db_session),
    wallet_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    transaction_type: TransactionType | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, le=100),
):
    """Tüm transaction'ları listele (Admin)."""
    stmt = select(Transaction)
    
    if wallet_id:
        stmt = stmt.where(Transaction.wallet_id == wallet_id)
    
    if organization_id:
        stmt = stmt.join(Wallet).where(Wallet.organization_id == organization_id)
    
    if transaction_type:
        stmt = stmt.where(Transaction.transaction_type == transaction_type)
    
    # Pagination
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size).order_by(Transaction.created_at.desc())
    
    result = await db.execute(stmt)
    transactions = result.scalars().all()
    
    return [TransactionResponse.model_validate(t) for t in transactions]
