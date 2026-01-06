"""
RealEstate Module - FastAPI Dependencies
"""
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.auth.dependencies import TenantContext, get_tenant_context
from src.modules.real_estate.service import RealEstateService


async def get_real_estate_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
) -> RealEstateService:
    """Get RealEstateService instance with tenant context."""
    return RealEstateService(db, tenant_context.organization_id)


# Type alias
RealEstateServiceDep = Annotated[RealEstateService, Depends(get_real_estate_service)]
