"""
Admin Routes - Billing

Admin faturalama işlemleri - Fatura ve ödeme yönetimi.
NOT: AWX Wallet/Rewards işlemleri routes/rewards.py'de.

Tag: 13. 👑 Admin - Billing
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional

from src.modules.admin.dependencies import AdminServiceDep
from src.modules.auth.dependencies import require_role

router = APIRouter(tags=["13. 👑 Admin - Billing"])


@router.get(
    "/billing/invoices",
    summary="Tüm Faturaları Listele",
    description="Sistemdeki tüm faturaları listeler (Admin).",
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_all_invoices(
    admin_service: AdminServiceDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="Fatura durumu: pending, paid, cancelled"),
    sort_by: str = Query("created_at", description="Sıralama alanı"),
    order: str = Query("desc", description="Sıralama yönü: asc, desc"),
):
    """Tüm faturaları listele."""
    return {"message": "All invoices", "invoices": [], "total": 0, "page": page, "page_size": page_size}


@router.get(
    "/billing/organizations/{org_id}/invoices",
    summary="Organizasyon Faturalarını Listele",
    description="Bir organizasyonun tüm faturalarını listeler.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_organization_invoices(
    org_id: str,
    admin_service: AdminServiceDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
):
    """Organizasyon faturalarını listele."""
    return {"message": f"Organization {org_id} invoices", "invoices": [], "total": 0}


@router.get(
    "/billing/organizations/{org_id}/summary",
    summary="Organizasyon Fatura Özeti",
    description="Organizasyonun fatura ve ödeme özetini döner.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def get_organization_billing_summary(
    org_id: str,
    admin_service: AdminServiceDep,
):
    """Organizasyon fatura özeti."""
    return {
        "organization_id": org_id,
        "total_invoices": 0,
        "total_paid": 0,
        "total_pending": 0,
        "total_overdue": 0,
    }


@router.post(
    "/billing/invoices/{invoice_id}/void",
    summary="Fatura İptal Et",
    description="Bir faturayı iptal eder (Admin).",
    dependencies=[Depends(require_role(["admin"]))],
)
async def void_invoice(
    invoice_id: str,
    admin_service: AdminServiceDep,
):
    """Faturayı iptal et."""
    return {"message": f"Invoice {invoice_id} voided", "status": "voided"}
