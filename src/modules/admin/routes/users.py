"""
Admin Routes - Users

Kullanıcı yönetimi işlemleri.
Tag: 11. 👑 Admin - Users
"""
import uuid

from fastapi import APIRouter, Depends, status

from src.modules.admin.dependencies import AdminServiceDep
from src.modules.auth.dependencies import CurrentUser, require_role
from src.modules.auth.schemas import (
    AddUserToOrganizationRequest,
    AddUserToOrganizationResponse,
    AdminUserListResponse,
    AssignRoleToUserRequest,
    AssignRoleToUserResponse,
    ImpersonateUserRequest,
    ImpersonateUserResponse,
    InvitationCreateRequest,
    InvitationListResponse,
    InvitationResponse,
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
    org_id: uuid.UUID,
    admin_service: AdminServiceDep,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> AdminUserListResponse:
    return await admin_service.list_organization_users(
        organization_id=str(org_id),
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
    org_id: uuid.UUID,
    request: AddUserToOrganizationRequest,
    admin_service: AdminServiceDep,
) -> AddUserToOrganizationResponse:
    request.organization_id = str(org_id)
    return await admin_service.add_user_to_organization(request)


@router.post(
    "/users/{user_id}/role",
    response_model=AssignRoleToUserResponse,
    summary="Kullanıcıya Rol Ata",
    description="Kullanıcıya belirli bir organizasyonda rol atar.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def assign_role_to_user(
    user_id: uuid.UUID,
    request: AssignRoleToUserRequest,
    admin_service: AdminServiceDep,
) -> AssignRoleToUserResponse:
    return await admin_service.assign_role_to_user(str(user_id), request)


@router.post(
    "/users/{user_id}/revoke-sessions",
    summary="Kullanıcı Oturumlarını Sonlandır",
    description="Kullanıcının tüm aktif oturumlarını iptal eder.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def revoke_user_sessions(
    user_id: uuid.UUID,
    admin_service: AdminServiceDep,
    revoke_auth0: bool = True,
):
    return await admin_service.revoke_user_sessions_enhanced(
        user_id=user_id,
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
    user_id: uuid.UUID,
    admin_service: AdminServiceDep,
    current_user: CurrentUser,
    request: ImpersonateUserRequest | None = None,
) -> ImpersonateUserResponse:
    reason = request.reason if request else None
    duration = request.duration_minutes if request else 60
    return await admin_service.impersonate_user(
        admin_user=current_user,
        target_user_id=user_id,
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
    user_id: uuid.UUID,
    admin_service: AdminServiceDep,
    reason: str | None = None,
):
    return await admin_service.ban_user(
        user_id=user_id,
        reason=reason,
    )


@router.delete(
    "/organizations/{org_id}/users/{user_id}",
    summary="Kullanıcı Çıkar",
    description="Kullanıcıyı organizasyondan çıkarır (Soft Delete).",
    dependencies=[Depends(require_role(["admin"]))],
)
async def remove_user_from_organization(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    admin_service: AdminServiceDep,
):
    """Kullanıcıyı organizasyondan çıkar."""
    return await admin_service.remove_user_from_organization(
        organization_id=org_id,
        user_id=user_id,
    )


# ============== INVITATION ENDPOINTS ==============


@router.post(
    "/organizations/{org_id}/invitations",
    response_model=InvitationResponse,
    summary="Davetiye Oluştur (Admin)",
    description="Admin olarak organizasyona kullanıcı davet eder ve email gönderir.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def create_invitation(
    org_id: uuid.UUID,
    request: InvitationCreateRequest,
    admin_service: AdminServiceDep,
    current_user: CurrentUser,
) -> InvitationResponse:
    """Admin olarak davetiye oluştur ve email gönder."""
    invitation = await admin_service.create_invitation(
        organization_id=org_id,
        email=request.email,
        role_code=request.role,
        invited_by=current_user,
        message=request.message,
        expires_hours=request.expires_hours,
    )
    
    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role_code=invitation.role_code,
        organization_id=invitation.organization_id,
        organization_name=invitation.organization.name if invitation.organization else None,
        invited_by_email=current_user.email,
        is_used=invitation.is_used,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        message=invitation.message,
    )


@router.get(
    "/organizations/{org_id}/invitations",
    response_model=InvitationListResponse,
    summary="Davetiyeleri Listele (Admin)",
    description="Organizasyonun tüm davetiyelerini listeler.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_invitations(
    org_id: uuid.UUID,
    admin_service: AdminServiceDep,
    include_used: bool = False,
) -> InvitationListResponse:
    """Organizasyonun davetiyelerini listele."""
    invitations = await admin_service.get_organization_invitations(
        organization_id=org_id,
        include_used=include_used,
    )
    
    items = [
        InvitationResponse(
            id=inv.id,
            email=inv.email,
            role_code=inv.role_code,
            organization_id=inv.organization_id,
            organization_name=inv.organization.name if inv.organization else None,
            invited_by_email=inv.invited_by.email if inv.invited_by else None,
            is_used=inv.is_used,
            expires_at=inv.expires_at,
            created_at=inv.created_at,
            message=inv.message,
        )
        for inv in invitations
    ]
    
    return InvitationListResponse(items=items, total=len(items))


@router.delete(
    "/invitations/{invitation_id}",
    summary="Davetiye İptal Et (Admin)",
    description="Bekleyen davetiyeyi iptal eder.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    admin_service: AdminServiceDep,
    current_user: CurrentUser,
):
    """Davetiyeyi iptal et."""
    return await admin_service.revoke_invitation(
        invitation_id=invitation_id,
        revoked_by=current_user,
    )
