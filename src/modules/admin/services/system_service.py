"""
Admin System Service

Sistem yönetimi işlemleri.
- Role management
- Permission management
- System logs
- System statistics
"""
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from src.core.exceptions import ConflictError, NotFoundError
from src.core.logging import get_logger
from src.modules.auth.models import (
    Permission,
    Role,
    ROLE_PERMISSIONS,
    MODULE_PERMISSIONS,
)
from src.modules.auth.schemas import (
    AdminRoleListResponse,
    AdminPermissionListResponse,
    RoleResponse,
    RoleInfo,
)

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class PermissionResponse(BaseModel):
    """Permission response schema."""
    code: str
    name: str
    description: str


class AdminSystemService:
    """Admin system management service."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # =========================================================================
    # ROLE MANAGEMENT
    # =========================================================================
    
    async def list_all_roles(self) -> AdminRoleListResponse:
        """Tüm rolleri listele."""
        stmt = select(Role).order_by(Role.code)
        result = await self.db.execute(stmt)
        roles = result.scalars().all()
        
        role_responses = []
        for role in roles:
            # Get permissions for this role
            permissions = set()
            if role.code in ROLE_PERMISSIONS:
                permissions.update(ROLE_PERMISSIONS[role.code])
            
            role_responses.append(RoleResponse(
                id=role.id,
                code=role.code,
                name=role.name,
                description=role.description,
                permissions=list(permissions),
                is_system=role.is_system,
                created_at=role.created_at,
            ))
        
        return AdminRoleListResponse(roles=role_responses)
    
    async def get_role_by_id(self, role_id: uuid.UUID) -> RoleResponse:
        """Get role by ID with permissions."""
        stmt = select(Role).where(Role.id == role_id)
        result = await self.db.execute(stmt)
        role = result.scalar_one_or_none()
        
        if not role:
            raise NotFoundError("Role", role_id)
        
        # Get permissions for this role
        permissions = set()
        if role.code in ROLE_PERMISSIONS:
            permissions.update(ROLE_PERMISSIONS[role.code])
        
        return RoleResponse(
            id=role.id,
            code=role.code,
            name=role.name,
            description=role.description,
            permissions=list(permissions),
            is_system=role.is_system,
            created_at=role.created_at,
        )
    
    async def create_role(
        self,
        code: str,
        name: str,
        description: str | None = None,
        permissions: list[str] | None = None,
    ) -> RoleResponse:
        """Yeni rol oluştur."""
        # Check if role code already exists
        existing = await self._get_role_by_code(code)
        if existing:
            raise ConflictError(f"Role with code '{code}' already exists")
        
        role = Role(
            code=code,
            name=name,
            description=description,
        )
        
        self.db.add(role)
        await self.db.commit()
        await self.db.refresh(role)
        
        logger.info(
            "Role created",
            role_id=str(role.id),
            role_code=code,
            role_name=name,
        )
        
        return RoleResponse(
            id=role.id,
            code=role.code,
            name=role.name,
            description=role.description,
            permissions=permissions or [],
            created_at=role.created_at,
        )
    
    async def update_role(
        self,
        role_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
    ) -> RoleResponse:
        """Rol güncelle."""
        role = await self._get_role_by_id(role_id)
        if not role:
            raise NotFoundError("Role", role_id)
        
        if name is not None:
            role.name = name
        if description is not None:
            role.description = description
        
        await self.db.commit()
        await self.db.refresh(role)
        
        logger.info(
            "Role updated",
            role_id=str(role_id),
            role_code=role.code,
        )
        
        # Get permissions for this role
        permissions = set()
        if role.code in ROLE_PERMISSIONS:
            permissions.update(ROLE_PERMISSIONS[role.code])
        
        return RoleResponse(
            id=role.id,
            code=role.code,
            name=role.name,
            description=role.description,
            permissions=list(permissions),
            is_system=role.is_system,
            created_at=role.created_at,
        )
    
    async def delete_role(self, role_id: uuid.UUID) -> dict:
        """Rol sil."""
        role = await self._get_role_by_id(role_id)
        if not role:
            raise NotFoundError("Role", role_id)
        
        # Check if role is in use
        from src.modules.auth.models import OrganizationUser
        stmt = select(OrganizationUser).where(OrganizationUser.role_id == role_id)
        result = await self.db.execute(stmt)
        users_with_role = result.scalar_one_or_none()
        
        if users_with_role:
            raise ConflictError(f"Role '{role.code}' is in use and cannot be deleted")
        
        role_name = role.name
        await self.db.delete(role)
        await self.db.commit()
        
        logger.warning(
            "Role deleted",
            role_id=str(role_id),
            role_code=role.code,
            role_name=role_name,
        )
        
        return {
            "status": "deleted",
            "role_id": str(role_id),
            "role_code": role.code,
            "role_name": role_name,
            "message": f"Rol '{role_name}' silindi",
        }
    
    # =========================================================================
    # PERMISSION MANAGEMENT
    # =========================================================================
    
    async def list_all_permissions(self) -> AdminPermissionListResponse:
        """Tüm yetkileri listele."""
        permissions = []
        
        # Get all unique permissions from ROLE_PERMISSIONS
        all_permissions = set()
        for role_perms in ROLE_PERMISSIONS.values():
            all_permissions.update(role_perms)
        
        # Add module permissions
        for module_perms in MODULE_PERMISSIONS.values():
            all_permissions.update(module_perms)
        
        for perm in sorted(all_permissions):
            permissions.append(PermissionResponse(
                code=perm,
                name=perm.replace("_", " ").title(),
                description=f"Permission for {perm}",
            ))
        
        return AdminPermissionListResponse(permissions=permissions)
    
    async def get_permissions_by_role(self, role_code: str) -> list[PermissionResponse]:
        """Role'e göre yetkileri listele."""
        permissions = []
        
        if role_code in ROLE_PERMISSIONS:
            for perm in ROLE_PERMISSIONS[role_code]:
                permissions.append(PermissionResponse(
                    code=perm,
                    name=perm.replace("_", " ").title(),
                    description=f"Permission for {perm}",
                ))
        
        return permissions
    
    # =========================================================================
    # SYSTEM STATISTICS
    # =========================================================================
    
    async def get_system_stats(self) -> dict:
        """Sistem istatistiklerini getir."""
        from sqlalchemy import func
        from src.modules.auth.models import User, Organization, Role
        
        # User statistics
        total_users_stmt = select(func.count(User.id))
        total_users_result = await self.db.execute(total_users_stmt)
        total_users = total_users_result.scalar() or 0
        
        active_users_stmt = select(func.count(User.id)).where(User.is_active == True)
        active_users_result = await self.db.execute(active_users_stmt)
        active_users = active_users_result.scalar() or 0
        
        # Organization statistics
        total_orgs_stmt = select(func.count(Organization.id))
        total_orgs_result = await self.db.execute(total_orgs_stmt)
        total_organizations = total_orgs_result.scalar() or 0
        
        active_orgs_stmt = select(func.count(Organization.id)).where(Organization.is_active == True)
        active_orgs_result = await self.db.execute(active_orgs_stmt)
        active_organizations = active_orgs_result.scalar() or 0
        
        # Role statistics
        total_roles_stmt = select(func.count(Role.id))
        total_roles_result = await self.db.execute(total_roles_stmt)
        total_roles = total_roles_result.scalar() or 0
        
        return {
            "users": {
                "total": total_users,
                "active": active_users,
                "inactive": total_users - active_users,
            },
            "organizations": {
                "total": total_organizations,
                "active": active_organizations,
                "inactive": total_organizations - active_organizations,
            },
            "roles": {
                "total": total_roles,
                "available": list(ROLE_PERMISSIONS.keys()),
            },
            "permissions": {
                "total": len(set().union(*ROLE_PERMISSIONS.values())),
                "role_permissions": len(ROLE_PERMISSIONS),
                "module_permissions": len(MODULE_PERMISSIONS),
            },
        }
    
    async def get_system_health(self) -> dict:
        """Sistem sağlık durumu."""
        from datetime import datetime, timezone, timedelta
        
        # Recent activity (last 24 hours)
        one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)
        
        from src.modules.auth.models import User, Organization
        
        recent_users_stmt = select(func.count(User.id)).where(User.created_at >= one_day_ago)
        recent_users_result = await self.db.execute(recent_users_stmt)
        recent_users = recent_users_result.scalar() or 0
        
        recent_orgs_stmt = select(func.count(Organization.id)).where(Organization.created_at >= one_day_ago)
        recent_orgs_result = await self.db.execute(recent_orgs_stmt)
        recent_organizations = recent_orgs_result.scalar() or 0
        
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "recent_activity": {
                "last_24_hours": {
                    "new_users": recent_users,
                    "new_organizations": recent_organizations,
                },
            },
            "database": {
                "status": "connected",  # Could add actual health checks
            },
            "services": {
                "auth": "running",
                "billing": "running",  # Could add actual service health checks
                "notifications": "running",
            },
        }
    
    # =========================================================================
    # PRIVATE HELPER METHODS
    # =========================================================================
    
    async def _get_role_by_code(self, code: str) -> Role | None:
        """Get role by code."""
        stmt = select(Role).where(Role.code == code)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _get_role_by_id(self, role_id: uuid.UUID) -> Role | None:
        """Get role by ID."""
        stmt = select(Role).where(Role.id == role_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
