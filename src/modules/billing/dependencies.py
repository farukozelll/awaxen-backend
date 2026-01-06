"""
Billing Module - FastAPI Dependencies
"""
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.auth.dependencies import TenantContext, get_tenant_context
from src.modules.billing.service import BillingService


async def get_billing_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
) -> BillingService:
    """Get BillingService instance with tenant context."""
    return BillingService(db, tenant_context.organization_id)


# Type alias
BillingServiceDep = Annotated[BillingService, Depends(get_billing_service)]
