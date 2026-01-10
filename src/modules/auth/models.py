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
    1. admin - Sistem yöneticisi (tüm organizasyonları yönetir, rol ve permission atar)
    2. tenant - Organizasyon yöneticisi (kendi org'unda tam yetki)
    3. user - Normal kullanıcı (salt okunur erişim)
    4. device - Cihaz/Telemetri erişimi (IoT endpoint'leri için)
    """
    ADMIN = "admin"      # Sistem yöneticisi - tüm yetkiler
    TENANT = "tenant"    # Organizasyon yöneticisi
    USER = "user"        # Normal kullanıcı
    DEVICE = "device"    # Telemetri erişimi


class Permission(str, Enum):
    """
    Sistem genelinde tanımlı yetkiler.
    Admin tüm yetkilere sahiptir.
    Tenant kendi organizasyonunda yetki atayabilir.
    """
    # Organizasyon yönetimi
    ORG_CREATE = "org:create"           # Yeni organizasyon oluştur
    ORG_READ = "org:read"               # Organizasyon bilgilerini görüntüle
    ORG_UPDATE = "org:update"           # Organizasyon bilgilerini güncelle
    ORG_DELETE = "org:delete"           # Organizasyon sil
    
    # Kullanıcı yönetimi
    USER_CREATE = "user:create"         # Yeni kullanıcı oluştur
    USER_READ = "user:read"             # Kullanıcı bilgilerini görüntüle
    USER_UPDATE = "user:update"         # Kullanıcı bilgilerini güncelle
    USER_DELETE = "user:delete"         # Kullanıcı sil
    
    # Rol ve yetki yönetimi (sadece admin)
    ROLE_ASSIGN = "role:assign"         # Rol ata
    PERMISSION_ASSIGN = "permission:assign"  # Yetki ata
    
    # Asset yönetimi
    ASSET_CREATE = "asset:create"       # Asset oluştur
    ASSET_READ = "asset:read"           # Asset görüntüle
    ASSET_UPDATE = "asset:update"       # Asset güncelle
    ASSET_DELETE = "asset:delete"       # Asset sil
    
    # Zone yönetimi
    ZONE_CREATE = "zone:create"         # Zone oluştur
    ZONE_READ = "zone:read"             # Zone görüntüle
    ZONE_UPDATE = "zone:update"         # Zone güncelle
    ZONE_DELETE = "zone:delete"         # Zone sil
    
    # Cihaz yönetimi
    DEVICE_CREATE = "device:create"     # Cihaz ekle
    DEVICE_READ = "device:read"         # Cihaz görüntüle
    DEVICE_UPDATE = "device:update"     # Cihaz güncelle
    DEVICE_DELETE = "device:delete"     # Cihaz sil
    DEVICE_CONTROL = "device:control"   # Cihaz kontrol et (aç/kapa)
    
    # Telemetri
    TELEMETRY_READ = "telemetry:read"   # Telemetri verilerini görüntüle
    TELEMETRY_WRITE = "telemetry:write" # Telemetri verisi gönder
    
    # Gateway yönetimi
    GATEWAY_CREATE = "gateway:create"   # Gateway ekle
    GATEWAY_READ = "gateway:read"       # Gateway görüntüle
    GATEWAY_UPDATE = "gateway:update"   # Gateway güncelle
    GATEWAY_DELETE = "gateway:delete"   # Gateway sil
    
    # Billing
    BILLING_READ = "billing:read"       # Fatura/ödeme görüntüle
    BILLING_MANAGE = "billing:manage"   # Fatura/ödeme yönet
    
    # Audit
    AUDIT_READ = "audit:read"           # Denetim loglarını görüntüle
    
    # Energy/Recommendation
    ENERGY_READ = "energy:read"         # Enerji verilerini görüntüle
    RECOMMENDATION_READ = "recommendation:read"   # Önerileri görüntüle
    RECOMMENDATION_APPROVE = "recommendation:approve"  # Öneriyi onayla
    
    # Reward/Ledger
    REWARD_READ = "reward:read"         # Ödülleri görüntüle
    LEDGER_READ = "ledger:read"         # Ledger görüntüle


class ModuleType(str, Enum):
    """
    Organizasyona atanabilir modüller.
    Her modül belirli permission'ları ve özellikleri içerir.
    Admin organizasyon oluştururken bu modülleri atar.
    """
    # Core modüller (her organizasyonda varsayılan)
    CORE = "core"                   # Temel özellikler (auth, org, user)
    
    # Asset/Property yönetimi
    ASSET_MANAGEMENT = "asset_management"   # Asset, Zone yönetimi
    
    # IoT modülleri
    IOT = "iot"                     # Gateway, Device yönetimi
    TELEMETRY = "telemetry"         # Telemetri verileri
    
    # Enerji yönetimi
    ENERGY = "energy"               # EPİAŞ, Recommendation, Core Loop
    
    # Ödül sistemi
    REWARDS = "rewards"             # AWX puan sistemi, Ledger
    
    # Faturalama
    BILLING = "billing"             # Cüzdan, işlemler
    
    # Uyumluluk
    COMPLIANCE = "compliance"       # KVKK/GDPR, Audit logs
    
    # Bildirimler
    NOTIFICATIONS = "notifications" # Push, Telegram, Email
    
    # Dashboard
    DASHBOARD = "dashboard"         # Analitik, raporlar


# Modül bazlı permission'lar - her modül hangi permission'ları gerektirir
MODULE_PERMISSIONS: dict[str, list[str]] = {
    ModuleType.CORE.value: [
        Permission.ORG_READ.value,
        Permission.ORG_UPDATE.value,
        Permission.USER_READ.value,
        Permission.USER_CREATE.value,
        Permission.USER_UPDATE.value,
        Permission.ROLE_ASSIGN.value,
    ],
    ModuleType.ASSET_MANAGEMENT.value: [
        Permission.ASSET_CREATE.value,
        Permission.ASSET_READ.value,
        Permission.ASSET_UPDATE.value,
        Permission.ASSET_DELETE.value,
        Permission.ZONE_CREATE.value,
        Permission.ZONE_READ.value,
        Permission.ZONE_UPDATE.value,
        Permission.ZONE_DELETE.value,
    ],
    ModuleType.IOT.value: [
        Permission.GATEWAY_CREATE.value,
        Permission.GATEWAY_READ.value,
        Permission.GATEWAY_UPDATE.value,
        Permission.GATEWAY_DELETE.value,
        Permission.DEVICE_CREATE.value,
        Permission.DEVICE_READ.value,
        Permission.DEVICE_UPDATE.value,
        Permission.DEVICE_DELETE.value,
        Permission.DEVICE_CONTROL.value,
    ],
    ModuleType.TELEMETRY.value: [
        Permission.TELEMETRY_READ.value,
        Permission.TELEMETRY_WRITE.value,
    ],
    ModuleType.ENERGY.value: [
        Permission.ENERGY_READ.value,
        Permission.RECOMMENDATION_READ.value,
        Permission.RECOMMENDATION_APPROVE.value,
    ],
    ModuleType.REWARDS.value: [
        Permission.REWARD_READ.value,
        Permission.LEDGER_READ.value,
    ],
    ModuleType.BILLING.value: [
        Permission.BILLING_READ.value,
        Permission.BILLING_MANAGE.value,
    ],
    ModuleType.COMPLIANCE.value: [
        Permission.AUDIT_READ.value,
    ],
    ModuleType.NOTIFICATIONS.value: [],  # Özel permission yok, modül aktifliği yeterli
    ModuleType.DASHBOARD.value: [],  # Tüm read permission'ları kullanır
}


# Rol bazlı varsayılan yetkiler
ROLE_PERMISSIONS: dict[str, list[str]] = {
    RoleType.ADMIN.value: ["*"],  # Tüm yetkiler
    RoleType.TENANT.value: [
        # Organizasyon yönetimi (kendi org'u)
        Permission.ORG_READ.value,
        Permission.ORG_UPDATE.value,
        # Kullanıcı yönetimi
        Permission.USER_CREATE.value,
        Permission.USER_READ.value,
        Permission.USER_UPDATE.value,
        Permission.USER_DELETE.value,
        # Rol atama (kendi org'unda)
        Permission.ROLE_ASSIGN.value,
        Permission.PERMISSION_ASSIGN.value,
        # Asset yönetimi
        Permission.ASSET_CREATE.value,
        Permission.ASSET_READ.value,
        Permission.ASSET_UPDATE.value,
        Permission.ASSET_DELETE.value,
        # Zone yönetimi
        Permission.ZONE_CREATE.value,
        Permission.ZONE_READ.value,
        Permission.ZONE_UPDATE.value,
        Permission.ZONE_DELETE.value,
        # Cihaz yönetimi
        Permission.DEVICE_CREATE.value,
        Permission.DEVICE_READ.value,
        Permission.DEVICE_UPDATE.value,
        Permission.DEVICE_DELETE.value,
        Permission.DEVICE_CONTROL.value,
        # Telemetri
        Permission.TELEMETRY_READ.value,
        # Gateway
        Permission.GATEWAY_CREATE.value,
        Permission.GATEWAY_READ.value,
        Permission.GATEWAY_UPDATE.value,
        Permission.GATEWAY_DELETE.value,
        # Billing
        Permission.BILLING_READ.value,
        Permission.BILLING_MANAGE.value,
        # Audit
        Permission.AUDIT_READ.value,
    ],
    RoleType.USER.value: [
        # Salt okunur erişim
        Permission.ORG_READ.value,
        Permission.USER_READ.value,
        Permission.ASSET_READ.value,
        Permission.ZONE_READ.value,
        Permission.DEVICE_READ.value,
        Permission.TELEMETRY_READ.value,
        Permission.GATEWAY_READ.value,
        Permission.BILLING_READ.value,
    ],
    RoleType.DEVICE.value: [
        # Sadece telemetri erişimi
        Permission.TELEMETRY_READ.value,
        Permission.TELEMETRY_WRITE.value,
        Permission.DEVICE_READ.value,
        Permission.GATEWAY_READ.value,
    ],
}


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
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    # Telegram entegrasyonu
    telegram_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    # Adres bilgileri
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)  # İl
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)  # İlçe
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    
    # Bildirim ayarları
    notification_settings: Mapped[dict | None] = mapped_column(
        JSONB, 
        default=None, 
        nullable=True,
        comment="push_enabled, email_enabled, telegram_enabled, sms_enabled",
    )
    
    # KVKK/GDPR onayları
    consent_settings: Mapped[dict | None] = mapped_column(
        JSONB,
        default=None,
        nullable=True,
        comment="location, device_control, notifications, data_processing, marketing",
    )
    
    # Onboarding durumu
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    onboarding_step: Mapped[int | None] = mapped_column(nullable=True, comment="Current onboarding step")
    
    # Firebase Push Token
    fcm_token: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
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
    
    modules: Mapped[list["OrganizationModule"]] = relationship(
        "OrganizationModule",
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


class OrganizationModule(Base):
    """
    Organizasyona atanmış modüller.
    Admin organizasyon oluştururken modülleri atar.
    Tenant bu modüllerin yetkilerini kullanabilir.
    """
    __tablename__ = "organization_module"
    
    __table_args__ = (
        UniqueConstraint("organization_id", "module_code", name="uq_org_module"),
    )
    
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    module_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="ModuleType enum value",
    )
    
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    
    # Modül ayarları (opsiyonel)
    settings: Mapped[dict | None] = mapped_column(JSONB, default=None, nullable=True)
    
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    
    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="modules",
    )
