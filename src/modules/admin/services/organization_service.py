"""
Admin Organization Service

Organizasyon yönetimi işlemleri.
- Organization CRUD
- Module management
- Organization statistics
- Transfer ownership
"""
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.exceptions import NotFoundError
from src.core.logging import get_logger
from src.modules.auth.models import (
    ModuleType,
    Organization,
    OrganizationModule,
    OrganizationUser,
    Role,
    User,
)
from src.modules.auth.schemas import (
    AdminOrganizationDetailResponse,
    AdminOrganizationListItem,
    AdminOrganizationListResponse,
    CreateOrganizationStep2Request,
    CreateOrganizationStep2Response,
    OrganizationModuleResponse,
    OrganizationResponse,
    OrganizationWalletSummary,
    OrganizationWithModulesResponse,
)

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class AdminOrganizationService:
    """Admin organization management service."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # =========================================================================
    # ORGANIZATION CRUD
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
    
    async def list_all_organizations(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> AdminOrganizationListResponse:
        """Tüm organizasyonları listele (Admin için)."""
        
        # 1. Alt sorgular (Subqueries) hazırla - N+1 SOLUTION
        user_count_sub = (
            select(
                OrganizationUser.organization_id,
                func.count(OrganizationUser.id).label("user_count")
            )
            .group_by(OrganizationUser.organization_id)
            .subquery()
        )
        
        # Device count için subquery (try/catch ile)
        device_count_sub = None
        try:
            from src.modules.iot.models import Device
            device_count_sub = (
                select(
                    Device.organization_id,
                    func.count(Device.id).label("device_count")
                )
                .group_by(Device.organization_id)
                .subquery()
            )
        except Exception as e:
            # IoT modülü yoksa device_count = 0 olarak kalacak
            logger.debug("IoT module not available for device count", error=str(e))
        
        # 2. Ana sorguyu oluştur - TEK SORGUDA HER ŞEYİ ÇEK
        stmt = (
            select(Organization, user_count_sub.c.user_count)
            .outerjoin(user_count_sub, Organization.id == user_count_sub.c.organization_id)
            .options(selectinload(Organization.modules))  # Modülleri tek sorguda çek
        )
        
        # Device count'u ekle (varsa)
        if device_count_sub is not None:
            stmt = stmt.outerjoin(
                device_count_sub, Organization.id == device_count_sub.c.organization_id
            ).add_columns(device_count_sub.c.device_count)
        
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
        
        # 3. Memory'de işle - DB'YE GİTMEDEN
        items = []
        if device_count_sub:
            rows = result.all()  # [(Org, user_count, device_count), ...]
            for org, user_count, device_count in rows:
                modules = [m.module_code for m in org.modules if m.is_active]
                
                items.append(AdminOrganizationListItem(
                    id=org.id,
                    name=org.name,
                    slug=org.slug,
                    email=org.email,
                    is_active=org.is_active,
                    created_at=org.created_at,
                    user_count=user_count or 0,
                    device_count=device_count or 0,
                    modules=modules,
                ))
        else:
            rows = result.all()  # [(Org, user_count), ...]
            for org, user_count in rows:
                modules = [m.module_code for m in org.modules if m.is_active]
                
                items.append(AdminOrganizationListItem(
                    id=org.id,
                    name=org.name,
                    slug=org.slug,
                    email=org.email,
                    is_active=org.is_active,
                    created_at=org.created_at,
                    user_count=user_count or 0,
                    device_count=0,
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
                from src.modules.auth.schemas import RoleInfo
                role_info = None
                if m.role:
                    role_info = RoleInfo(code=m.role.code, name=m.role.name)
                
                users.append({
                    "id": m.user.id,
                    "email": m.user.email,
                    "full_name": m.user.full_name,
                    "phone": m.user.phone,
                    "is_active": m.user.is_active,
                    "created_at": m.user.created_at,
                    "last_login": m.user.last_login,
                    "role": role_info,
                })
        
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
                User.is_active
            )
        )
        
        role_distribution_stmt = (
            select(Role.code, func.count(User.id))
            .join(OrganizationUser, Role.id == OrganizationUser.role_id)
            .join(User, User.id == OrganizationUser.user_id)
            .where(OrganizationUser.organization_id == org_uuid)
            .group_by(Role.code)
        )
        
        thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
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
    
    # =========================================================================
    # ORGANIZATION ACTIONS
    # =========================================================================
    
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
        org.suspended_at = datetime.now(UTC)
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
    
    async def transfer_ownership(
        self,
        org_id: uuid.UUID,
        new_owner_user_id: uuid.UUID,
    ) -> dict:
        """Organizasyon sahipliğini devret."""
        org = await self.get_organization_by_id(org_id)
        if not org:
            raise NotFoundError("Organization", org_id)
        
        # Yeni sahibi organizasyon üyesi olmalı
        stmt = select(OrganizationUser).where(
            OrganizationUser.organization_id == org_id,
            OrganizationUser.user_id == new_owner_user_id,
        )
        result = await self.db.execute(stmt)
        membership = result.scalar_one_or_none()
        
        if not membership:
            raise NotFoundError("User is not a member of this organization")
        
        # Yeni sahibe tenant rolü ata
        tenant_role = await self._get_or_create_role("tenant")
        membership.role_id = tenant_role.id
        
        await self.db.commit()
        
        logger.info(
            "Organization ownership transferred",
            org_id=str(org_id),
            org_name=org.name,
            new_owner_id=str(new_owner_user_id),
        )
        
        return {
            "status": "transferred",
            "organization_id": str(org_id),
            "organization_name": org.name,
            "new_owner_id": str(new_owner_user_id),
            "message": f"Organizasyon '{org.name}' sahipliği devredildi",
        }
    
    # =========================================================================
    # MODULE MANAGEMENT
    # =========================================================================
    
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
        
        now = datetime.now(UTC)
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
    
    async def update_organization_modules(
        self,
        org_id: uuid.UUID,
        modules: list[str],
    ) -> dict:
        """Organizasyon modüllerini güncelle."""
        org = await self.get_organization_by_id(org_id)
        if not org:
            raise NotFoundError("Organization", org_id)
        
        # Mevcut modülleri getir
        stmt = select(OrganizationModule).where(
            OrganizationModule.organization_id == org_id
        )
        result = await self.db.execute(stmt)
        existing_modules = result.scalars().all()
        
        # Mevcut modülleri kapat
        for module in existing_modules:
            module.is_active = False
        
        # Yeni modülleri aç
        for module_code in modules:
            if module_code not in [m.value for m in ModuleType]:
                continue
            
            # Mevcut modülü bul ve aktifleştir
            for module in existing_modules:
                if module.module_code == module_code:
                    module.is_active = True
                    module.activated_at = datetime.now(UTC)
                    break
            else:
                # Yeni modül oluştur
                new_module = OrganizationModule(
                    organization_id=org_id,
                    module_code=module_code,
                    is_active=True,
                    activated_at=datetime.now(UTC),
                )
                self.db.add(new_module)
        
        await self.db.commit()
        
        logger.info(
            "Organization modules updated",
            org_id=str(org_id),
            modules=modules,
        )
        
        return {
            "status": "updated",
            "organization_id": str(org_id),
            "modules": modules,
            "message": "Organizasyon modülleri güncellendi",
        }
    
    # =========================================================================
    # PRIVATE HELPER METHODS
    # =========================================================================
    
    async def _get_organization_modules(self, organization_id: uuid.UUID) -> list[str]:
        """Organizasyonun aktif modüllerini döner."""
        stmt = select(OrganizationModule).where(
            OrganizationModule.organization_id == organization_id,
            OrganizationModule.is_active,
        )
        result = await self.db.execute(stmt)
        modules = result.scalars().all()
        
        return [m.module_code for m in modules]
    
    async def _get_organization_wallet_summary(self, org_uuid: uuid.UUID) -> OrganizationWalletSummary:
        """Organizasyonun COMPANY wallet özetini getir."""
        from decimal import Decimal
        
        try:
            from src.modules.billing.models import WalletType
            from src.modules.billing.service import BillingService
            
            # BillingService oluştur
            billing_service = BillingService(self.db, org_uuid)
            
            # Company wallet'larını getir
            wallets = await billing_service.list_wallets()
            
            total_balance = Decimal("0")
            currency_balance = {}
            
            for wallet in wallets:
                if wallet.wallet_type == WalletType.COMPANY:
                    total_balance += wallet.balance
                    currency_balance[wallet.currency] = wallet.balance
            
            return OrganizationWalletSummary(
                total_balance=float(total_balance),
                currency_balance=currency_balance,
                wallet_count=len([w for w in wallets if w.wallet_type == WalletType.COMPANY]),
            )
        except Exception as e:
            logger.warning(f"Could not get wallet summary for org {org_uuid}: {e}")
            return OrganizationWalletSummary(
                total_balance=0.0,
                currency_balance={},
                wallet_count=0,
            )
    
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
