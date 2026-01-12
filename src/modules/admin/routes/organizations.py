"""
Admin Routes - Organizations

Organizasyon CRUD işlemleri.
Tag: 10. 👑 Admin - Organizations
"""
import uuid
from fastapi import APIRouter, Depends, status, BackgroundTasks

from src.modules.admin.dependencies import AdminServiceDep
from src.modules.auth.dependencies import require_role
from src.modules.auth.schemas import (
    CreateOrganizationWithUserRequest,
    CreateOrganizationWithUserResponse,
    CreateOrganizationStep2Request,
    CreateOrganizationStep2Response,
    AdminOrganizationListResponse,
    AdminOrganizationDetailResponse,
    OrganizationModulesUpdate,
    OrganizationModulesUpdateRequest,
    OrganizationModulesUpdateResponse,
)

router = APIRouter(tags=["10. 👑 Admin - Organizations"])


@router.post(
    "/organizations",
    response_model=CreateOrganizationWithUserResponse,
    summary="Organizasyon Oluştur",
    description="Yeni organizasyon ve ilk kullanıcı (tenant owner) oluşturur.",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(["admin"]))],
)
async def create_organization(
    request: CreateOrganizationWithUserRequest,
    admin_service: AdminServiceDep,
    background_tasks: BackgroundTasks,
) -> CreateOrganizationWithUserResponse:
    return await admin_service.create_organization_with_user(request, background_tasks)


@router.post(
    "/organizations/{org_id}/modules",
    response_model=CreateOrganizationStep2Response,
    summary="Modül Ata",
    description="Organizasyona aktif modülleri atar.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def assign_organization_modules(
    org_id: uuid.UUID,
    request: OrganizationModulesUpdate,
    admin_service: AdminServiceDep,
) -> CreateOrganizationStep2Response:
    step2_request = CreateOrganizationStep2Request(
        organization_id=str(org_id),
        modules=request.modules,
    )
    return await admin_service.create_organization_step2(step2_request)


@router.put(
    "/organizations/{org_id}/modules",
    response_model=OrganizationModulesUpdateResponse,
    summary="Modülleri Güncelle",
    description="Organizasyonun modüllerini günceller.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def update_organization_modules(
    org_id: uuid.UUID,
    request: OrganizationModulesUpdateRequest,
    admin_service: AdminServiceDep,
) -> OrganizationModulesUpdateResponse:
    return await admin_service.update_organization_modules(
        org_id=org_id,
        modules=[m.model_dump() for m in request.modules],
    )


@router.get(
    "/organizations",
    response_model=AdminOrganizationListResponse,
    summary="Organizasyonları Listele",
    description="Tüm organizasyonları listeler.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_organizations(
    admin_service: AdminServiceDep,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    is_active: bool | None = None,
) -> AdminOrganizationListResponse:
    return await admin_service.list_all_organizations(
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
    )


@router.get(
    "/organizations/{org_id}",
    response_model=AdminOrganizationDetailResponse,
    summary="Organizasyon Detayı",
    description="Organizasyon detayını döner.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def get_organization(
    org_id: uuid.UUID,
    admin_service: AdminServiceDep,
) -> AdminOrganizationDetailResponse:
    return await admin_service.get_organization_detail(str(org_id))


@router.delete(
    "/organizations/{org_id}",
    summary="Organizasyon Sil",
    description="Organizasyonu siler.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def delete_organization(
    org_id: uuid.UUID,
    admin_service: AdminServiceDep,
    hard_delete: bool = False,
):
    return await admin_service.delete_organization(
        org_id=org_id,
        hard_delete=hard_delete,
    )


@router.patch(
    "/organizations/{org_id}/suspend",
    summary="Organizasyonu Askıya Al",
    description="Organizasyonu askıya alır.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def suspend_organization(
    org_id: uuid.UUID,
    admin_service: AdminServiceDep,
    reason: str | None = None,
):
    return await admin_service.suspend_organization(
        org_id=org_id,
        reason=reason,
    )


@router.patch(
    "/organizations/{org_id}/reactivate",
    summary="Organizasyonu Yeniden Aktifleştir",
    description="Askıya alınmış organizasyonu yeniden aktifleştirir.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def reactivate_organization(
    org_id: uuid.UUID,
    admin_service: AdminServiceDep,
):
    return await admin_service.reactivate_organization(
        org_id=org_id,
    )


@router.post(
    "/organizations/{org_id}/transfer-ownership",
    summary="Organizasyon Sahipliğini Devret",
    description="Organizasyon sahipliğini devreder.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def transfer_organization_ownership(
    org_id: uuid.UUID,
    new_owner_user_id: uuid.UUID,
    admin_service: AdminServiceDep,
):
    return await admin_service.transfer_ownership(
        org_id=org_id,
        new_owner_user_id=new_owner_user_id,
    )


@router.get(
    "/organizations/{org_id}/stats",
    summary="Organizasyon İstatistikleri",
    description="Organizasyon istatistiklerini döner.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def get_organization_stats(
    org_id: uuid.UUID,
    admin_service: AdminServiceDep,
):
    return await admin_service.get_organization_stats(str(org_id))
