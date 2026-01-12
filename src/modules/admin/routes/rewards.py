"""
Admin Routes - Rewards

Admin AWX puan ve cüzdan yönetimi.
Tag: 14. 👑 Admin - Rewards
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.modules.admin.services import AdminRewardsServiceDep
from src.modules.auth.dependencies import require_role

router = APIRouter(tags=["14. 👑 Admin - Rewards"])


@router.get(
    "/rewards/wallets",
    summary="Tüm AWX Wallet'ları Listele",
    description="Sistemdeki tüm AWX cüzdanlarını listeler (Admin - Cross-tenant).",
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_all_wallets(
    rewards_service: AdminRewardsServiceDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at", description="Sıralama alanı"),
    order: str = Query("desc", description="Sıralama yönü: asc, desc"),
    wallet_type: str | None = Query(None, description="Wallet tipi: company, personal"),
    organization_id: str | None = Query(None, description="Organizasyon ID filtresi"),
):
    """Tüm AWX wallet'ları listele (Cross-tenant)."""
    try:
        return await rewards_service.list_all_wallets(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            order=order,
            wallet_type=wallet_type,
            organization_id=organization_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Wallet listesi alınamadı: {e!s}"
        ) from e


@router.get(
    "/rewards/organizations/{org_id}/wallets",
    summary="Organizasyon AWX Wallet'larını Listele",
    description="Bir organizasyonun tüm AWX cüzdanlarını listeler.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_organization_wallets(
    org_id: uuid.UUID,
    rewards_service: AdminRewardsServiceDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Organizasyon AWX wallet'larını listele."""
    try:
        return await rewards_service.list_all_wallets(
            page=page,
            page_size=page_size,
            organization_id=str(org_id),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Organizasyon wallet'ları alınamadı: {e!s}"
        )


@router.get(
    "/rewards/organizations/{org_id}/summary",
    summary="Organizasyon AWX Özeti",
    description="Organizasyonun AWX puan özetini döner.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def get_organization_rewards_summary(
    org_id: uuid.UUID,
    rewards_service: AdminRewardsServiceDep,
):
    """Organizasyon AWX özeti."""
    try:
        # Get organization wallets
        org_wallets = await rewards_service.list_all_wallets(
            page=1,
            page_size=1000,  # Large page size to get all
            organization_id=str(org_id),
        )
        
        # Calculate summary
        total_wallets = org_wallets["total"]
        total_balance = sum(wallet.balance for wallet in org_wallets["wallets"])
        
        # Get recent transactions for this organization
        recent_tx = await rewards_service.list_all_transactions(
            page=1,
            page_size=100,
            organization_id=str(org_id),
        )
        
        # Calculate credit/debit totals
        total_credits = sum(
            tx.amount for tx in recent_tx["transactions"] 
            if tx.transaction_type == "credit"
        )
        total_debits = sum(
            tx.amount for tx in recent_tx["transactions"] 
            if tx.transaction_type == "debit"
        )
        
        return {
            "organization_id": str(org_id),
            "total_wallets": total_wallets,
            "total_balance": float(total_balance),
            "total_credits": float(total_credits),
            "total_debits": float(total_debits),
            "transaction_count": recent_tx["total"],
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Organizasyon özeti alınamadı: {e!s}"
        )


@router.get(
    "/rewards/wallets/{wallet_id}",
    summary="Wallet Detayı",
    description="Belirli bir AWX cüzdanının detaylarını döner.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def get_wallet_detail(
    wallet_id: uuid.UUID,
    rewards_service: AdminRewardsServiceDep,
):
    """Wallet detayı."""
    try:
        return await rewards_service.get_wallet_detail(wallet_id)
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Wallet bulunamadı"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Wallet detayı alınamadı: {e!s}"
        )


@router.get(
    "/rewards/transactions",
    summary="Tüm AWX Transaction'ları Listele",
    description="Sistemdeki tüm AWX işlemlerini listeler (Cross-tenant).",
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_all_transactions(
    rewards_service: AdminRewardsServiceDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    transaction_type: str | None = Query(None, description="İşlem tipi: credit, debit"),
    wallet_type: str | None = Query(None, description="Wallet tipi: company, personal"),
    organization_id: str | None = Query(None, description="Organizasyon ID filtresi"),
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
):
    """Tüm AWX transaction'ları listele (Cross-tenant)."""
    try:
        return await rewards_service.list_all_transactions(
            page=page,
            page_size=page_size,
            transaction_type=transaction_type,
            wallet_type=wallet_type,
            organization_id=organization_id,
            sort_by=sort_by,
            order=order,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transaction listesi alınamadı: {e!s}"
        )


@router.post(
    "/rewards/wallets/{wallet_id}/adjust",
    summary="Wallet Bakiye Düzelt",
    description="Admin tarafından manuel bakiye düzeltmesi.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def adjust_wallet_balance(
    wallet_id: uuid.UUID,
    rewards_service: AdminRewardsServiceDep,
):
    """Wallet bakiyesini düzelt."""
    try:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Manuel bakiye düzeltme henüz implement edilmedi"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bakiye düzeltme yapılamadı: {e!s}"
        )


@router.get(
    "/rewards/stats/wallets",
    summary="Sistem Wallet İstatistikleri",
    description="Tüm sistemdeki wallet istatistiklerini döner.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def get_wallet_stats(
    rewards_service: AdminRewardsServiceDep,
):
    """Sistem wallet istatistikleri."""
    try:
        return await rewards_service.get_system_wallet_stats()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Wallet istatistikleri alınamadı: {e!s}"
        )


@router.get(
    "/rewards/stats/transactions",
    summary="Sistem Transaction İstatistikleri",
    description="Tüm sistemdeki transaction istatistiklerini döner.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def get_transaction_stats(
    rewards_service: AdminRewardsServiceDep,
):
    """Sistem transaction istatistikleri."""
    try:
        return await rewards_service.get_transaction_stats()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transaction istatistikleri alınamadı: {e!s}"
        )
