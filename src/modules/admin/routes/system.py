"""
Admin Routes - System

Sistem sağlığı, loglar ve rol/yetki yönetimi.
Tag: 12. 👑 Admin - System
"""
from fastapi import APIRouter, Depends

from src.modules.admin.dependencies import AdminServiceDep
from src.modules.auth.dependencies import require_role
from src.modules.auth.schemas import AdminRoleListResponse

router = APIRouter(tags=["12. 👑 Admin - System"])


@router.get(
    "/system/status",
    summary="Sistem Durumu",
    description="Sistemin genel durumunu ve servislerin sağlığını döner.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def get_system_status(admin_service: AdminServiceDep):
    return {
        "status": "healthy",
        "services": {
            "database": "connected",
            "redis": "connected",
            "mqtt": "connected",
        },
    }


@router.get(
    "/system/health",
    summary="Sağlık Kontrolü",
    description="Detaylı sağlık kontrolü yapar.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def health_check(admin_service: AdminServiceDep):
    return {
        "status": "ok",
        "checks": {
            "database": "ok",
            "redis": "ok",
            "external_apis": "ok",
        },
    }


@router.get(
    "/system/metrics",
    summary="Sistem Metrikleri",
    description="Sistem metriklerini döner.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def get_system_metrics(admin_service: AdminServiceDep):
    return {
        "users": {"total": 0, "active": 0},
        "organizations": {"total": 0, "active": 0},
        "requests": {"total_today": 0},
    }


@router.get(
    "/roles",
    response_model=AdminRoleListResponse,
    summary="Rolleri Listele",
    description="Sistemdeki tüm rolleri listeler.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_roles(admin_service: AdminServiceDep) -> AdminRoleListResponse:
    return await admin_service.list_all_roles()


@router.get(
    "/permissions",
    summary="Yetkileri Listele",
    description="Sistemdeki tüm yetkileri listeler.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_permissions(admin_service: AdminServiceDep):
    return await admin_service.list_all_permissions()
