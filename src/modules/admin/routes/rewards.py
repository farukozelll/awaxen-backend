"""
Admin Routes - Rewards

Admin AWX puan ve cüzdan yönetimi.
Tag: 14. 👑 Admin - Rewards
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional

from src.modules.admin.dependencies import AdminServiceDep
from src.modules.auth.dependencies import require_role

router = APIRouter(tags=["14. 👑 Admin - Rewards"])


@router.get(
    "/rewards/wallets",
    summary="Tüm AWX Wallet'ları Listele",
    description="Sistemdeki tüm AWX cüzdanlarını listeler (Admin).",
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_all_wallets(
    admin_service: AdminServiceDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at", description="Sıralama alanı"),
    order: str = Query("desc", description="Sıralama yönü: asc, desc"),
):
    """Tüm AWX wallet'ları listele."""
    return {"message": "All wallets", "wallets": [], "total": 0, "page": page, "page_size": page_size}


@router.get(
    "/rewards/organizations/{org_id}/wallets",
    summary="Organizasyon AWX Wallet'larını Listele",
    description="Bir organizasyonun tüm AWX cüzdanlarını listeler.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_organization_wallets(
    org_id: str,
    admin_service: AdminServiceDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Organizasyon AWX wallet'larını listele."""
    return {"message": f"Organization {org_id} wallets", "wallets": [], "total": 0}


@router.get(
    "/rewards/organizations/{org_id}/summary",
    summary="Organizasyon AWX Özeti",
    description="Organizasyonun AWX puan özetini döner.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def get_organization_rewards_summary(
    org_id: str,
    admin_service: AdminServiceDep,
):
    """Organizasyon AWX özeti."""
    return {
        "organization_id": org_id,
        "total_awx_distributed": 0,
        "total_awx_spent": 0,
        "total_awx_balance": 0,
        "active_streaks": 0,
    }


@router.get(
    "/rewards/wallets/{wallet_id}",
    summary="Wallet Detayı",
    description="Belirli bir AWX cüzdanının detaylarını döner.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def get_wallet_detail(
    wallet_id: str,
    admin_service: AdminServiceDep,
):
    """Wallet detayı."""
    return {"wallet_id": wallet_id, "balance": 0, "transactions": []}


@router.get(
    "/rewards/transactions",
    summary="Tüm AWX Transaction'ları Listele",
    description="Sistemdeki tüm AWX işlemlerini listeler.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_all_transactions(
    admin_service: AdminServiceDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    transaction_type: Optional[str] = Query(None, description="İşlem tipi: earn, spend, transfer"),
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
):
    """Tüm AWX transaction'ları listele."""
    return {"message": "All transactions", "transactions": [], "total": 0}


@router.post(
    "/rewards/wallets/{wallet_id}/adjust",
    summary="Wallet Bakiye Düzelt",
    description="Admin tarafından manuel bakiye düzeltmesi.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def adjust_wallet_balance(
    wallet_id: str,
    admin_service: AdminServiceDep,
):
    """Wallet bakiyesini düzelt."""
    return {"message": f"Wallet {wallet_id} balance adjusted", "new_balance": 0}
