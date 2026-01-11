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
    AdminUserListResponse,
    InvitationCreateRequest,
    InvitationListResponse,
    InvitationResponse,
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


# NOT: POST /organizations/{org_id}/users kaldırıldı
# Kullanıcı eklemek için DAİMA /invitations endpoint'i kullanılmalı
# Bu endpoint direkt DB'ye yazıyordu, davetiye akışını atlıyordu


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


# NOT: PUT /organizations/{org_id}/modules kaldırıldı
# Modül yönetimi sadece Admin tarafından yapılabilir
# Admin endpoint: PUT /api/v1/admin/organizations/{org_id}/modules


@tenant_router.delete(
    "/organizations/{org_id}/users/{user_id}",
    summary="Kullanıcı Çıkar",
    description="Kullanıcıyı organizasyondan çıkarır (Soft Delete).",
    dependencies=[Depends(require_role(["admin", "tenant"]))],
)
async def remove_user_from_organization(
    org_id: str,
    user_id: str,
    admin_service: AdminServiceDep,
):
    """
    Kullanıcıyı organizasyondan çıkar (Soft Delete).
    
    - Kullanıcı is_active=False yapılır
    - Organizasyon üyeliği kaldırılır
    - Auth0'dan engellenmez (sadece bu org'dan çıkar)
    """
    try:
        org_uuid = uuid.UUID(org_id)
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geçersiz ID formatı",
        )
    
    result = await admin_service.remove_user_from_organization(
        organization_id=org_uuid,
        user_id=user_uuid,
    )
    return result
