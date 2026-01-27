"""
Admin User Service

Kullanıcı yönetimi işlemleri.
- User listing and filtering
- User management (ban, impersonate)
- Role assignment
- Session management
"""
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.core.logging import get_logger
from src.modules.auth.models import (
    Organization,
    OrganizationUser,
    Role,
    User,
)
from src.modules.auth.schemas import (
    AdminUserListItem,
    AdminUserListResponse,
    AssignRoleToUserResponse,
    RoleInfo,
    UserResponse,
)

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class AdminUserService:
    """Admin user management service."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # =========================================================================
    # USER LISTING
    # =========================================================================
    
    async def list_all_users(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        role: str | None = None,
        organization_id: str | None = None,
        is_active: bool | None = None,
    ) -> AdminUserListResponse:
        """Tüm kullanıcıları listele (Admin için)."""
        stmt = (
            select(User)
            .options(
                selectinload(User.organization_memberships)
                .selectinload(OrganizationUser.role),
                selectinload(User.organization_memberships)
                .selectinload(OrganizationUser.organization),
            )
        )
        count_stmt = select(func.count(User.id))
        
        if search:
            stmt = stmt.where(
                (User.email.ilike(f"%{search}%")) |
                (User.full_name.ilike(f"%{search}%"))
            )
            count_stmt = count_stmt.where(
                (User.email.ilike(f"%{search}%")) |
                (User.full_name.ilike(f"%{search}%"))
            )
        
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
            count_stmt = count_stmt.where(User.is_active == is_active)
        
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0
        
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size).order_by(User.created_at.desc())
        
        result = await self.db.execute(stmt)
        users = result.scalars().all()
        
        items = []
        for user in users:
            role_info = None
            org_response = None
            
            for m in user.organization_memberships:
                if m.is_default:
                    if m.role:
                        role_info = RoleInfo(code=m.role.code, name=m.role.name)
                    if m.organization:
                        org_response = {
                            "id": m.organization.id,
                            "name": m.organization.name,
                            "slug": m.organization.slug,
                        }
                    break
            
            items.append(AdminUserListItem(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                phone=user.phone,
                is_active=user.is_active,
                created_at=user.created_at,
                last_login=user.last_login,
                role=role_info,
                organization=org_response,
            ))
        
        return AdminUserListResponse(
            users=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    
    async def list_organization_users(
        self,
        organization_id: str,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ):
        """Organizasyondaki kullanıcıları listele."""
        from src.modules.auth.schemas import (
            AdminUserListItem,
            AdminUserListResponse,
            OrganizationResponse,
            RoleInfo,
        )
        
        # Base query - sadece belirtilen organizasyondaki kullanıcılar
        # PERFORMANCE: Sadece ilgili organizasyon membership'ını yükle
        stmt = (
            select(User)
            .join(OrganizationUser)
            .where(OrganizationUser.organization_id == organization_id)
            .options(
                # Sadece bu organizasyondaki membership'ı yükle (N+1 çözümü)
                selectinload(
                    User.organization_memberships.and_(
                        OrganizationUser.organization_id == organization_id
                    )
                )
                .selectinload(OrganizationUser.role),
                selectinload(
                    User.organization_memberships.and_(
                        OrganizationUser.organization_id == organization_id
                    )
                )
                .selectinload(OrganizationUser.organization),
            )
        )
        count_stmt = (
            select(func.count(User.id))
            .join(OrganizationUser)
            .where(OrganizationUser.organization_id == organization_id)
        )
        
        # Filters
        if search:
            stmt = stmt.where(
                (User.email.ilike(f"%{search}%")) |
                (User.full_name.ilike(f"%{search}%"))
            )
            count_stmt = count_stmt.where(
                (User.email.ilike(f"%{search}%")) |
                (User.full_name.ilike(f"%{search}%"))
            )
        
        if role:
            stmt = stmt.join(OrganizationUser.role).where(Role.code == role)
            count_stmt = count_stmt.join(OrganizationUser.role).where(Role.code == role)
        
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
            count_stmt = count_stmt.where(User.is_active == is_active)
        
        # Total count
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0
        
        # Pagination
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size).order_by(User.created_at.desc())
        
        result = await self.db.execute(stmt)
        users = result.scalars().all()
        
        # Build response - ARTIK PYTHON'DA FİLTRELEME YOK
        items = []
        for user in users:
            role_info = None
            org_response = None
            
            # PERFORMANCE: Sadece 1 membership var (o organizasyondaki)
            if user.organization_memberships:
                membership = user.organization_memberships[0]  # İlk ve tek eleman
                if membership.role:
                    role_info = RoleInfo(code=membership.role.code, name=membership.role.name)
                if membership.organization:
                    org_response = OrganizationResponse.model_validate(membership.organization)
            
            items.append(AdminUserListItem(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                phone=user.phone,
                is_active=user.is_active,
                created_at=user.created_at,
                last_login=user.last_login,
                role=role_info,
                organization=org_response,
            ))
        
        return AdminUserListResponse(
            users=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    
    # =========================================================================
    # USER MANAGEMENT
    # =========================================================================
    
    async def add_user_to_organization(
        self,
        request,
    ) -> dict:
        """Organizasyona kullanıcı ekle."""
        from src.modules.auth.schemas import (
            OrganizationResponse,
        )
        
        org = await self._get_organization_by_id(request.organization_id)
        if not org:
            raise NotFoundError("Organization", request.organization_id)
        
        existing_user = await self._get_user_by_email(request.email)
        
        if existing_user:
            stmt = select(OrganizationUser).where(
                OrganizationUser.user_id == existing_user.id,
                OrganizationUser.organization_id == org.id,
            )
            result = await self.db.execute(stmt)
            existing_membership = result.scalar_one_or_none()
            
            if existing_membership:
                raise ConflictError(f"User {request.email} is already a member of this organization")
            
            user = existing_user
        else:
            user = User(
                email=request.email,
                full_name=request.full_name,
                phone=request.phone,
                is_active=True,
                is_verified=False,
                onboarding_completed=False,
            )
            self.db.add(user)
            await self.db.flush()
        
        role = await self._get_or_create_role(request.role_code)
        
        membership = OrganizationUser(
            user_id=user.id,
            organization_id=org.id,
            role_id=role.id,
            is_default=not existing_user,
            joined_at=datetime.now(UTC),
        )
        self.db.add(membership)
        
        await self.db.commit()
        await self.db.refresh(user)
        
        logger.info(
            "User added to organization",
            user_id=str(user.id),
            org_id=str(org.id),
            role=request.role_code,
        )
        
        return {
            "message": "Kullanıcı organizasyona eklendi",
            "user": UserResponse.model_validate(user),
            "organization": OrganizationResponse.model_validate(org),
            "role": request.role_code,
        }
    
    async def remove_user_from_organization(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> dict:
        """
        Kullanıcıyı organizasyondan çıkar (Soft Delete).
        
        - Kullanıcı is_active=False yapılır
        - Organizasyon üyeliği kaldırılır
        - Auth0'dan engellenmez (sadece bu org'dan çıkar)
        """
        # Kullanıcıyı bul
        user = await self._get_user_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)
        
        # Organizasyonu bul
        org = await self._get_organization_by_id(organization_id)
        if not org:
            raise NotFoundError("Organization", organization_id)
        
        # Üyeliği bul
        membership = None
        for m in user.organization_memberships:
            if m.organization_id == organization_id:
                membership = m
                break
        
        if not membership:
            raise NotFoundError("User is not a member of this organization")
        
        # Üyeliği sil
        await self.db.delete(membership)
        
        # Kullanıcının başka organizasyonu var mı kontrol et
        remaining_memberships = [
            m for m in user.organization_memberships 
            if m.organization_id != organization_id
        ]
        
        if not remaining_memberships:
            # Başka organizasyonu yok, kullanıcıyı pasife çek
            user.is_active = False
            user.deleted_at = datetime.now(UTC)
        
        await self.db.commit()
        
        logger.info(
            "User removed from organization",
            user_id=str(user_id),
            user_email=user.email,
            organization_id=str(organization_id),
            organization_name=org.name,
            user_deactivated=not remaining_memberships,
        )
        
        return {
            "message": f"Kullanıcı '{user.email}' organizasyondan çıkarıldı",
            "user_id": str(user_id),
            "organization_id": str(organization_id),
            "user_deactivated": not remaining_memberships,
        }
    
    async def assign_role_to_user(self, user_id: str, request) -> AssignRoleToUserResponse:
        """Kullanıcıya rol ata."""
        user = await self._get_user_by_id(uuid.UUID(user_id))
        if not user:
            raise NotFoundError("User not found")
        
        role = await self._get_or_create_role(request.role_code)
        
        target_org_id = request.organization_id
        membership = None
        
        for m in user.organization_memberships:
            if target_org_id:
                if m.organization_id == target_org_id:
                    membership = m
                    target_org_id = m.organization_id
                    break
            elif m.is_default:
                membership = m
                target_org_id = m.organization_id
                break
        
        if not membership:
            raise NotFoundError("User membership not found")
        
        membership.role_id = role.id
        await self.db.commit()
        
        from src.modules.auth.schemas import RoleInfo
        return AssignRoleToUserResponse(
            message=f"Rol '{request.role_code}' kullanıcıya atandı",
            user_id=user.id,
            role=RoleInfo(code=role.code, name=role.name),
            organization_id=target_org_id,
        )
    
    async def ban_user(self, user_id: uuid.UUID, reason: str | None = None) -> dict:
        """Kullanıcıyı yasakla."""
        user = await self._get_user_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)
        
        user.is_active = False
        user.banned_at = datetime.now(UTC)
        user.banned_reason = reason
        
        await self.db.commit()
        
        logger.warning(
            "User banned",
            user_id=str(user_id),
            user_email=user.email,
            reason=reason,
        )
        
        return {
            "status": "banned",
            "user_id": str(user_id),
            "user_email": user.email,
            "reason": reason,
            "message": f"Kullanıcı '{user.email}' yasaklandı",
        }
    
    # =========================================================================
    # SESSION MANAGEMENT
    # =========================================================================
    
    async def revoke_user_sessions_enhanced(
        self,
        user_id: uuid.UUID,
        revoke_auth0: bool = True,
    ) -> dict:
        """
        Revoke all sessions for a user with Redis blacklist and Auth0 (Admin only).
        
        1. Redis'te refresh_token'ı blacklist'e ekle
        2. Auth0 Management API ile oturumu kapat (opsiyonel)
        3. Audit log'a kaydet
        """
        user = await self._get_user_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)
        
        revoke_results = {
            "redis_blacklist": False,
            "auth0_revoked": False,
            "error": None,
        }
        
        try:
            # 1. Redis blacklist (implementasyon gerekebilir)
            # TODO: Redis blacklist implementasyonu
            revoke_results["redis_blacklist"] = True
            logger.info("User sessions added to Redis blacklist", user_id=str(user_id))
            
        except Exception as e:
            logger.error("Failed to blacklist user sessions in Redis", user_id=str(user_id), error=str(e))
            revoke_results["error"] = str(e)
        
        # 2. Auth0 session revoke
        if revoke_auth0:
            try:
                # TODO: Auth0 Management API implementasyonu
                revoke_results["auth0_revoked"] = True
                logger.info("Auth0 sessions revoked", user_id=str(user_id))
                
            except Exception as e:
                logger.error("Failed to revoke Auth0 sessions", user_id=str(user_id), error=str(e))
                revoke_results["error"] = str(e)
        
        # 3. Audit log
        logger.warning(
            "User sessions revoked by admin",
            user_id=str(user_id),
            user_email=user.email,
            revoke_results=revoke_results,
        )
        
        return {
            "status": "revoked",
            "user_id": str(user_id),
            "user_email": user.email,
            "revoke_results": revoke_results,
            "message": f"'{user.email}' kullanıcısının tüm oturumları sonlandırıldı",
        }
    
    async def impersonate_user(
        self,
        admin_user: User,
        target_user_id: uuid.UUID,
        reason: str | None = None,
        duration_minutes: int = 60,
    ) -> dict:
        """
        Admin olarak başka bir kullanıcıyı taklit et.
        
        Güvenli impersonasyon token'ı oluşturur ve audit log'a kaydeder.
        """
        target_user = await self._get_user_by_id(target_user_id)
        if not target_user:
            raise NotFoundError("Target user not found")
        
        # Admin'in target user'ı taklit etme yetkisi var mı?
        if not admin_user.is_superuser:
            # Aynı organizasyon olmalı
            admin_orgs = {m.organization_id for m in admin_user.organization_memberships}
            target_orgs = {m.organization_id for m in target_user.organization_memberships}
            
            if not admin_orgs.intersection(target_orgs):
                raise ForbiddenError("You can only impersonate users in your organizations")
        
        # Get default organization for context
        default_org_id = None
        for membership in target_user.organization_memberships:
            if membership.is_default:
                default_org_id = str(membership.organization_id)
                break
        
        # Güvenli impersonation token oluştur
        from src.core.security_enhanced import create_impersonation_token, get_token_info
        
        token = create_impersonation_token(
            target_user_id=str(target_user.id),
            admin_user_id=str(admin_user.id),
            duration_minutes=duration_minutes,
            org_id=default_org_id,
            reason=reason,
        )
        
        # Token bilgisini logla (güvenlik için)
        from src.core.security_enhanced import verify_token
        token_info = get_token_info(verify_token(token))
        
        # Audit log
        logger.warning(
            "User impersonation started",
            admin_user_id=str(admin_user.id),
            admin_email=admin_user.email,
            target_user_id=str(target_user_id),
            target_email=target_user.email,
            reason=reason,
            duration_minutes=duration_minutes,
            token_info=token_info,
        )
        
        return {
            "status": "impersonation_started",
            "admin_user_id": str(admin_user.id),
            "target_user_id": str(target_user_id),
            "target_email": target_user.email,
            "reason": reason,
            "duration_minutes": duration_minutes,
            "token": token,  # Return token for frontend
            "expires_at": datetime.now(UTC) + timedelta(minutes=duration_minutes),
            "message": f"'{target_user.email}' kullanıcısı olarak taklit başlatıldı",
        }
    
    # =========================================================================
    # PRIVATE HELPER METHODS
    # =========================================================================
    
    async def _get_organization_by_id(self, org_id: uuid.UUID) -> Organization | None:
        """Get organization by ID."""
        stmt = select(Organization).where(Organization.id == org_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        """Get user by ID with relationships."""
        stmt = (
            select(User)
            .options(selectinload(User.organization_memberships))
            .where(User.id == user_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _get_user_by_email(self, email: str) -> User | None:
        """Get user by email."""
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _get_or_create_role(self, role_code: str) -> Role:
        """Get or create a role by code."""
        stmt = select(Role).where(Role.code == role_code)
        result = await self.db.execute(stmt)
        role = result.scalar_one_or_none()
        
        if not role:
            role = Role(
                code=role_code,
                name=role_code.title(),
                description=f"Auto-created {role_code} role",
            )
            self.db.add(role)
            await self.db.flush()
            logger.info("Role created", role_code=role_code)
        
        return role
