"""
Auth Module - Database Models
User, Organization, Role, and OrganizationUser (Many-to-Many with roles).
A user can belong to multiple organizations with different roles.
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models import Base

if TYPE_CHECKING:
    from src.modules.real_estate.models import Asset
    from src.modules.billing.models import Wallet


class RoleType(str, Enum):
    """
    Predefined role types for RBAC.
    
    Hiyerarşi:
    1. super_admin - Tam sistem yetkisi (tüm organizasyonlar)
    2. admin - Organizasyon yönetimi (kendi org'unda tam yetki)
    3. operator - Cihaz kontrolü ve telemetri
    4. user - Salt okunur erişim
    5. agent - Kiracı bulma, sözleşme yönetimi
    """
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    OPERATOR = "operator"
    USER = "user"
    AGENT = "agent"


class User(Base):
    """
    User model - Auth0 entegrasyonu ile.
    Users can belong to multiple organizations through OrganizationUser.
    """
    __tablename__ = "user"
    
    # Auth0 entegrasyonu
    auth0_id: Mapped[str | None] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=True,
        comment="Auth0 user ID (sub claim)",
    )
    
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: Mapped[str | None] = mapped_column(
        String(255), 
        nullable=True,
        comment="Nullable for Auth0 users",
    )
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    # Telegram entegrasyonu
    telegram_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    organization_memberships: Mapped[list["OrganizationUser"]] = relationship(
        "OrganizationUser",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Organization(Base):
    """
    Organization (Tenant) model.
    Multi-tenant isolation is based on organization_id.
    """
    __tablename__ = "organization"
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Contact info
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Settings
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings: Mapped[dict | None] = mapped_column(JSONB, default=None, nullable=True)
    
    # Relationships
    members: Mapped[list["OrganizationUser"]] = relationship(
        "OrganizationUser",
        back_populates="organization",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    
    assets: Mapped[list["Asset"]] = relationship(
        "Asset",
        back_populates="organization",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    
    wallets: Mapped[list["Wallet"]] = relationship(
        "Wallet",
        back_populates="organization",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Role(Base):
    """
    Role model for RBAC.
    Defines permissions for organization members.
    """
    __tablename__ = "role"
    
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Permissions stored as JSON array
    permissions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="System roles cannot be deleted",
    )


class OrganizationUser(Base):
    """
    Many-to-Many relationship between User and Organization with Role.
    A user can have different roles in different organizations.
    """
    __tablename__ = "organization_user"
    
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_org_user"),
    )
    
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("role.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    # Additional membership info
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Default organization for user",
    )
    
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    
    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="organization_memberships",
    )
    
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="members",
    )
    
    role: Mapped["Role | None"] = relationship("Role", lazy="joined")
