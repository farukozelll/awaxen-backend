"""
Admin Module - Dependencies

Dependency injection for AdminService.
"""
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.admin.service import AdminService


async def get_admin_service(
    db: AsyncSession = Depends(get_db),
) -> AdminService:
    """Get AdminService instance."""
    return AdminService(db)


AdminServiceDep = Annotated[AdminService, Depends(get_admin_service)]
