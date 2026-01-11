"""
Admin Routes - Users

Kullanıcı yönetimi işlemleri.
Tag: 11. 👑 Admin - Users
"""
import uuid
from fastapi import APIRouter, Depends, status

from src.modules.admin.dependencies import AdminServiceDep
from src.modules.auth.dependencies import require_role, CurrentUser
from src.modules.auth.schemas import (
    AdminUserListResponse,
    AssignRoleToUserRequest,
    AssignRoleToUserResponse,
    ImpersonateUserRequest,
    ImpersonateUserResponse,
    AddUserToOrganizationRequest,
    AddUserToOrganizationResponse,
)

router = APIRouter(tags=["11. 👑 Admin - Users"])


@router.get(
    "/users",
    response_model=AdminUserListResponse,
    summary="Tüm Kullanıcıları Listele",
    description="Sistemdeki tüm kullanıcıları listeler.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_all_users(
    admin_service: AdminServiceDep,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    is_active: bool | None = None,
) -> AdminUserListResponse:
    return await admin_service.list_all_users(
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
    )


@router.get(
    "/organizations/{org_id}/users",
    response_model=AdminUserListResponse,
    summary="Organizasyon Kullanıcıları",
    description="Organizasyondaki kullanıcıları listeler.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_organization_users(
    org_id: str,
    admin_service: AdminServiceDep,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> AdminUserListResponse:
    return await admin_service.list_organization_users(
        organization_id=org_id,
        page=page,
        page_size=page_size,
        search=search,
        role=role,
        is_active=is_active,
    )


@router.post(
    "/organizations/{org_id}/users",
    response_model=AddUserToOrganizationResponse,
    summary="Kullanıcı Ekle",
    description="Organizasyona kullanıcı ekler.",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(["admin"]))],
)
async def add_user_to_organization(
    org_id: str,
    request: AddUserToOrganizationRequest,
    admin_service: AdminServiceDep,
) -> AddUserToOrganizationResponse:
    request.organization_id = org_id
    return await admin_service.add_user_to_organization(request)


@router.post(
    "/users/{user_id}/role",
    response_model=AssignRoleToUserResponse,
    summary="Kullanıcıya Rol Ata",
    description="Kullanıcıya belirli bir organizasyonda rol atar.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def assign_role_to_user(
    user_id: str,
    request: AssignRoleToUserRequest,
    admin_service: AdminServiceDep,
) -> AssignRoleToUserResponse:
    return await admin_service.assign_role_to_user(user_id, request)


@router.post(
    "/users/{user_id}/revoke-sessions",
    summary="Kullanıcı Oturumlarını Sonlandır",
    description="Kullanıcının tüm aktif oturumlarını iptal eder.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def revoke_user_sessions(
    user_id: str,
    admin_service: AdminServiceDep,
    revoke_auth0: bool = True,
):
    return await admin_service.revoke_user_sessions_enhanced(
        user_id=uuid.UUID(user_id),
        revoke_auth0=revoke_auth0,
    )


@router.post(
    "/users/{user_id}/impersonate",
    response_model=ImpersonateUserResponse,
    summary="Kullanıcı Taklit Et",
    description="Admin olarak başka bir kullanıcıyı taklit eder.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def impersonate_user(
    user_id: str,
    admin_service: AdminServiceDep,
    current_user: CurrentUser,
    request: ImpersonateUserRequest | None = None,
) -> ImpersonateUserResponse:
    reason = request.reason if request else None
    duration = request.duration_minutes if request else 60
    return await admin_service.impersonate_user(
        admin_user=current_user,
        target_user_id=uuid.UUID(user_id),
        reason=reason,
        duration_minutes=duration,
    )


@router.post(
    "/users/{user_id}/ban",
    summary="Kullanıcıyı Yasakla",
    description="Kullanıcıyı sistemden kalıcı olarak yasaklar.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def ban_user(
    user_id: str,
    admin_service: AdminServiceDep,
    reason: str | None = None,
):
    return await admin_service.ban_user(
        user_id=uuid.UUID(user_id),
        reason=reason,
    )
