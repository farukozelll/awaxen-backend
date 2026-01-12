"""
Admin Rewards Service

Cross-tenant wallet ve transaction yönetimi.
Admin kullanıcıların tüm organizasyonların wallet'larını görmesi için.
- Cross-tenant wallet listing
- System-wide transaction tracking
- Admin-level wallet statistics
"""
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.exceptions import NotFoundError
from src.modules.billing.models import (
    Transaction,
    TransactionStatus,
    TransactionType,
    Wallet,
    WalletType,
)
from src.modules.billing.schemas import WalletResponse, TransactionResponse
from src.core.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class AdminRewardsService:
    """Admin rewards management service - Cross-tenant operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # =========================================================================
    # CROSS-TENANT WALLET OPERATIONS
    # =========================================================================
    
    async def list_all_wallets(
        self,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        order: str = "desc",
        wallet_type: str | None = None,
        organization_id: str | None = None,
    ) -> dict:
        """
        Tüm AWX wallet'larını listele (Cross-tenant).
        
        Admin kullanıcısı tüm organizasyonların wallet'larını görebilir.
        """
        # Base query - tenant context bypass
        stmt = select(Wallet).options(
            selectinload(Wallet.organization),
            selectinload(Wallet.user),
        )
        count_stmt = select(func.count(Wallet.id))
        
        # Filters
        if wallet_type:
            try:
                wallet_type_enum = WalletType(wallet_type)
                stmt = stmt.where(Wallet.wallet_type == wallet_type_enum)
                count_stmt = count_stmt.where(Wallet.wallet_type == wallet_type_enum)
            except ValueError:
                logger.warning(f"Invalid wallet type: {wallet_type}")
                # Return empty result for invalid wallet type
                return {
                    "wallets": [],
                    "total": 0,
                    "page": page,
                    "page_size": page_size,
                    "sort_by": sort_by,
                    "order": order,
                }
        
        if organization_id:
            try:
                org_uuid = uuid.UUID(organization_id)
                stmt = stmt.where(Wallet.organization_id == org_uuid)
                count_stmt = count_stmt.where(Wallet.organization_id == org_uuid)
            except ValueError:
                logger.warning(f"Invalid organization ID: {organization_id}")
                return {
                    "wallets": [],
                    "total": 0,
                    "page": page,
                    "page_size": page_size,
                    "sort_by": sort_by,
                    "order": order,
                }
        
        # Sorting
        if hasattr(Wallet, sort_by):
            sort_column = getattr(Wallet, sort_by)
            if order.lower() == "desc":
                stmt = stmt.order_by(sort_column.desc())
            else:
                stmt = stmt.order_by(sort_column.asc())
        else:
            stmt = stmt.order_by(Wallet.created_at.desc())
        
        # Total count
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0
        
        # Pagination
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)
        
        result = await self.db.execute(stmt)
        wallets = result.scalars().all()
        
        # Build response
        wallet_responses = []
        for wallet in wallets:
            wallet_responses.append(WalletResponse.model_validate(wallet))
        
        return {
            "wallets": wallet_responses,
            "total": total,
            "page": page,
            "page_size": page_size,
            "sort_by": sort_by,
            "order": order,
        }
    
    async def get_wallet_detail(self, wallet_id: uuid.UUID) -> dict:
        """Belirli bir wallet'ın detaylarını getir (Cross-tenant)."""
        stmt = (
            select(Wallet)
            .options(
                selectinload(Wallet.organization),
                selectinload(Wallet.user),
            )
            .where(Wallet.id == wallet_id)
        )
        
        result = await self.db.execute(stmt)
        wallet = result.scalar_one_or_none()
        
        if not wallet:
            raise NotFoundError("Wallet not found")
        
        # Get wallet transactions
        transactions = await self.list_wallet_transactions(wallet_id)
        
        return {
            "wallet": WalletResponse.model_validate(wallet),
            "transactions": transactions,
            "transaction_count": len(transactions),
        }
    
    async def list_wallet_transactions(
        self,
        wallet_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        transaction_type: str | None = None,
    ) -> list[TransactionResponse]:
        """Wallet transaction'larını listele."""
        stmt = select(Transaction).where(Transaction.wallet_id == wallet_id)
        
        if transaction_type:
            try:
                tx_type = TransactionType(transaction_type)
                stmt = stmt.where(Transaction.transaction_type == tx_type)
            except ValueError:
                logger.warning(f"Invalid transaction type: {transaction_type}")
                return []
        
        stmt = stmt.order_by(Transaction.created_at.desc())
        
        # Pagination
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)
        
        result = await self.db.execute(stmt)
        transactions = result.scalars().all()
        
        return [TransactionResponse.model_validate(tx) for tx in transactions]
    
    # =========================================================================
    # SYSTEM-WIDE TRANSACTION OPERATIONS
    # =========================================================================
    
    async def list_all_transactions(
        self,
        page: int = 1,
        page_size: int = 20,
        transaction_type: str | None = None,
        wallet_type: str | None = None,
        organization_id: str | None = None,
        sort_by: str = "created_at",
        order: str = "desc",
    ) -> dict:
        """Tüm transaction'ları listele (Cross-tenant)."""
        stmt = (
            select(Transaction)
            .options(
                selectinload(Transaction.wallet).selectinload(Wallet.organization),
                selectinload(Transaction.wallet).selectinload(Wallet.user),
            )
        )
        count_stmt = select(func.count(Transaction.id))
        
        # Filters
        if transaction_type:
            try:
                tx_type = TransactionType(transaction_type)
                stmt = stmt.where(Transaction.transaction_type == tx_type)
                count_stmt = count_stmt.where(Transaction.transaction_type == tx_type)
            except ValueError:
                logger.warning(f"Invalid transaction type: {transaction_type}")
                return {
                    "transactions": [],
                    "total": 0,
                    "page": page,
                    "page_size": page_size,
                    "sort_by": sort_by,
                    "order": order,
                }
        
        if wallet_type:
            try:
                wallet_type_enum = WalletType(wallet_type)
                stmt = stmt.join(Wallet).where(Wallet.wallet_type == wallet_type_enum)
                count_stmt = count_stmt.join(Wallet).where(Wallet.wallet_type == wallet_type_enum)
            except ValueError:
                logger.warning(f"Invalid wallet type: {wallet_type}")
                return {
                    "transactions": [],
                    "total": 0,
                    "page": page,
                    "page_size": page_size,
                    "sort_by": sort_by,
                    "order": order,
                }
        
        if organization_id:
            try:
                org_uuid = uuid.UUID(organization_id)
                stmt = stmt.join(Wallet).where(Wallet.organization_id == org_uuid)
                count_stmt = count_stmt.join(Wallet).where(Wallet.organization_id == org_uuid)
            except ValueError:
                logger.warning(f"Invalid organization ID: {organization_id}")
                return {
                    "transactions": [],
                    "total": 0,
                    "page": page,
                    "page_size": page_size,
                    "sort_by": sort_by,
                    "order": order,
                }
        
        # Sorting
        if hasattr(Transaction, sort_by):
            sort_column = getattr(Transaction, sort_by)
            if order.lower() == "desc":
                stmt = stmt.order_by(sort_column.desc())
            else:
                stmt = stmt.order_by(sort_column.asc())
        else:
            stmt = stmt.order_by(Transaction.created_at.desc())
        
        # Total count
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0
        
        # Pagination
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)
        
        result = await self.db.execute(stmt)
        transactions = result.scalars().all()
        
        # Build response
        transaction_responses = [TransactionResponse.model_validate(tx) for tx in transactions]
        
        return {
            "transactions": transaction_responses,
            "total": total,
            "page": page,
            "page_size": page_size,
            "sort_by": sort_by,
            "order": order,
        }
    
    # =========================================================================
    # ADMIN WALLET STATISTICS
    # =========================================================================
    
    async def get_system_wallet_stats(self) -> dict:
        """Sistem genelinde wallet istatistikleri."""
        # Total wallets by type
        wallet_type_stats = {}
        for wallet_type in WalletType:
            stmt = select(func.count(Wallet.id)).where(Wallet.wallet_type == wallet_type)
            result = await self.db.execute(stmt)
            wallet_type_stats[wallet_type.value] = result.scalar() or 0
        
        # Total balance by type
        balance_stats = {}
        for wallet_type in WalletType:
            stmt = select(func.sum(Wallet.balance)).where(Wallet.wallet_type == wallet_type)
            result = await self.db.execute(stmt)
            balance = result.scalar() or 0
            balance_stats[wallet_type.value] = float(balance)
        
        # Organization distribution
        org_wallets_stmt = (
            select(
                Wallet.organization_id,
                func.count(Wallet.id).label("wallet_count"),
                func.sum(Wallet.balance).label("total_balance")
            )
            .where(Wallet.organization_id.isnot(None))
            .group_by(Wallet.organization_id)
            .order_by(func.sum(Wallet.balance).desc())
            .limit(10)  # Top 10 organizations
        )
        
        org_wallets_result = await self.db.execute(org_wallets_stmt)
        top_organizations = []
        
        for row in org_wallets_result:
            top_organizations.append({
                "organization_id": str(row.organization_id),
                "wallet_count": row.wallet_count,
                "total_balance": float(row.total_balance or 0),
            })
        
        return {
            "wallet_count_by_type": wallet_type_stats,
            "total_balance_by_type": balance_stats,
            "top_organizations_by_balance": top_organizations,
            "total_wallets": sum(wallet_type_stats.values()),
            "total_balance": sum(balance_stats.values()),
        }
    
    async def get_transaction_stats(self) -> dict:
        """Transaction istatistikleri."""
        # Transaction count by type
        tx_type_stats = {}
        for tx_type in TransactionType:
            stmt = select(func.count(Transaction.id)).where(Transaction.transaction_type == tx_type)
            result = await self.db.execute(stmt)
            tx_type_stats[tx_type.value] = result.scalar() or 0
        
        # Transaction volume by type
        volume_stats = {}
        for tx_type in TransactionType:
            stmt = select(func.sum(Transaction.amount)).where(Transaction.transaction_type == tx_type)
            result = await self.db.execute(stmt)
            volume = result.scalar() or 0
            volume_stats[tx_type.value] = float(volume)
        
        # Recent activity (last 7 days)
        from datetime import timedelta
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        
        recent_tx_stmt = select(func.count(Transaction.id)).where(
            Transaction.created_at >= seven_days_ago
        )
        recent_tx_result = await self.db.execute(recent_tx_stmt)
        recent_transactions = recent_tx_result.scalar() or 0
        
        return {
            "transaction_count_by_type": tx_type_stats,
            "transaction_volume_by_type": volume_stats,
            "recent_transactions_7_days": recent_transactions,
            "total_transactions": sum(tx_type_stats.values()),
            "total_volume": sum(volume_stats.values()),
        }
