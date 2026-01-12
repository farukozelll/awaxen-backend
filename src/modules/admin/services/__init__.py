"""
Admin Module - FastAPI Dependencies

Admin service'leri için dependency injection.
"""
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.admin.services.invitation_service import AdminInvitationService
from src.modules.admin.services.organization_service import AdminOrganizationService
from src.modules.admin.services.rewards_service import AdminRewardsService
from src.modules.admin.services.system_service import AdminSystemService
from src.modules.admin.services.user_service import AdminUserService


async def get_admin_organization_service(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> AdminOrganizationService:
    """Get AdminOrganizationService instance."""
    return AdminOrganizationService(db)


async def get_admin_user_service(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> AdminUserService:
    """Get AdminUserService instance."""
    return AdminUserService(db)


async def get_admin_invitation_service(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> AdminInvitationService:
    """Get AdminInvitationService instance."""
    return AdminInvitationService(db)


async def get_admin_system_service(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> AdminSystemService:
    """Get AdminSystemService instance."""
    return AdminSystemService(db)


async def get_admin_rewards_service(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> AdminRewardsService:
    """Get AdminRewardsService instance."""
    return AdminRewardsService(db)


# Type aliases for dependency injection
AdminOrganizationServiceDep = Annotated[AdminOrganizationService, Depends(get_admin_organization_service)]
AdminUserServiceDep = Annotated[AdminUserService, Depends(get_admin_user_service)]
AdminInvitationServiceDep = Annotated[AdminInvitationService, Depends(get_admin_invitation_service)]
AdminSystemServiceDep = Annotated[AdminSystemService, Depends(get_admin_system_service)]
AdminRewardsServiceDep = Annotated[AdminRewardsService, Depends(get_admin_rewards_service)]
