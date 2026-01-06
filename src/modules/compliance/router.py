"""
Compliance Module - API Routes
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.auth.dependencies import get_current_user, require_permissions
from src.modules.auth.models import User
from src.modules.compliance.schemas import (
    ConsentAccept,
    ConsentListResponse,
    ConsentResponse,
    AuditLogListResponse,
)
from src.modules.compliance.service import ConsentService, AuditLogService

router = APIRouter(prefix="/consents", tags=["Compliance"])


@router.get("", response_model=ConsentListResponse)
async def get_my_consents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all consents for current user."""
    service = ConsentService(db)
    consents = await service.get_user_consents(current_user.id)
    
    return ConsentListResponse(
        consents=[
            ConsentResponse(
                id=c.id,
                user_id=c.user_id,
                organization_id=c.organization_id,
                consent_type=c.consent_type,
                version=c.version,
                accepted_at=c.accepted_at,
                revoked_at=c.revoked_at,
                created_at=c.created_at,
                is_active=c.is_active,
            )
            for c in consents
        ],
        total=len(consents),
    )


@router.post("/accept", response_model=ConsentResponse)
async def accept_consent(
    data: ConsentAccept,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept a consent."""
    service = ConsentService(db)
    
    metadata = data.metadata or {}
    metadata["ip_address"] = request.client.host if request.client else None
    metadata["user_agent"] = request.headers.get("user-agent")
    
    consent = await service.accept_consent(
        user_id=current_user.id,
        consent_type=data.consent_type,
        version=data.version,
        metadata=metadata,
    )
    
    return ConsentResponse(
        id=consent.id,
        user_id=consent.user_id,
        organization_id=consent.organization_id,
        consent_type=consent.consent_type,
        version=consent.version,
        accepted_at=consent.accepted_at,
        revoked_at=consent.revoked_at,
        created_at=consent.created_at,
        is_active=consent.is_active,
    )


@router.post("/revoke/{consent_type}", response_model=ConsentResponse)
async def revoke_consent(
    consent_type: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a consent."""
    service = ConsentService(db)
    consent = await service.revoke_consent(current_user.id, consent_type)
    
    if not consent:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Active consent not found")
    
    return ConsentResponse(
        id=consent.id,
        user_id=consent.user_id,
        organization_id=consent.organization_id,
        consent_type=consent.consent_type,
        version=consent.version,
        accepted_at=consent.accepted_at,
        revoked_at=consent.revoked_at,
        created_at=consent.created_at,
        is_active=consent.is_active,
    )


# Admin routes for audit logs
audit_router = APIRouter(prefix="/audit", tags=["Admin"])


@audit_router.get("/logs", response_model=AuditLogListResponse)
async def get_audit_logs(
    organization_id: UUID | None = Query(None),
    entity_type: str | None = Query(None),
    action: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_permissions(["audit:read"])),
    db: AsyncSession = Depends(get_db),
):
    """Get audit logs (admin only)."""
    service = AuditLogService(db)
    logs, total = await service.get_logs(
        organization_id=organization_id,
        entity_type=entity_type,
        action=action,
        page=page,
        page_size=page_size,
    )
    
    return AuditLogListResponse(
        logs=logs,
        total=total,
        page=page,
        page_size=page_size,
    )
