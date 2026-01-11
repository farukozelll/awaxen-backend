"""
Admin Module - Service Layer

L7 Best Practice: Domain Separation
- AuthService: Authentication (login, sync, token validation)
- AdminService: Management (organizations, users, roles, invitations)

Bu servis sadece Admin işlemlerini yönetir:
- Organization CRUD
- User management (invite, ban, impersonate)
- Role/Permission assignment
- Module management
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.modules.auth.models import (
    Invitation,
    ModuleType,
    Organization,
    OrganizationModule,
    OrganizationUser,
    Permission,
    Role,
    RoleType,
    User,
    ROLE_PERMISSIONS,
    MODULE_PERMISSIONS,
)
from src.modules.auth.schemas import (
    AddUserToOrganizationRequest,
    AddUserToOrganizationResponse,
    AdminOrganizationDetailResponse,
    AdminOrganizationListItem,
    AdminOrganizationListResponse,
    AdminPermissionListResponse,
    AdminRoleListResponse,
    AdminUserListItem,
    AdminUserListResponse,
    AssignRoleToUserResponse,
    AvailableModulesResponse,
    AvailablePermissionsResponse,
    AvailableRolesResponse,
    CreateOrganizationStep2Request,
    CreateOrganizationStep2Response,
    CreateOrganizationWithUserRequest,
    CreateOrganizationWithUserResponse,
    InvitationResponse,
    ModuleInfo,
    OrganizationModuleResponse,
    OrganizationResponse,
    OrganizationWalletSummary,
    OrganizationWithModulesResponse,
    RoleInfo,
    RoleResponse,
    UserResponse,
)

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class AdminService:
    """
    Admin Service - Organization, User, Role, Invitation Management
    
    Bu servis AuthService'ten ayrılmıştır (Separation of Concerns).
    Sadece yönetim işlemlerini yapar.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # =========================================================================
    # ORGANIZATION MANAGEMENT
    # =========================================================================
    
    async def get_organization_by_id(self, org_id: uuid.UUID) -> Organization | None:
        """Get organization by ID."""
        stmt = select(Organization).where(Organization.id == org_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_organization_by_slug(self, slug: str) -> Organization | None:
        """Get organization by slug."""
        stmt = select(Organization).where(Organization.slug == slug)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def create_organization_with_user(
        self,
        request: CreateOrganizationWithUserRequest,
    ) -> CreateOrganizationWithUserResponse:
        """
        Tab 1: Organizasyon ve ilk kullanıcı (tenant owner) birlikte oluşturma.
        """
        # Slug oluştur
        slug = request.organization_slug
        if not slug:
            slug = request.organization_name.lower().replace(" ", "-").replace("'", "")
        
        # Slug kontrolü
        existing_org = await self.get_organization_by_slug(slug)
        if existing_org:
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"
        
        # Email kontrolü
        existing_user = await self._get_user_by_email(request.user_email)
        if existing_user:
            raise ConflictError(f"User with email {request.user_email} already exists")
        
        # Organizasyon oluştur
        org = Organization(
            name=request.organization_name,
            slug=slug,
            description=request.organization_description,
            organization_type=request.organization_type.value if request.organization_type else None,
            company_size=request.company_size,
            email=request.organization_email,
            phone=request.organization_phone,
            city=request.city,
            district=request.district,
            neighborhood=request.neighborhood,
            street=request.street,
            postal_code=request.postal_code,
            country=request.country,
            latitude=request.latitude,
            longitude=request.longitude,
            is_active=True,
        )
        self.db.add(org)
        await self.db.flush()
        
        # Kullanıcı oluştur
        full_name = f"{request.user_first_name} {request.user_last_name}"
        user = User(
            email=request.user_email,
            full_name=full_name,
            first_name=request.user_first_name,
            last_name=request.user_last_name,
            phone=request.user_phone,
            is_active=True,
            is_verified=False,
        )
        self.db.add(user)
        await self.db.flush()
        
        # Rol al veya oluştur
        role = await self._get_or_create_role(request.user_role)
        
        # Kullanıcıyı organizasyona ekle
        membership = OrganizationUser(
            user_id=user.id,
            organization_id=org.id,
            role_id=role.id,
            is_default=True,
            joined_at=datetime.now(timezone.utc),
        )
        self.db.add(membership)
        
        await self.db.commit()
        await self.db.refresh(org)
        await self.db.refresh(user)
        await self.db.refresh(role)
        
        logger.info(
            "Organization and user created by admin",
            org_id=str(org.id),
            user_id=str(user.id),
            role=request.user_role,
        )
        
        return CreateOrganizationWithUserResponse(
            message="Organizasyon ve kullanıcı başarıyla oluşturuldu",
            organization=OrganizationResponse.model_validate(org),
            user=UserResponse.model_validate(user),
            role=RoleResponse.model_validate(role),
        )
    
    async def create_organization_step2(
        self,
        request: CreateOrganizationStep2Request,
    ) -> CreateOrganizationStep2Response:
        """Step 2: Organizasyona modül ata."""
        org = await self.get_organization_by_id(request.organization_id)
        if not org:
            raise NotFoundError("Organization", request.organization_id)
        
        # Core modülü her zaman ekle
        modules_to_add = set(request.modules)
        modules_to_add.add(ModuleType.CORE.value)
        
        now = datetime.now(timezone.utc)
        for module_code in modules_to_add:
            if module_code not in [m.value for m in ModuleType]:
                logger.warning("Invalid module code", module_code=module_code)
                continue
            
            stmt = select(OrganizationModule).where(
                OrganizationModule.organization_id == org.id,
                OrganizationModule.module_code == module_code,
            )
            result = await self.db.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if not existing:
                org_module = OrganizationModule(
                    organization_id=org.id,
                    module_code=module_code,
                    is_active=True,
                    activated_at=now,
                )
                self.db.add(org_module)
        
        await self.db.commit()
        await self.db.refresh(org)
        
        stmt = select(OrganizationModule).where(
            OrganizationModule.organization_id == org.id
        )
        result = await self.db.execute(stmt)
        org_modules = result.scalars().all()
        
        logger.info(
            "Modules assigned to organization",
            org_id=str(org.id),
            modules=[m.module_code for m in org_modules],
        )
        
        return CreateOrganizationStep2Response(
            message="Modüller atandı. Şimdi kullanıcı ekleyebilirsiniz.",
            organization=OrganizationWithModulesResponse(
                id=org.id,
                name=org.name,
                slug=org.slug,
                modules=[OrganizationModuleResponse.model_validate(m) for m in org_modules],
            ),
        )
    
    async def list_all_organizations(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> AdminOrganizationListResponse:
        """Tüm organizasyonları listele (Admin için)."""
        stmt = select(Organization)
        count_stmt = select(func.count(Organization.id))
        
        if search:
            stmt = stmt.where(
                (Organization.name.ilike(f"%{search}%")) |
                (Organization.slug.ilike(f"%{search}%"))
            )
            count_stmt = count_stmt.where(
                (Organization.name.ilike(f"%{search}%")) |
                (Organization.slug.ilike(f"%{search}%"))
            )
        
        if is_active is not None:
            stmt = stmt.where(Organization.is_active == is_active)
            count_stmt = count_stmt.where(Organization.is_active == is_active)
        
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0
        
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size).order_by(Organization.created_at.desc())
        
        result = await self.db.execute(stmt)
        organizations = result.scalars().all()
        
        items = []
        for org in organizations:
            user_count_stmt = select(func.count(OrganizationUser.id)).where(
                OrganizationUser.organization_id == org.id
            )
            user_count_result = await self.db.execute(user_count_stmt)
            user_count = user_count_result.scalar() or 0
            
            modules = await self._get_organization_modules(org.id)
            
            try:
                from src.modules.iot.models import Device
                device_count_stmt = select(func.count(Device.id)).where(
                    Device.organization_id == org.id
                )
                device_count_result = await self.db.execute(device_count_stmt)
                device_count = device_count_result.scalar() or 0
            except Exception:
                device_count = 0
            
            items.append(AdminOrganizationListItem(
                id=org.id,
                name=org.name,
                slug=org.slug,
                email=org.email,
                is_active=org.is_active,
                created_at=org.created_at,
                user_count=user_count,
                device_count=device_count,
                modules=modules,
            ))
        
        return AdminOrganizationListResponse(
            organizations=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    
    async def get_organization_detail(self, org_id: str) -> AdminOrganizationDetailResponse:
        """Organizasyon detayını getir (Admin için)."""
        org = await self.get_organization_by_id(uuid.UUID(org_id))
        if not org:
            raise NotFoundError("Organization not found")
        
        stmt = (
            select(OrganizationUser)
            .options(selectinload(OrganizationUser.user), selectinload(OrganizationUser.role))
            .where(OrganizationUser.organization_id == org.id)
        )
        result = await self.db.execute(stmt)
        memberships = result.scalars().all()
        
        users = []
        for m in memberships:
            if m.user:
                role_info = None
                if m.role:
                    role_info = RoleInfo(code=m.role.code, name=m.role.name)
                
                users.append(AdminUserListItem(
                    id=m.user.id,
                    email=m.user.email,
                    full_name=m.user.full_name,
                    phone=m.user.phone,
                    is_active=m.user.is_active,
                    created_at=m.user.created_at,
                    last_login=m.user.last_login,
                    role=role_info,
                    organization=None,
                ))
        
        modules = await self._get_organization_modules(org.id)
        wallet_summary = await self._get_organization_wallet_summary(org.id)
        
        return AdminOrganizationDetailResponse(
            organization=OrganizationResponse.model_validate(org),
            users=users,
            modules=modules,
            device_count=0,
            gateway_count=0,
            asset_count=0,
            wallet_summary=wallet_summary,
        )
    
    async def get_organization_stats(self, organization_id: str) -> dict:
        """Organizasyon istatistiklerini getir."""
        try:
            org_uuid = uuid.UUID(organization_id)
        except ValueError:
            raise NotFoundError("Invalid organization ID")
        
        org = await self.get_organization_by_id(org_uuid)
        if not org:
            raise NotFoundError("Organization not found")
        
        total_users_stmt = (
            select(func.count(User.id))
            .join(OrganizationUser)
            .where(OrganizationUser.organization_id == org_uuid)
        )
        
        active_users_stmt = (
            select(func.count(User.id))
            .join(OrganizationUser)
            .where(
                OrganizationUser.organization_id == org_uuid,
                User.is_active == True
            )
        )
        
        role_distribution_stmt = (
            select(Role.code, func.count(User.id))
            .join(OrganizationUser, Role.id == OrganizationUser.role_id)
            .join(User, User.id == OrganizationUser.user_id)
            .where(OrganizationUser.organization_id == org_uuid)
            .group_by(Role.code)
        )
        
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        recent_activity_stmt = (
            select(func.count(User.id))
            .join(OrganizationUser)
            .where(
                OrganizationUser.organization_id == org_uuid,
                User.last_login >= thirty_days_ago
            )
        )
        
        total_users_result = await self.db.execute(total_users_stmt)
        active_users_result = await self.db.execute(active_users_stmt)
        role_dist_result = await self.db.execute(role_distribution_stmt)
        recent_activity_result = await self.db.execute(recent_activity_stmt)
        
        total_users = total_users_result.scalar() or 0
        active_users = active_users_result.scalar() or 0
        recent_activity = recent_activity_result.scalar() or 0
        
        role_distribution = {}
        for row in role_dist_result:
            role_distribution[row[0]] = row[1]
        
        wallet_summary = await self._get_organization_wallet_summary(org_uuid)
        
        try:
            from src.modules.iot.models import Device
            device_count_stmt = select(func.count(Device.id)).where(
                Device.organization_id == org_uuid
            )
            device_count_result = await self.db.execute(device_count_stmt)
            device_count = device_count_result.scalar() or 0
        except Exception:
            device_count = 0
        
        try:
            from src.modules.real_estate.models import Asset
            asset_count_stmt = select(func.count(Asset.id)).where(
                Asset.organization_id == org_uuid
            )
            asset_count_result = await self.db.execute(asset_count_stmt)
            asset_count = asset_count_result.scalar() or 0
        except Exception:
            asset_count = 0
        
        return {
            "organization_id": organization_id,
            "organization_name": org.name,
            "total_users": total_users,
            "active_users": active_users,
            "inactive_users": total_users - active_users,
            "role_distribution": role_distribution,
            "recent_activity_30_days": recent_activity,
            "device_count": device_count,
            "asset_count": asset_count,
            "wallet_summary": wallet_summary,
        }
    
    async def suspend_organization(
        self,
        org_id: uuid.UUID,
        reason: str | None = None,
    ) -> dict:
        """Organizasyonu askıya al."""
        org = await self.get_organization_by_id(org_id)
        if not org:
            raise NotFoundError("Organization", org_id)
        
        org.is_active = False
        org.suspended_at = datetime.now(timezone.utc)
        org.suspended_reason = reason
        
        await self.db.commit()
        
        logger.warning(
            "Organization suspended",
            org_id=str(org_id),
            org_name=org.name,
            reason=reason,
        )
        
        return {
            "status": "suspended",
            "organization_id": str(org_id),
            "organization_name": org.name,
            "reason": reason,
            "message": f"Organizasyon '{org.name}' askıya alındı",
        }
    
    async def reactivate_organization(self, org_id: uuid.UUID) -> dict:
        """Organizasyonu yeniden aktifleştir."""
        org = await self.get_organization_by_id(org_id)
        if not org:
            raise NotFoundError("Organization", org_id)
        
        org.is_active = True
        org.suspended_at = None
        org.suspended_reason = None
        
        await self.db.commit()
        
        logger.info(
            "Organization reactivated",
            org_id=str(org_id),
            org_name=org.name,
        )
        
        return {
            "status": "active",
            "organization_id": str(org_id),
            "organization_name": org.name,
            "message": f"Organizasyon '{org.name}' yeniden aktifleştirildi",
        }
    
    async def delete_organization(
        self,
        org_id: uuid.UUID,
        hard_delete: bool = False,
    ) -> dict:
        """Organizasyonu sil (soft veya hard delete)."""
        org = await self.get_organization_by_id(org_id)
        if not org:
            raise NotFoundError("Organization", org_id)
        
        org_name = org.name
        
        if hard_delete:
            await self.db.delete(org)
            await self.db.commit()
            
            logger.warning(
                "Organization hard deleted",
                org_id=str(org_id),
                org_name=org_name,
            )
            
            return {
                "status": "deleted",
                "organization_id": str(org_id),
                "organization_name": org_name,
                "message": f"Organizasyon '{org_name}' kalıcı olarak silindi",
            }
        else:
            org.is_active = False
            await self.db.commit()
            
            logger.info(
                "Organization soft deleted",
                org_id=str(org_id),
                org_name=org_name,
            )
            
            return {
                "status": "deactivated",
                "organization_id": str(org_id),
                "organization_name": org_name,
                "message": f"Organizasyon '{org_name}' devre dışı bırakıldı",
            }
    
    # =========================================================================
    # USER MANAGEMENT
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
                        org_response = OrganizationResponse.model_validate(m.organization)
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
    ) -> AdminUserListResponse:
        """Organizasyondaki kullanıcıları listele."""
        stmt = (
            select(User)
            .join(OrganizationUser)
            .where(OrganizationUser.organization_id == organization_id)
            .options(
                selectinload(User.organization_memberships)
                .selectinload(OrganizationUser.role),
                selectinload(User.organization_memberships)
                .selectinload(OrganizationUser.organization),
            )
        )
        count_stmt = (
            select(func.count(User.id))
            .join(OrganizationUser)
            .where(OrganizationUser.organization_id == organization_id)
        )
        
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
                if m.organization_id == organization_id:
                    if m.role:
                        role_info = RoleInfo(code=m.role.code, name=m.role.name)
                    if m.organization:
                        org_response = OrganizationResponse.model_validate(m.organization)
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
    
    async def add_user_to_organization(
        self,
        request: AddUserToOrganizationRequest,
    ) -> AddUserToOrganizationResponse:
        """Organizasyona kullanıcı ekle."""
        org = await self.get_organization_by_id(request.organization_id)
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
        
        role = await self._get_or_create_role(request.role)
        
        membership = OrganizationUser(
            user_id=user.id,
            organization_id=org.id,
            role_id=role.id,
            is_default=not existing_user,
            joined_at=datetime.now(timezone.utc),
        )
        self.db.add(membership)
        
        await self.db.commit()
        await self.db.refresh(user)
        
        logger.info(
            "User added to organization",
            user_id=str(user.id),
            org_id=str(org.id),
            role=request.role,
        )
        
        return AddUserToOrganizationResponse(
            message="Kullanıcı organizasyona eklendi",
            user=UserResponse.model_validate(user),
            organization=OrganizationResponse.model_validate(org),
            role=request.role,
        )
    
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
                    break
            elif m.is_default:
                membership = m
                target_org_id = m.organization_id
                break
        
        if not membership:
            raise NotFoundError("User membership not found")
        
        membership.role_id = role.id
        await self.db.commit()
        
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
        user.banned_at = datetime.now(timezone.utc)
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
    
    async def revoke_user_sessions_enhanced(
        self,
        user_id: uuid.UUID,
        revoke_auth0: bool = True,
    ) -> dict:
        """
        Kullanıcının tüm oturumlarını sonlandır (Redis + Auth0).
        """
        user = await self._get_user_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)
        
        revoke_results = {
            "redis_blacklisted": False,
            "auth0_revoked": False,
            "auth0_status": None,
        }
        
        # Redis'te token'ları blacklist'e ekle
        try:
            from src.core.redis import get_redis
            redis = await get_redis()
            if redis:
                blacklist_key = f"token_blacklist:user:{user_id}"
                await redis.setex(blacklist_key, 86400, "revoked")
                revoke_results["redis_blacklisted"] = True
                logger.info("User tokens blacklisted in Redis", user_id=str(user_id))
        except Exception as e:
            logger.warning(f"Redis blacklist failed: {e}")
        
        # Auth0 Management API ile session iptal
        if revoke_auth0 and user.auth0_id:
            try:
                from src.core.auth0 import get_auth0_management
                auth0_mgmt = get_auth0_management()
                
                if auth0_mgmt.is_configured:
                    result = await auth0_mgmt.revoke_user_sessions(user.auth0_id)
                    revoke_results["auth0_status"] = result.get("status")
                    revoke_results["auth0_revoked"] = result.get("status") == "revoked"
                else:
                    revoke_results["auth0_status"] = "not_configured"
            except Exception as e:
                logger.warning(f"Auth0 session revocation failed: {e}")
                revoke_results["auth0_status"] = f"error: {str(e)}"
        
        logger.warning(
            "User sessions revoked",
            user_id=str(user_id),
            user_email=user.email,
            results=revoke_results,
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
        """Kullanıcı olarak giriş yap (impersonation)."""
        from src.core.security import create_access_token
        
        target_user = await self._get_user_by_id(target_user_id)
        if not target_user:
            raise NotFoundError("User", target_user_id)
        
        # Impersonation token oluştur
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
        token = create_access_token(
            data={
                "sub": str(target_user.id),
                "email": target_user.email,
                "impersonated_by": str(admin_user.id),
                "impersonation_reason": reason,
            },
            expires_delta=timedelta(minutes=duration_minutes),
        )
        
        logger.warning(
            "User impersonation started",
            admin_id=str(admin_user.id),
            admin_email=admin_user.email,
            target_id=str(target_user_id),
            target_email=target_user.email,
            reason=reason,
            duration_minutes=duration_minutes,
        )
        
        return {
            "message": f"'{target_user.email}' kullanıcısı olarak giriş yapıldı",
            "impersonated_user": UserResponse.model_validate(target_user),
            "access_token": token,
            "expires_at": expires_at,
            "admin_user_id": admin_user.id,
        }
    
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
    ) -> Invitation:
        """Yeni davetiye oluştur."""
        org = await self.get_organization_by_id(organization_id)
        if not org:
            raise NotFoundError("Organization", organization_id)
        
        # Davet eden kişi organizasyonun üyesi mi?
        is_member = False
        is_owner = False
        for membership in invited_by.organization_memberships:
            if membership.organization_id == organization_id:
                is_member = True
                is_owner = membership.is_owner
                break
        
        if not is_member:
            raise ForbiddenError("Bu organizasyona davet gönderme yetkiniz yok")
        
        # Rol kontrolü - tenant sadece user/device atayabilir
        if role_code not in ["user", "device"]:
            if not is_owner:
                raise ForbiddenError("Sadece 'user' veya 'device' rolü atayabilirsiniz")
        
        # Aynı email için aktif davetiye var mı?
        existing = await self._get_pending_invitations(email)
        for inv in existing:
            if inv.organization_id == organization_id:
                raise ConflictError(
                    f"Bu email için zaten aktif bir davetiye var (expires: {inv.expires_at})"
                )
        
        token = secrets.token_urlsafe(32)
        
        invitation = Invitation(
            email=email,
            token=token,
            organization_id=organization_id,
            role_code=role_code,
            invited_by_id=invited_by.id,
            message=message,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_hours),
        )
        self.db.add(invitation)
        await self.db.commit()
        await self.db.refresh(invitation)
        
        logger.info(
            "Invitation created",
            invitation_id=str(invitation.id),
            email=email,
            organization_id=str(organization_id),
            role=role_code,
            invited_by=invited_by.email,
        )
        
        return invitation
    
    async def get_organization_invitations(
        self,
        organization_id: uuid.UUID,
        include_used: bool = False,
    ) -> list[Invitation]:
        """Organizasyonun davetiyelerini listele."""
        stmt = (
            select(Invitation)
            .options(
                selectinload(Invitation.organization),
                selectinload(Invitation.invited_by),
            )
            .where(Invitation.organization_id == organization_id)
            .order_by(Invitation.created_at.desc())
        )
        
        if not include_used:
            stmt = stmt.where(
                Invitation.is_used == False,
                Invitation.expires_at > datetime.now(timezone.utc),
            )
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def revoke_invitation(self, invitation_id: uuid.UUID, revoked_by: User) -> dict:
        """Davetiyeyi iptal et."""
        stmt = (
            select(Invitation)
            .options(selectinload(Invitation.organization))
            .where(Invitation.id == invitation_id)
        )
        result = await self.db.execute(stmt)
        invitation = result.scalar_one_or_none()
        
        if not invitation:
            raise NotFoundError("Invitation", invitation_id)
        
        is_authorized = False
        for membership in revoked_by.organization_memberships:
            if membership.organization_id == invitation.organization_id:
                is_authorized = True
                break
        
        if not is_authorized:
            raise ForbiddenError("Bu davetiyeyi iptal etme yetkiniz yok")
        
        await self.db.delete(invitation)
        await self.db.commit()
        
        logger.info(
            "Invitation revoked",
            invitation_id=str(invitation_id),
            email=invitation.email,
            revoked_by=revoked_by.email,
        )
        
        return {
            "status": "revoked",
            "invitation_id": str(invitation_id),
            "email": invitation.email,
            "message": f"'{invitation.email}' için davetiye iptal edildi",
        }
    
    # =========================================================================
    # ROLE & PERMISSION MANAGEMENT
    # =========================================================================
    
    async def list_all_roles(self) -> AdminRoleListResponse:
        """Tüm rolleri listele."""
        stmt = select(Role).order_by(Role.code)
        result = await self.db.execute(stmt)
        roles = result.scalars().all()
        
        return AdminRoleListResponse(
            roles=[RoleResponse.model_validate(r) for r in roles],
            total=len(roles),
        )
    
    async def list_all_permissions(self) -> AdminPermissionListResponse:
        """Tüm yetkileri listele."""
        permissions = [p.value for p in Permission]
        
        return AdminPermissionListResponse(
            permissions=permissions,
            total=len(permissions),
        )
    
    def get_available_roles(self) -> AvailableRolesResponse:
        """Sistemdeki tüm rolleri döner."""
        roles = [
            {
                "code": RoleType.ADMIN.value,
                "name": "Admin",
                "description": "Sistem yöneticisi - tüm yetkiler",
                "permissions": ROLE_PERMISSIONS[RoleType.ADMIN.value],
            },
            {
                "code": RoleType.TENANT.value,
                "name": "Tenant",
                "description": "Organizasyon yöneticisi",
                "permissions": ROLE_PERMISSIONS[RoleType.TENANT.value],
            },
            {
                "code": RoleType.USER.value,
                "name": "User",
                "description": "Normal kullanıcı - salt okunur",
                "permissions": ROLE_PERMISSIONS[RoleType.USER.value],
            },
            {
                "code": RoleType.DEVICE.value,
                "name": "Device",
                "description": "Cihaz/Telemetri erişimi",
                "permissions": ROLE_PERMISSIONS[RoleType.DEVICE.value],
            },
        ]
        return AvailableRolesResponse(roles=roles)
    
    def get_available_permissions(self) -> AvailablePermissionsResponse:
        """Sistemdeki tüm yetkileri döner."""
        permissions = [
            {"code": p.value, "description": p.value.replace(":", " ").replace("_", " ").title()}
            for p in Permission
        ]
        return AvailablePermissionsResponse(permissions=permissions)
    
    def get_available_modules(self) -> AvailableModulesResponse:
        """Sistemdeki tüm modülleri döner."""
        module_names = {
            ModuleType.CORE.value: "Core",
            ModuleType.ASSET_MANAGEMENT.value: "Asset Management",
            ModuleType.IOT.value: "IoT",
            ModuleType.TELEMETRY.value: "Telemetry",
            ModuleType.ENERGY.value: "Energy",
            ModuleType.REWARDS.value: "Rewards",
            ModuleType.BILLING.value: "Billing",
            ModuleType.COMPLIANCE.value: "Compliance",
            ModuleType.NOTIFICATIONS.value: "Notifications",
            ModuleType.DASHBOARD.value: "Dashboard",
        }
        
        module_descriptions = {
            ModuleType.CORE.value: "Temel özellikler (auth, org, user)",
            ModuleType.ASSET_MANAGEMENT.value: "Asset ve Zone yönetimi",
            ModuleType.IOT.value: "Gateway ve cihaz yönetimi",
            ModuleType.TELEMETRY.value: "Telemetri verileri",
            ModuleType.ENERGY.value: "EPİAŞ, Recommendation, Core Loop",
            ModuleType.REWARDS.value: "AWX puan sistemi, Ledger",
            ModuleType.BILLING.value: "Cüzdan ve işlemler",
            ModuleType.COMPLIANCE.value: "KVKK/GDPR, Audit logs",
            ModuleType.NOTIFICATIONS.value: "Push, Telegram, Email bildirimleri",
            ModuleType.DASHBOARD.value: "Analitik ve raporlar",
        }
        
        modules = [
            ModuleInfo(
                code=m.value,
                name=module_names.get(m.value, m.value),
                description=module_descriptions.get(m.value),
                permissions=MODULE_PERMISSIONS.get(m.value, []),
            )
            for m in ModuleType
        ]
        return AvailableModulesResponse(modules=modules)
    
    # =========================================================================
    # MODULE MANAGEMENT
    # =========================================================================
    
    async def update_organization_modules(
        self,
        org_id: uuid.UUID,
        modules: list[str],
    ) -> dict:
        """Organizasyonun modüllerini güncelle."""
        org = await self.get_organization_by_id(org_id)
        if not org:
            raise NotFoundError("Organization", org_id)
        
        # Core modülü her zaman ekle
        modules_to_set = set(modules)
        modules_to_set.add(ModuleType.CORE.value)
        
        # Mevcut modülleri al
        stmt = select(OrganizationModule).where(
            OrganizationModule.organization_id == org_id
        )
        result = await self.db.execute(stmt)
        existing_modules = {m.module_code: m for m in result.scalars().all()}
        
        now = datetime.now(timezone.utc)
        
        # Yeni modülleri ekle, mevcut olmayanları deaktif et
        for module_code in modules_to_set:
            if module_code not in [m.value for m in ModuleType]:
                continue
            
            if module_code in existing_modules:
                existing_modules[module_code].is_active = True
            else:
                org_module = OrganizationModule(
                    organization_id=org_id,
                    module_code=module_code,
                    is_active=True,
                    activated_at=now,
                )
                self.db.add(org_module)
        
        # Listede olmayan modülleri deaktif et
        for module_code, module in existing_modules.items():
            if module_code not in modules_to_set:
                module.is_active = False
        
        await self.db.commit()
        
        active_modules = await self._get_organization_modules(org_id)
        
        return {
            "status": "updated",
            "organization_id": str(org_id),
            "active_modules": active_modules,
            "message": f"Modüller güncellendi: {', '.join(active_modules)}",
        }
    
    # =========================================================================
    # OWNERSHIP TRANSFER
    # =========================================================================
    
    async def transfer_ownership(
        self,
        org_id: uuid.UUID,
        new_owner_user_id: uuid.UUID,
    ) -> dict:
        """Organizasyon sahipliğini devret."""
        org = await self.get_organization_by_id(org_id)
        if not org:
            raise NotFoundError("Organization", org_id)
        
        new_owner = await self._get_user_by_id(new_owner_user_id)
        if not new_owner:
            raise NotFoundError("User", new_owner_user_id)
        
        # Yeni sahip organizasyonun üyesi mi?
        stmt = select(OrganizationUser).where(
            OrganizationUser.user_id == new_owner_user_id,
            OrganizationUser.organization_id == org_id,
        )
        result = await self.db.execute(stmt)
        new_owner_membership = result.scalar_one_or_none()
        
        if not new_owner_membership:
            raise ConflictError("Yeni sahip bu organizasyonun üyesi değil")
        
        # Rolleri al
        tenant_role = await self._get_or_create_role(RoleType.TENANT.value)
        user_role = await self._get_or_create_role(RoleType.USER.value)
        
        # Mevcut sahipleri bul ve user rolüne düşür
        stmt = (
            select(OrganizationUser)
            .options(selectinload(OrganizationUser.user))
            .where(
                OrganizationUser.organization_id == org_id,
                OrganizationUser.is_owner == True,
            )
        )
        result = await self.db.execute(stmt)
        current_owners = result.scalars().all()
        
        current_owner_email = None
        for owner in current_owners:
            owner.is_owner = False
            owner.role_id = user_role.id
            if owner.user:
                current_owner_email = owner.user.email
        
        # Yeni sahibe tenant rolü ver
        new_owner_membership.is_owner = True
        new_owner_membership.role_id = tenant_role.id
        new_owner_membership.is_default = True
        
        await self.db.commit()
        
        logger.info(
            "Organization ownership transferred",
            org_id=str(org_id),
            org_name=org.name,
            old_owner_email=current_owner_email,
            new_owner_email=new_owner.email,
        )
        
        return {
            "status": "transferred",
            "organization_id": str(org_id),
            "organization_name": org.name,
            "old_owner_email": current_owner_email,
            "new_owner_id": str(new_owner_user_id),
            "new_owner_email": new_owner.email,
            "message": f"Organizasyon sahipliği '{new_owner.email}' kullanıcısına devredildi",
        }
    
    # =========================================================================
    # PRIVATE HELPER METHODS
    # =========================================================================
    
    async def _get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        """Get user by ID with relationships."""
        stmt = (
            select(User)
            .options(
                selectinload(User.organization_memberships)
                .selectinload(OrganizationUser.role),
                selectinload(User.organization_memberships)
                .selectinload(OrganizationUser.organization),
            )
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
        
        if role:
            return role
        
        role_names = {
            RoleType.ADMIN.value: "Admin",
            RoleType.TENANT.value: "Tenant",
            RoleType.USER.value: "User",
            RoleType.DEVICE.value: "Device",
        }
        
        permissions = ROLE_PERMISSIONS.get(role_code, [])
        
        role = Role(
            code=role_code,
            name=role_names.get(role_code, role_code.title()),
            permissions=permissions,
        )
        self.db.add(role)
        await self.db.flush()
        
        logger.info("Role created", role_code=role_code)
        return role
    
    async def _get_organization_modules(self, organization_id: uuid.UUID) -> list[str]:
        """Organizasyonun aktif modüllerini döner."""
        stmt = select(OrganizationModule).where(
            OrganizationModule.organization_id == organization_id,
            OrganizationModule.is_active == True,
        )
        result = await self.db.execute(stmt)
        modules = result.scalars().all()
        
        return [m.module_code for m in modules]
    
    async def _get_pending_invitations(self, email: str) -> list[Invitation]:
        """Bekleyen davetiyeleri getir."""
        stmt = (
            select(Invitation)
            .where(
                Invitation.email == email,
                Invitation.is_used == False,
                Invitation.expires_at > datetime.now(timezone.utc),
            )
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def _get_organization_wallet_summary(self, org_uuid: uuid.UUID) -> OrganizationWalletSummary:
        """Organizasyonun COMPANY wallet özetini getir."""
        from decimal import Decimal
        
        try:
            from src.modules.billing.models import Wallet, WalletType
            
            wallet_stmt = select(Wallet).where(
                Wallet.organization_id == org_uuid,
                Wallet.wallet_type == WalletType.COMPANY,
            )
            wallet_result = await self.db.execute(wallet_stmt)
            wallets = wallet_result.scalars().all()
            
            if not wallets:
                return OrganizationWalletSummary(
                    wallet_count=0,
                    balances={},
                    total_balance_try="0.00",
                )
            
            balances = {}
            total_try = Decimal("0")
            for w in wallets:
                balances[w.currency] = str(w.balance)
                if w.currency == "TRY":
                    total_try = w.balance
            
            return OrganizationWalletSummary(
                wallet_count=len(wallets),
                balances=balances,
                total_balance_try=str(total_try),
            )
        except Exception as e:
            logger.warning(f"Could not get wallet summary: {e}")
            return OrganizationWalletSummary(
                wallet_count=0,
                balances={},
                total_balance_try="0.00",
            )
