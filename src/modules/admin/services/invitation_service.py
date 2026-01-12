"""
Admin Invitation Service

Davetiye yönetimi işlemleri.
- Create invitations
- List invitations
- Revoke invitations
- Email notifications
"""
import uuid
import secrets
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.exceptions import ConflictError, NotFoundError, ForbiddenError
from src.modules.auth.models import (
    Invitation,
    Organization,
    OrganizationUser,
    User,
)
from src.modules.auth.schemas import InvitationResponse
from src.core.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class AdminInvitationService:
    """Admin invitation management service."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # =========================================================================
    # INVITATION MANAGEMENT
    # =========================================================================
    
    async def create_invitation(
        self,
        organization_id: uuid.UUID,
        email: str,
        role_code: str,
        invited_by: User,
        message: str | None = None,
        expires_hours: int = 48,
    ) -> "Invitation":
        """
        Yeni davetiye oluştur.
        
        Güvenlik Kontrolleri:
        1. Davet eden kişi organizasyonun üyesi olmalı
        2. Tenant sadece user/device rolü atayabilir
        3. Aynı email için aktif davetiye varsa hata ver
        """
        # Organizasyonu kontrol et
        org = await self._get_organization_by_id(organization_id)
        if not org:
            raise NotFoundError("Organization", organization_id)
        
        # Davet eden kişi organizasyonun üyesi mi?
        # Async SQLAlchemy için güvenli approach - direct query instead of lazy loading
        stmt = (
            select(OrganizationUser)
            .where(
                OrganizationUser.user_id == invited_by.id,
                OrganizationUser.organization_id == organization_id
            )
            .options(selectinload(OrganizationUser.role))
        )
        
        result = await self.db.execute(stmt)
        membership = result.scalar_one_or_none()
        
        if not membership:
            raise ForbiddenError("Bu organizasyona davet gönderme yetkiniz yok")
        
        is_tenant = membership.role and membership.role.code == "tenant"
        
        # Rol kontrolü - tenant sadece user/device atayabilir
        allowed_roles = ["user", "device"]
        if role_code not in allowed_roles:
            raise ForbiddenError(f"Tenant sadece şu rolleri atayabilir: {allowed_roles}")
        
        # Aynı email için aktif davetiye var mı?
        existing = await self._get_pending_invitations(email)
        for inv in existing:
            if inv.organization_id == organization_id:
                raise ConflictError(
                    f"Bu email için zaten aktif bir davetiye var (expires: {inv.expires_at})"
                )
        
        # Token oluştur
        token = secrets.token_urlsafe(32)
        
        # Davetiye oluştur
        invitation = Invitation(
            email=email,
            token=token,
            organization_id=organization_id,
            role_code=role_code,
            invited_by_id=invited_by.id,
            message=message,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_hours),
            is_used=False,
        )
        
        self.db.add(invitation)
        await self.db.flush()
        
        # Email gönder (Notification Service)
        try:
            from src.modules.notifications.service import NotificationService
            notification_service = NotificationService(self.db)
            
            await notification_service.send_invitation_email(
                email=email,
                token=token,
                org_name=org.name,
                invited_by_name=invited_by.full_name or invited_by.email,
            )
            
            logger.info(
                "Invitation email sent successfully",
                email=email,
                org_name=org.name,
                token=token[:8] + "...",  # Only log first 8 chars for security
            )
        except Exception as e:
            logger.error(
                f"Invitation email failed: {e}",
                email=email,
                org_name=org.name,
            )
            # Email gitmese bile davetiye oluşturulur, manuel gönderilebilir
        
        await self.db.commit()
        await self.db.refresh(invitation)
        
        logger.info(
            "Invitation created",
            invitation_id=str(invitation.id),
            email=email,
            organization_id=str(organization_id),
            role_code=role_code,
            invited_by=str(invited_by.id),
        )
        
        return invitation
    
    async def get_organization_invitations(
        self,
        organization_id: uuid.UUID,
        include_used: bool = False,
    ) -> list[Invitation]:
        """Organizasyonun davetiyelerini listele."""
        stmt = select(Invitation).where(Invitation.organization_id == organization_id)
        
        if not include_used:
            stmt = stmt.where(Invitation.is_used == False)
        
        stmt = stmt.order_by(Invitation.created_at.desc())
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def revoke_invitation(self, invitation_id: uuid.UUID, revoked_by: User) -> dict:
        """Davetiyeyi iptal et."""
        stmt = (
            select(Invitation)
            .where(Invitation.id == invitation_id)
            .options(selectinload(Invitation.organization))
        )
        result = await self.db.execute(stmt)
        invitation = result.scalar_one_or_none()
        
        if not invitation:
            raise NotFoundError("Invitation", invitation_id)
        
        # Davetiyeyi sil
        await self.db.delete(invitation)
        await self.db.commit()
        
        logger.info(
            "Invitation revoked",
            invitation_id=str(invitation_id),
            email=invitation.email,
            organization_id=str(invitation.organization_id),
            revoked_by=str(revoked_by.id),
        )
        
        return {
            "status": "revoked",
            "invitation_id": str(invitation_id),
            "email": invitation.email,
            "organization_id": str(invitation.organization_id),
            "message": f"Davetiye iptal edildi: {invitation.email}",
        }
    
    async def list_all_invitations(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        include_used: bool = False,
    ) -> dict:
        """Tüm davetiyeleri listele (Admin için)."""
        stmt = select(Invitation).options(selectinload(Invitation.organization))
        count_stmt = select(func.count(Invitation.id))
        
        if search:
            stmt = stmt.where(Invitation.email.ilike(f"%{search}%"))
            count_stmt = count_stmt.where(Invitation.email.ilike(f"%{search}%"))
        
        if not include_used:
            stmt = stmt.where(Invitation.is_used == False)
            count_stmt = count_stmt.where(Invitation.is_used == False)
        
        # Total count
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0
        
        # Pagination
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size).order_by(Invitation.created_at.desc())
        
        result = await self.db.execute(stmt)
        invitations = result.scalars().all()
        
        items = []
        for inv in invitations:
            items.append(InvitationResponse(
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
            ))
        
        return {
            "invitations": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    
    async def get_invitation_stats(self) -> dict:
        """Davetiye istatistiklerini getir."""
        from sqlalchemy import func
        
        # Toplam davetiyeler
        total_stmt = select(func.count(Invitation.id))
        total_result = await self.db.execute(total_stmt)
        total_invitations = total_result.scalar() or 0
        
        # Kullanılmış davetiyeler
        used_stmt = select(func.count(Invitation.id)).where(Invitation.is_used == True)
        used_result = await self.db.execute(used_stmt)
        used_invitations = used_result.scalar() or 0
        
        # Bekleyen davetiyeler
        pending_invitations = total_invitations - used_invitations
        
        # Son 7 günde oluşturulanlar
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        recent_stmt = select(func.count(Invitation.id)).where(
            Invitation.created_at >= seven_days_ago
        )
        recent_result = await self.db.execute(recent_stmt)
        recent_invitations = recent_result.scalar() or 0
        
        # Süresi geçmiş davetiyeler
        expired_stmt = select(func.count(Invitation.id)).where(
            Invitation.expires_at < datetime.now(timezone.utc),
            Invitation.is_used == False
        )
        expired_result = await self.db.execute(expired_stmt)
        expired_invitations = expired_result.scalar() or 0
        
        return {
            "total_invitations": total_invitations,
            "used_invitations": used_invitations,
            "pending_invitations": pending_invitations,
            "recent_invitations": recent_invitations,
            "expired_invitations": expired_invitations,
            "conversion_rate": (used_invitations / total_invitations * 100) if total_invitations > 0 else 0,
        }
    
    # =========================================================================
    # PRIVATE HELPER METHODS
    # =========================================================================
    
    async def _get_organization_by_id(self, org_id: uuid.UUID) -> Organization | None:
        """Get organization by ID."""
        stmt = select(Organization).where(Organization.id == org_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _get_pending_invitations(self, email: str) -> list[Invitation]:
        """Bekleyen davetiyeleri getir."""
        stmt = (
            select(Invitation)
            .where(
                Invitation.email == email,
                Invitation.is_used == False,
                Invitation.expires_at > datetime.now(timezone.utc)
            )
            .order_by(Invitation.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
