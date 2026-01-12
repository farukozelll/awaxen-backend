"""
Admin Module - Dependencies

Dependency injection for AdminService and specialized services.
"""
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.admin.service import AdminService
from src.modules.admin.services import (
    AdminOrganizationServiceDep,
    AdminUserServiceDep,
    AdminInvitationServiceDep,
    AdminSystemServiceDep,
)


async def get_admin_service(
    db: AsyncSession = Depends(get_db),
) -> AdminService:
    """Get AdminService instance (Facade pattern)."""
    return AdminService(db)


# Legacy dependency for backward compatibility
AdminServiceDep = Annotated[AdminService, Depends(get_admin_service)]

# New specialized dependencies for direct access
AdminOrganizationServiceDep = AdminOrganizationServiceDep
AdminUserServiceDep = AdminUserServiceDep
AdminInvitationServiceDep = AdminInvitationServiceDep
AdminSystemServiceDep = AdminSystemServiceDep
