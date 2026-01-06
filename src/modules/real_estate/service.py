"""
RealEstate Module - Business Logic Service
"""
import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.exceptions import ConflictError, NotFoundError, ValidationError
from src.core.logging import get_logger
from src.modules.real_estate.models import (
    Asset, AssetType, Lease, Zone, AssetMembership, Tenancy, HandoverToken, TenancyStatus
)
from src.modules.real_estate.schemas import (
    AssetCreate,
    AssetUpdate,
    LeaseCreate,
    LeaseUpdate,
    ZoneCreate,
    TenancyCreate,
    AssetMembershipCreate,
)

logger = get_logger(__name__)


class RealEstateService:
    """Real estate management service."""
    
    def __init__(self, db: AsyncSession, organization_id: uuid.UUID):
        self.db = db
        self.organization_id = organization_id
    
    # ============== Asset Operations ==============
    
    async def get_asset_by_id(self, asset_id: uuid.UUID) -> Asset | None:
        """Get asset by ID within organization."""
        stmt = (
            select(Asset)
            .options(selectinload(Asset.children))
            .where(
                Asset.id == asset_id,
                Asset.organization_id == self.organization_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_asset_by_code(self, code: str) -> Asset | None:
        """Get asset by code within organization."""
        stmt = select(Asset).where(
            Asset.code == code,
            Asset.organization_id == self.organization_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_assets(
        self,
        asset_type: AssetType | None = None,
        parent_id: uuid.UUID | None = None,
        root_only: bool = False,
    ) -> Sequence[Asset]:
        """
        List assets with optional filters.
        
        Args:
            asset_type: Filter by asset type
            parent_id: Filter by parent asset
            root_only: Only return root assets (no parent)
        """
        stmt = select(Asset).where(Asset.organization_id == self.organization_id)
        
        if asset_type:
            stmt = stmt.where(Asset.asset_type == asset_type)
        
        if parent_id:
            stmt = stmt.where(Asset.parent_id == parent_id)
        elif root_only:
            stmt = stmt.where(Asset.parent_id.is_(None))
        
        stmt = stmt.order_by(Asset.asset_type, Asset.name)
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def create_asset(self, data: AssetCreate) -> Asset:
        """Create a new asset."""
        # Check code uniqueness
        existing = await self.get_asset_by_code(data.code)
        if existing:
            raise ConflictError(f"Asset with code '{data.code}' already exists")
        
        # Validate parent hierarchy
        if data.parent_id:
            parent = await self.get_asset_by_id(data.parent_id)
            if not parent:
                raise NotFoundError("Parent Asset", data.parent_id)
            
            # Validate hierarchy rules
            self._validate_hierarchy(parent.asset_type, data.asset_type)
        
        asset = Asset(
            organization_id=self.organization_id,
            **data.model_dump(exclude_unset=True, by_alias=True),
        )
        self.db.add(asset)
        await self.db.commit()
        await self.db.refresh(asset)
        
        logger.info(
            "Asset created",
            asset_id=str(asset.id),
            code=asset.code,
            type=asset.asset_type,
        )
        return asset
    
    async def update_asset(self, asset_id: uuid.UUID, data: AssetUpdate) -> Asset:
        """Update an asset."""
        asset = await self.get_asset_by_id(asset_id)
        if not asset:
            raise NotFoundError("Asset", asset_id)
        
        # Check code uniqueness if changing
        if data.code and data.code != asset.code:
            existing = await self.get_asset_by_code(data.code)
            if existing:
                raise ConflictError(f"Asset with code '{data.code}' already exists")
        
        update_data = data.model_dump(exclude_unset=True, by_alias=True)
        for field, value in update_data.items():
            setattr(asset, field, value)
        
        await self.db.commit()
        await self.db.refresh(asset)
        return asset
    
    async def delete_asset(self, asset_id: uuid.UUID) -> None:
        """Delete an asset and all its children (cascade)."""
        asset = await self.get_asset_by_id(asset_id)
        if not asset:
            raise NotFoundError("Asset", asset_id)
        
        await self.db.delete(asset)
        await self.db.commit()
        
        logger.info("Asset deleted", asset_id=str(asset_id))
    
    async def get_asset_hierarchy(self, root_id: uuid.UUID | None = None) -> list[Asset]:
        """
        Get full asset hierarchy starting from root or specific asset.
        Returns assets with children loaded recursively.
        """
        if root_id:
            root = await self.get_asset_by_id(root_id)
            if not root:
                raise NotFoundError("Asset", root_id)
            return [root]
        
        # Get all root assets with children
        stmt = (
            select(Asset)
            .options(selectinload(Asset.children).selectinload(Asset.children))
            .where(
                Asset.organization_id == self.organization_id,
                Asset.parent_id.is_(None),
            )
            .order_by(Asset.name)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    def _validate_hierarchy(self, parent_type: AssetType, child_type: AssetType) -> None:
        """Validate parent-child hierarchy rules."""
        valid_children = {
            AssetType.SITE: [AssetType.BLOCK, AssetType.COMMON_AREA],
            AssetType.BLOCK: [AssetType.FLOOR, AssetType.COMMON_AREA],
            AssetType.FLOOR: [AssetType.UNIT, AssetType.COMMON_AREA, AssetType.METER_POINT],
            AssetType.UNIT: [AssetType.METER_POINT],
            AssetType.COMMON_AREA: [AssetType.METER_POINT],
            AssetType.METER_POINT: [],
        }
        
        allowed = valid_children.get(parent_type, [])
        if child_type not in allowed:
            raise ValidationError(
                f"Cannot create {child_type.value} under {parent_type.value}",
                details={
                    "parent_type": parent_type.value,
                    "child_type": child_type.value,
                    "allowed_children": [t.value for t in allowed],
                },
            )
    
    # ============== Lease Operations ==============
    
    async def get_lease_by_id(self, lease_id: uuid.UUID) -> Lease | None:
        """Get lease by ID within organization."""
        stmt = (
            select(Lease)
            .options(selectinload(Lease.asset))
            .where(
                Lease.id == lease_id,
                Lease.organization_id == self.organization_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_leases(
        self,
        asset_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> Sequence[Lease]:
        """List leases with optional filters."""
        stmt = (
            select(Lease)
            .options(selectinload(Lease.asset))
            .where(Lease.organization_id == self.organization_id)
        )
        
        if asset_id:
            stmt = stmt.where(Lease.asset_id == asset_id)
        
        if status:
            stmt = stmt.where(Lease.status == status)
        
        stmt = stmt.order_by(Lease.start_date.desc())
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def create_lease(self, data: LeaseCreate) -> Lease:
        """Create a new lease."""
        # Verify asset exists
        asset = await self.get_asset_by_id(data.asset_id)
        if not asset:
            raise NotFoundError("Asset", data.asset_id)
        
        # Validate dates
        if data.end_date <= data.start_date:
            raise ValidationError("End date must be after start date")
        
        lease = Lease(
            organization_id=self.organization_id,
            **data.model_dump(),
        )
        self.db.add(lease)
        await self.db.commit()
        await self.db.refresh(lease)
        
        logger.info(
            "Lease created",
            lease_id=str(lease.id),
            asset_id=str(data.asset_id),
            tenant=data.tenant_name,
        )
        return lease
    
    async def update_lease(self, lease_id: uuid.UUID, data: LeaseUpdate) -> Lease:
        """Update a lease."""
        lease = await self.get_lease_by_id(lease_id)
        if not lease:
            raise NotFoundError("Lease", lease_id)
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(lease, field, value)
        
        await self.db.commit()
        await self.db.refresh(lease)
        return lease
    
    async def delete_lease(self, lease_id: uuid.UUID) -> None:
        """Delete a lease."""
        lease = await self.get_lease_by_id(lease_id)
        if not lease:
            raise NotFoundError("Lease", lease_id)
        
        await self.db.delete(lease)
        await self.db.commit()
        
        logger.info("Lease deleted", lease_id=str(lease_id))
    
    # ============== Zone Operations ==============
    
    async def list_zones(self, asset_id: uuid.UUID) -> Sequence[Zone]:
        """List zones for an asset."""
        stmt = select(Zone).where(Zone.asset_id == asset_id).order_by(Zone.name)
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def create_zone(self, data: ZoneCreate) -> Zone:
        """Create a new zone."""
        asset = await self.get_asset_by_id(data.asset_id)
        if not asset:
            raise NotFoundError("Asset", data.asset_id)
        
        zone = Zone(**data.model_dump())
        self.db.add(zone)
        await self.db.commit()
        await self.db.refresh(zone)
        
        logger.info("Zone created", zone_id=str(zone.id), asset_id=str(data.asset_id))
        return zone
    
    async def delete_zone(self, zone_id: uuid.UUID) -> None:
        """Delete a zone."""
        stmt = select(Zone).where(Zone.id == zone_id)
        result = await self.db.execute(stmt)
        zone = result.scalar_one_or_none()
        
        if not zone:
            raise NotFoundError("Zone", zone_id)
        
        await self.db.delete(zone)
        await self.db.commit()
    
    # ============== Asset Membership Operations ==============
    
    async def list_memberships(self, asset_id: uuid.UUID) -> Sequence[AssetMembership]:
        """List memberships for an asset."""
        stmt = (
            select(AssetMembership)
            .where(AssetMembership.asset_id == asset_id)
            .order_by(AssetMembership.created_at)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def add_membership(self, data: AssetMembershipCreate) -> AssetMembership:
        """Add a user to an asset with specific relation and scopes."""
        asset = await self.get_asset_by_id(data.asset_id)
        if not asset:
            raise NotFoundError("Asset", data.asset_id)
        
        membership = AssetMembership(**data.model_dump())
        self.db.add(membership)
        await self.db.commit()
        await self.db.refresh(membership)
        
        logger.info(
            "Membership added",
            asset_id=str(data.asset_id),
            user_id=str(data.user_id),
            relation=data.relation,
        )
        return membership
    
    async def revoke_membership(self, membership_id: uuid.UUID) -> AssetMembership:
        """Revoke an asset membership."""
        from datetime import datetime, timezone
        
        stmt = select(AssetMembership).where(AssetMembership.id == membership_id)
        result = await self.db.execute(stmt)
        membership = result.scalar_one_or_none()
        
        if not membership:
            raise NotFoundError("AssetMembership", membership_id)
        
        membership.revoked_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(membership)
        return membership
    
    # ============== Tenancy Operations ==============
    
    async def list_tenancies(self, asset_id: uuid.UUID) -> Sequence[Tenancy]:
        """List tenancies for an asset."""
        stmt = (
            select(Tenancy)
            .where(Tenancy.asset_id == asset_id)
            .order_by(Tenancy.start_at.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_active_tenancy(self, asset_id: uuid.UUID) -> Tenancy | None:
        """Get active tenancy for an asset."""
        stmt = select(Tenancy).where(
            Tenancy.asset_id == asset_id,
            Tenancy.status == TenancyStatus.ACTIVE.value,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def create_tenancy(self, data: TenancyCreate) -> Tenancy:
        """Create a new tenancy."""
        asset = await self.get_asset_by_id(data.asset_id)
        if not asset:
            raise NotFoundError("Asset", data.asset_id)
        
        # Check for existing active tenancy
        existing = await self.get_active_tenancy(data.asset_id)
        if existing:
            raise ConflictError("Asset already has an active tenancy")
        
        tenancy = Tenancy(
            asset_id=data.asset_id,
            tenant_user_id=data.tenant_user_id,
            start_at=data.start_at,
            status=TenancyStatus.ACTIVE.value,
            handover_mode=data.handover_mode,
        )
        self.db.add(tenancy)
        await self.db.commit()
        await self.db.refresh(tenancy)
        
        logger.info(
            "Tenancy created",
            tenancy_id=str(tenancy.id),
            asset_id=str(data.asset_id),
            tenant_id=str(data.tenant_user_id),
        )
        return tenancy
    
    async def end_tenancy(self, tenancy_id: uuid.UUID) -> Tenancy:
        """End a tenancy."""
        from datetime import datetime, timezone
        
        stmt = select(Tenancy).where(Tenancy.id == tenancy_id)
        result = await self.db.execute(stmt)
        tenancy = result.scalar_one_or_none()
        
        if not tenancy:
            raise NotFoundError("Tenancy", tenancy_id)
        
        tenancy.status = TenancyStatus.ENDED.value
        tenancy.end_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(tenancy)
        
        logger.info("Tenancy ended", tenancy_id=str(tenancy_id))
        return tenancy
    
    # ============== Handover Operations ==============
    
    async def create_handover_token(
        self, asset_id: uuid.UUID, expires_in_hours: int = 48
    ) -> HandoverToken:
        """Create a handover token for tenant transition."""
        import secrets
        from datetime import datetime, timezone, timedelta
        
        asset = await self.get_asset_by_id(asset_id)
        if not asset:
            raise NotFoundError("Asset", asset_id)
        
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)
        
        handover = HandoverToken(
            asset_id=asset_id,
            token=token,
            expires_at=expires_at,
        )
        self.db.add(handover)
        await self.db.commit()
        await self.db.refresh(handover)
        
        logger.info(
            "Handover token created",
            asset_id=str(asset_id),
            expires_at=str(expires_at),
        )
        return handover
    
    async def claim_handover(
        self, token: str, user_id: uuid.UUID
    ) -> tuple[HandoverToken, Tenancy]:
        """Claim a handover token and create new tenancy."""
        from datetime import datetime, timezone
        
        stmt = select(HandoverToken).where(HandoverToken.token == token)
        result = await self.db.execute(stmt)
        handover = result.scalar_one_or_none()
        
        if not handover:
            raise NotFoundError("HandoverToken", token)
        
        if not handover.is_valid:
            raise ValidationError("Handover token is expired or already used")
        
        # Mark token as used
        now = datetime.now(timezone.utc)
        handover.used_at = now
        handover.used_by_user_id = user_id
        
        # End existing tenancy if any
        existing = await self.get_active_tenancy(handover.asset_id)
        if existing:
            existing.status = TenancyStatus.ENDED.value
            existing.end_at = now
        
        # Create new tenancy
        tenancy = Tenancy(
            asset_id=handover.asset_id,
            tenant_user_id=user_id,
            start_at=now,
            status=TenancyStatus.ACTIVE.value,
            handover_mode="qr",
        )
        self.db.add(tenancy)
        
        await self.db.commit()
        await self.db.refresh(handover)
        await self.db.refresh(tenancy)
        
        logger.info(
            "Handover claimed",
            asset_id=str(handover.asset_id),
            new_tenant_id=str(user_id),
        )
        return handover, tenancy
    
    async def wipe_tenant_data(self, asset_id: uuid.UUID) -> None:
        """Wipe tenant-specific data during handover."""
        # End active tenancy
        tenancy = await self.get_active_tenancy(asset_id)
        if tenancy:
            await self.end_tenancy(tenancy.id)
        
        # Revoke tenant memberships
        stmt = select(AssetMembership).where(
            AssetMembership.asset_id == asset_id,
            AssetMembership.relation == "tenant",
            AssetMembership.revoked_at.is_(None),
        )
        result = await self.db.execute(stmt)
        memberships = result.scalars().all()
        
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        for m in memberships:
            m.revoked_at = now
        
        await self.db.commit()
        logger.info("Tenant data wiped", asset_id=str(asset_id))
