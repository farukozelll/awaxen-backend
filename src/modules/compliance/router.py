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

router = APIRouter(prefix="/consents", tags=["52. 📜 Compliance"])


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
audit_router = APIRouter(prefix="/audit", tags=["13. 👑 Admin - Audit"])


@audit_router.get("/logs", response_model=AuditLogListResponse)
async def get_audit_logs(
    organization_id: UUID | None = Query(None, description="Sadece bu organizasyonun logları"),
    user_id: UUID | None = Query(None, description="Sadece bu kullanıcının yaptığı işlemler"),
    entity_type: str | None = Query(None, description="Entity tipi (asset, device, user, etc.)"),
    action: str | None = Query(None, description="Aksiyon tipi (create, update, delete, etc.)"),
    start_date: str | None = Query(None, description="Başlangıç tarihi (ISO format: 2024-01-01T00:00:00Z)"),
    end_date: str | None = Query(None, description="Bitiş tarihi (ISO format: 2024-01-31T23:59:59Z)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_permissions(["audit:read"])),
    db: AsyncSession = Depends(get_db),
):
    """
    Get audit logs with advanced filtering (admin only).
    
    **Filtreler:**
    - `organization_id`: Sadece belirli bir organizasyonun logları
    - `user_id`: Sadece belirli bir kullanıcının yaptığı işlemler
    - `entity_type`: Entity tipi (asset, device, gateway, user, organization, etc.)
    - `action`: Aksiyon tipi (create, update, delete, login, etc.)
    - `start_date` / `end_date`: Tarih aralığı (ISO 8601 format)
    
    **Örnek Kullanım:**
    - Bir organizasyonun tüm logları: `?organization_id=xxx`
    - Bir kullanıcının yaptıkları: `?user_id=xxx`
    - Son 7 günün logları: `?start_date=2024-01-08T00:00:00Z`
    - Belirli bir aksiyonun logları: `?action=device.create`
    """
    from datetime import datetime
    
    # Parse date strings to datetime
    start_datetime = None
    end_datetime = None
    
    if start_date:
        try:
            start_datetime = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        except ValueError:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use ISO 8601 format.")
    
    if end_date:
        try:
            end_datetime = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        except ValueError:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Invalid end_date format. Use ISO 8601 format.")
    
    service = AuditLogService(db)
    logs, total = await service.get_logs(
        organization_id=organization_id,
        entity_type=entity_type,
        entity_id=None,
        actor_user_id=user_id,
        action=action,
        start_date=start_datetime,
        end_date=end_datetime,
        page=page,
        page_size=page_size,
    )
    
    return AuditLogListResponse(
        logs=logs,
        total=total,
        page=page,
        page_size=page_size,
    )
