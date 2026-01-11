"""
Auth Module - Tenant Management Router

Tenant (organizasyon sahibi) endpoint'leri için ayrı router.
Bu endpoint'ler sadece kendi organizasyonlarını yönetebilir.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status

from src.modules.admin.dependencies import AdminServiceDep
from src.modules.auth.dependencies import require_role
from src.modules.auth.schemas import (
    AddUserToOrganizationRequest,
    AddUserToOrganizationResponse,
    AdminUserListResponse,
    InvitationCreateRequest,
    InvitationListResponse,
    InvitationResponse,
    OrganizationModulesUpdate,
    OrganizationModulesUpdateRequest,
    OrganizationModulesUpdateResponse,
)

tenant_router = APIRouter(
    prefix="/tenant",
    tags=["05. 🏢 Tenant Management"],
)


@tenant_router.get(
    "/organizations/{org_id}/users",
    response_model=AdminUserListResponse,
    summary="Organizasyon Kullanıcıları",
    description="Organizasyondaki kullanıcıları listeler.",
    dependencies=[Depends(require_role(["admin", "tenant"]))],
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
    """Organizasyon kullanıcılarını listele."""
    return await admin_service.list_organization_users(
        organization_id=org_id,
        page=page,
        page_size=page_size,
        search=search,
        role=role,
        is_active=is_active,
    )


@tenant_router.post(
    "/organizations/{org_id}/users",
    response_model=AddUserToOrganizationResponse,
    summary="Kullanıcı Davet Et",
    description="Organizasyona kullanıcı davet eder.",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(["admin", "tenant"]))],
)
async def invite_user_to_organization(
    org_id: str,
    request: AddUserToOrganizationRequest,
    admin_service: AdminServiceDep,
) -> AddUserToOrganizationResponse:
    """Kullanıcı davet et."""
    request.organization_id = org_id
    return await admin_service.add_user_to_organization(request)


@tenant_router.post(
    "/organizations/{org_id}/invitations",
    response_model=InvitationResponse,
    summary="Davetiye Oluştur",
    description="Organizasyona yeni kullanıcı davet eder.",
    dependencies=[Depends(require_role(["admin", "tenant"]))],
)
async def create_invitation(
    org_id: str,
    request: InvitationCreateRequest,
    current_user,
    admin_service: AdminServiceDep,
) -> InvitationResponse:
    """Organizasyona kullanıcı davet et."""
    try:
        org_uuid = uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geçersiz organizasyon ID formatı",
        )
    
    invitation = await admin_service.create_invitation(
        organization_id=org_uuid,
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


@tenant_router.get(
    "/organizations/{org_id}/invitations",
    response_model=InvitationListResponse,
    summary="Davetiyeleri Listele",
    description="Organizasyonun bekleyen davetiyelerini listeler.",
    dependencies=[Depends(require_role(["admin", "tenant"]))],
)
async def list_invitations(
    org_id: str,
    current_user,
    admin_service: AdminServiceDep,
    include_used: bool = False,
) -> InvitationListResponse:
    """Organizasyonun davetiyelerini listele."""
    try:
        org_uuid = uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geçersiz organizasyon ID formatı",
        )
    
    invitations = await admin_service.get_organization_invitations(
        organization_id=org_uuid,
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


@tenant_router.delete(
    "/invitations/{invitation_id}",
    summary="Davetiye İptal Et",
    description="Bekleyen davetiyeyi iptal eder.",
    dependencies=[Depends(require_role(["admin", "tenant"]))],
)
async def revoke_invitation(
    invitation_id: str,
    current_user,
    admin_service: AdminServiceDep,
):
    """Davetiyeyi iptal et."""
    try:
        inv_uuid = uuid.UUID(invitation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geçersiz davetiye ID formatı",
        )
    
    result = await admin_service.revoke_invitation(inv_uuid, current_user)
    return result


@tenant_router.put(
    "/organizations/{org_id}/modules",
    response_model=OrganizationModulesUpdateResponse,
    summary="Modülleri Güncelle",
    description="Organizasyonun modüllerini günceller.",
    dependencies=[Depends(require_role(["admin", "tenant"]))],
)
async def update_organization_modules(
    org_id: str,
    request: OrganizationModulesUpdateRequest,
    admin_service: AdminServiceDep,
) -> OrganizationModulesUpdateResponse:
    """Organizasyon modüllerini güncelle."""
    return await admin_service.update_organization_modules(
        org_id=uuid.UUID(org_id),
        modules=[m.model_dump() for m in request.modules],
    )
