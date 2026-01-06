"""
IoT Module - FastAPI Dependencies
"""
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.auth.dependencies import TenantContext, get_tenant_context
from src.modules.iot.service import IoTService, TelemetryService


async def get_iot_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
) -> IoTService:
    """Get IoTService instance with tenant context."""
    return IoTService(db, tenant_context.organization_id)


async def get_telemetry_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TelemetryService:
    """Get TelemetryService instance."""
    return TelemetryService(db)


# Type aliases
IoTServiceDep = Annotated[IoTService, Depends(get_iot_service)]
TelemetryServiceDep = Annotated[TelemetryService, Depends(get_telemetry_service)]
