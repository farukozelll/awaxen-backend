"""
RealEstate Module - Database Models
Hierarchical Asset structure: Site -> Block -> Floor -> Unit (Self-referencing table)
Zone, Tenancy, AssetMembership, and HandoverToken models for property lifecycle management.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models import Base, TenantMixin

if TYPE_CHECKING:
    from src.modules.auth.models import Organization, User
    from src.modules.iot.models import Device, Gateway


class AssetType(str, Enum):
    """Asset type enumeration for Awaxen property types."""
    VILLA = "villa"
    APARTMENT = "apartment"
    FACTORY = "factory"
    GREENHOUSE = "greenhouse"
    OFFICE = "office"
    WAREHOUSE = "warehouse"
    SITE = "site"
    BLOCK = "block"
    FLOOR = "floor"
    UNIT = "unit"
    COMMON_AREA = "common"
    METER_POINT = "meter"


class ZoneType(str, Enum):
    """Zone type enumeration for rooms/areas within an asset."""
    ROOM = "room"
    AREA = "area"
    PANEL = "panel"
    MACHINE_ZONE = "machine_zone"
    OUTDOOR = "outdoor"


class AssetMembershipRelation(str, Enum):
    """Relation types for asset membership."""
    OWNER = "owner"
    TENANT = "tenant"
    AGENT = "agent"
    OPERATOR_VIEW = "operator_view"


class TenancyStatus(str, Enum):
    """Tenancy lifecycle status."""
    ACTIVE = "active"
    ENDED = "ended"
    PENDING = "pending"


class HandoverMode(str, Enum):
    """How the handover was initiated."""
    QR = "qr"
    ADMIN = "admin"
    OWNER_INITIATED = "owner_initiated"


class AssetStatus(str, Enum):
    """Asset operational status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNDER_CONSTRUCTION = "under_construction"
    MAINTENANCE = "maintenance"


class Asset(Base, TenantMixin):
    """
    Asset model with self-referencing hierarchy.
    Supports: Site -> Block -> Floor -> Unit structure.
    
    Example hierarchy:
    - Site: "Awaxen Tower Complex"
      - Block: "A Block"
        - Floor: "1st Floor"
          - Unit: "Apartment 101"
          - Unit: "Apartment 102"
        - Floor: "2nd Floor"
          - Unit: "Apartment 201"
      - Block: "B Block"
        ...
    """
    __tablename__ = "asset"
    
    __table_args__ = (
        Index("ix_asset_org_type", "organization_id", "asset_type"),
        Index("ix_asset_parent", "parent_id"),
        Index("ix_asset_hierarchy", "organization_id", "parent_id", "asset_type"),
        UniqueConstraint("organization_id", "code", name="uq_asset_org_code"),
    )
    
    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Unique code within organization (e.g., SITE-001, BLK-A, FLR-01, UNIT-101)",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Hierarchy
    asset_type: Mapped[AssetType] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )
    
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("asset.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    
    # Location
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    
    # Physical properties
    area_sqm: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Area in square meters",
    )
    floor_number: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Floor number (for floor/unit types)",
    )
    
    # Status
    status: Mapped[AssetStatus] = mapped_column(
        String(30),
        default=AssetStatus.ACTIVE,
        nullable=False,
    )
    
    # Metadata
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        comment="Additional asset-specific metadata",
    )
    
    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="assets",
    )
    
    parent: Mapped["Asset | None"] = relationship(
        "Asset",
        remote_side="Asset.id",
        back_populates="children",
        foreign_keys=[parent_id],
    )
    
    children: Mapped[list["Asset"]] = relationship(
        "Asset",
        back_populates="parent",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    
    leases: Mapped[list["Lease"]] = relationship(
        "Lease",
        back_populates="asset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    
    devices: Mapped[list["Device"]] = relationship(
        "Device",
        back_populates="asset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    
    gateways: Mapped[list["Gateway"]] = relationship(
        "Gateway",
        back_populates="asset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    
    zones: Mapped[list["Zone"]] = relationship(
        "Zone",
        back_populates="asset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    
    memberships: Mapped[list["AssetMembership"]] = relationship(
        "AssetMembership",
        back_populates="asset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    
    tenancies: Mapped[list["Tenancy"]] = relationship(
        "Tenancy",
        back_populates="asset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    
    handover_tokens: Mapped[list["HandoverToken"]] = relationship(
        "HandoverToken",
        back_populates="asset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    
    @property
    def full_path(self) -> str:
        """Get full hierarchical path (e.g., 'Site A / Block 1 / Floor 2 / Unit 201')."""
        parts = [self.name]
        current = self.parent
        while current:
            parts.insert(0, current.name)
            current = current.parent
        return " / ".join(parts)


class LeaseStatus(str, Enum):
    """Lease status enumeration."""
    DRAFT = "draft"
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"
    PENDING_RENEWAL = "pending_renewal"


class Lease(Base, TenantMixin):
    """
    Lease/Contract model.
    Represents tenant contracts for assets (units).
    """
    __tablename__ = "lease"
    
    __table_args__ = (
        Index("ix_lease_org_status", "organization_id", "status"),
        Index("ix_lease_dates", "start_date", "end_date"),
    )
    
    # Asset reference
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("asset.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Tenant info (could be linked to a Tenant model later)
    tenant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tenant_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tenant_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tenant_id_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="National ID or passport number",
    )
    
    # Contract details
    contract_number: Mapped[str | None] = mapped_column(
        String(100),
        unique=True,
        nullable=True,
    )
    
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Financial
    monthly_rent: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    deposit_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="TRY",
        nullable=False,
    )
    
    # Status
    status: Mapped[LeaseStatus] = mapped_column(
        String(30),
        default=LeaseStatus.DRAFT,
        nullable=False,
        index=True,
    )
    
    # Dates
    signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    terminated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Relationships
    asset: Mapped["Asset"] = relationship(
        "Asset",
        back_populates="leases",
    )


class Zone(Base):
    """
    Zone model - rooms/areas within an asset.
    
    Examples: Salon, Mutfak, Yatak Odası, Sera-1, Panel Odası
    Devices are assigned to zones for better organization.
    """
    __tablename__ = "zone"
    
    __table_args__ = (
        Index("idx_zone_asset", "asset_id"),
    )
    
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("asset.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    zone_type: Mapped[str] = mapped_column(
        String(30),
        default=ZoneType.ROOM.value,
        nullable=False,
    )
    
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Relationships
    asset: Mapped["Asset"] = relationship(
        "Asset",
        back_populates="zones",
    )


class AssetMembership(Base):
    """
    Asset-level access control.
    
    Defines who has access to which asset and with what permissions.
    This is separate from organization roles - provides asset-scoped permissions.
    """
    __tablename__ = "asset_membership"
    
    __table_args__ = (
        UniqueConstraint("asset_id", "user_id", "relation", name="uq_asset_membership"),
        Index("idx_asset_membership_asset", "asset_id"),
        Index("idx_asset_membership_user", "user_id"),
    )
    
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("asset.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    relation: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="owner/tenant/agent/operator_view",
    )
    
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        default=list,
        nullable=False,
        comment="read/control/billing_view/maintenance",
    )
    
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Relationships
    asset: Mapped["Asset"] = relationship(
        "Asset",
        back_populates="memberships",
    )
    
    @property
    def is_active(self) -> bool:
        """Check if membership is currently active."""
        return self.revoked_at is None


class Tenancy(Base):
    """
    Tenancy lifecycle tracking.
    
    Tracks who is currently living/using an asset.
    Used for digital handover and tenant wipe operations.
    """
    __tablename__ = "tenancy"
    
    __table_args__ = (
        Index("idx_tenancy_asset", "asset_id"),
        Index("idx_tenancy_tenant", "tenant_user_id"),
        Index("idx_tenancy_status", "status"),
    )
    
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("asset.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    tenant_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    
    end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    status: Mapped[str] = mapped_column(
        String(20),
        default=TenancyStatus.ACTIVE.value,
        nullable=False,
    )
    
    handover_mode: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="How the tenancy was initiated: qr/admin/owner_initiated",
    )
    
    # Relationships
    asset: Mapped["Asset"] = relationship(
        "Asset",
        back_populates="tenancies",
    )
    
    @property
    def is_active(self) -> bool:
        """Check if tenancy is currently active."""
        return self.status == TenancyStatus.ACTIVE.value and self.end_at is None


class HandoverToken(Base):
    """
    Digital handover tokens for tenant transitions.
    
    When a tenant moves out, owner generates a handover token.
    New tenant scans QR/enters token to claim the asset.
    """
    __tablename__ = "handover_token"
    
    __table_args__ = (
        Index("idx_handover_asset", "asset_id"),
        Index("idx_handover_token", "token"),
    )
    
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("asset.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    token: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    used_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Relationships
    asset: Mapped["Asset"] = relationship(
        "Asset",
        back_populates="handover_tokens",
    )
    
    @property
    def is_valid(self) -> bool:
        """Check if token is still valid (not used and not expired)."""
        from datetime import timezone
        now = datetime.now(timezone.utc)
        return self.used_at is None and self.expires_at > now
