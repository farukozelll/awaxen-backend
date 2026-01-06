"""
Compliance Module - Service Layer
"""
import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.compliance.models import Consent, AuditLog


class ConsentService:
    """Service for managing user consents."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_consents(self, user_id: UUID) -> list[Consent]:
        """Get all consents for a user."""
        result = await self.db.execute(
            select(Consent)
            .where(Consent.user_id == user_id)
            .order_by(Consent.consent_type)
        )
        return list(result.scalars().all())

    async def get_active_consent(
        self, user_id: UUID, consent_type: str
    ) -> Consent | None:
        """Get active consent of a specific type for a user."""
        result = await self.db.execute(
            select(Consent)
            .where(
                Consent.user_id == user_id,
                Consent.consent_type == consent_type,
                Consent.accepted_at.isnot(None),
                Consent.revoked_at.is_(None),
            )
            .order_by(Consent.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def accept_consent(
        self,
        user_id: UUID,
        consent_type: str,
        version: str,
        organization_id: UUID | None = None,
        metadata: dict | None = None,
    ) -> Consent:
        """Accept a consent."""
        now = datetime.now(timezone.utc)
        
        consent = Consent(
            user_id=user_id,
            organization_id=organization_id,
            consent_type=consent_type,
            version=version,
            accepted_at=now,
            metadata_=metadata or {},
        )
        
        self.db.add(consent)
        await self.db.commit()
        await self.db.refresh(consent)
        return consent

    async def revoke_consent(self, user_id: UUID, consent_type: str) -> Consent | None:
        """Revoke an active consent."""
        consent = await self.get_active_consent(user_id, consent_type)
        if consent:
            consent.revoked_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(consent)
        return consent

    async def has_required_consents(
        self, user_id: UUID, required_types: list[str]
    ) -> bool:
        """Check if user has all required consents."""
        for consent_type in required_types:
            consent = await self.get_active_consent(user_id, consent_type)
            if not consent:
                return False
        return True


class AuditLogService:
    """Service for audit logging."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        action: str,
        entity_type: str,
        entity_id: UUID | None = None,
        actor_user_id: UUID | None = None,
        organization_id: UUID | None = None,
        payload: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        """Create an audit log entry."""
        payload_hash = None
        if payload:
            payload_hash = hashlib.sha256(
                json.dumps(payload, sort_keys=True, default=str).encode()
            ).hexdigest()

        log = AuditLog(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_hash=payload_hash,
            payload=payload or {},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def get_logs(
        self,
        organization_id: UUID | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        actor_user_id: UUID | None = None,
        action: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditLog], int]:
        """Get audit logs with filtering and pagination."""
        query = select(AuditLog)
        count_query = select(func.count(AuditLog.id))

        if organization_id:
            query = query.where(AuditLog.organization_id == organization_id)
            count_query = count_query.where(AuditLog.organization_id == organization_id)
        if entity_type:
            query = query.where(AuditLog.entity_type == entity_type)
            count_query = count_query.where(AuditLog.entity_type == entity_type)
        if entity_id:
            query = query.where(AuditLog.entity_id == entity_id)
            count_query = count_query.where(AuditLog.entity_id == entity_id)
        if actor_user_id:
            query = query.where(AuditLog.actor_user_id == actor_user_id)
            count_query = count_query.where(AuditLog.actor_user_id == actor_user_id)
        if action:
            query = query.where(AuditLog.action == action)
            count_query = count_query.where(AuditLog.action == action)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(AuditLog.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        logs = list(result.scalars().all())

        return logs, total
