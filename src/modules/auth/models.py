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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models import Base

if TYPE_CHECKING:
    from src.modules.billing.models import Wallet
    from src.modules.real_estate.models import Asset


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


class OrganizationType(str, Enum):
    """
    Organizasyon/Tesis tipi.
    Hava durumu ve enerji hesaplamaları için önemli.
    """
    VILLA = "villa"                     # Villa
    HOUSE = "house"                     # Müstakil ev
    APARTMENT = "apartment"             # Apartman dairesi
    STUDIO = "studio"                   # Stüdyo daire (1+0)
    FLAT_1_1 = "flat_1_1"              # 1+1 daire
    FLAT_2_1 = "flat_2_1"              # 2+1 daire
    FLAT_3_1 = "flat_3_1"              # 3+1 daire
    FLAT_4_1 = "flat_4_1"              # 4+1 ve üzeri
    OFFICE = "office"                   # Ofis
    FACTORY = "factory"                 # Fabrika
    WAREHOUSE = "warehouse"             # Depo
    FARM = "farm"                       # Tarla/Çiftlik
    GREENHOUSE = "greenhouse"           # Sera
    SHOP = "shop"                       # Dükkan/Mağaza
    HOTEL = "hotel"                     # Otel
    HOSPITAL = "hospital"               # Hastane
    SCHOOL = "school"                   # Okul
    OTHER = "other"                     # Diğer


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
    kvkk_accepted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="KVKK aydınlatma metni onayı",
    )
    kvkk_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="KVKK onay tarihi",
    )
    marketing_consent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Pazarlama iletişimi onayı",
    )
    marketing_consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Pazarlama onay tarihi",
    )
    
    # Onboarding durumu
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    onboarding_step: Mapped[int | None] = mapped_column(nullable=True, comment="Current onboarding step")
    
    # Firebase Push Token
    fcm_token: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # User status for lifecycle management
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="active, suspended, banned, pending",
    )
    
    # Login tracking (Güvenlik denetimi için)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="Son giriş IP adresi (IPv6 destekli)",
    )
    last_login_user_agent: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Son giriş tarayıcı bilgisi",
    )
    
    # MFA status
    mfa_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="İki faktörlü doğrulama aktif mi",
    )
    
    # User preferences (Dil, Tema, vb.)
    preferences: Mapped[dict | None] = mapped_column(
        JSONB,
        default=None,
        nullable=True,
        comment="language, theme, timezone, date_format",
    )
    
    # Relationships
    organization_memberships: Mapped[list["OrganizationUser"]] = relationship(
        "OrganizationUser",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    
    # User wallets (PERSONAL wallets - AWX Puan)
    wallets: Mapped[list["Wallet"]] = relationship(
        "Wallet",
        back_populates="user",
        foreign_keys="Wallet.user_id",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Organization(Base):
    """
    Organization (Tenant) model.
    Multi-tenant isolation is based on organization_id.
    
    Detaylı adres bilgisi hava durumu ve enerji hesaplamaları için gerekli.
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
    
    # Organization type and size
    organization_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="villa, house, apartment, flat_1_1, factory, etc.",
    )
    company_size: Mapped[int | None] = mapped_column(
        nullable=True,
        default=0,
        comment="Çalışan sayısı veya m2 büyüklüğü",
    )
    
    # Contact info
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    # Detailed address (for weather API)
    city: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Şehir (İstanbul, Ankara, vb.)",
    )
    district: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="İlçe (Kadıköy, Çankaya, vb.)",
    )
    neighborhood: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Mahalle",
    )
    street: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Sokak/Cadde ve kapı no",
    )
    postal_code: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Posta kodu",
    )
    country: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="Türkiye",
    )
    
    # Coordinates (for weather API)
    latitude: Mapped[float | None] = mapped_column(
        nullable=True,
        comment="Enlem koordinatı",
    )
    longitude: Mapped[float | None] = mapped_column(
        nullable=True,
        comment="Boylam koordinatı",
    )
    
    # Legacy address field (deprecated, use detailed fields)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Billing/Tax info (Fatura kesebilmek için)
    tax_number: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Vergi numarası",
    )
    tax_office: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Vergi dairesi",
    )
    billing_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Fatura e-posta adresi",
    )
    billing_address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Fatura adresi",
    )
    
    # Subscription tier/plan
    tier: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="free",
        comment="free, starter, pro, enterprise",
    )
    
    # Organization status (for lifecycle management)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="active, suspended, pending, deleted",
    )
    suspended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Askıya alınma tarihi",
    )
    suspended_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Askıya alma nedeni",
    )
    
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
    
    @property
    def full_address(self) -> str:
        """Tam adres string'i oluştur."""
        parts = [self.street, self.neighborhood, self.district, self.city, self.country]
        return ", ".join(p for p in parts if p)


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


class Invitation(Base):
    """
    Kullanıcı davetiye modeli.
    
    Akış:
    1. Tenant Admin, bir email'e davetiye gönderir
    2. Davetiye token'ı oluşturulur ve email gönderilir
    3. Kullanıcı linke tıklar ve Auth0 ile giriş yapar
    4. /auth/sync sırasında bekleyen davetiye kontrol edilir
    5. Kullanıcı organizasyona eklenir, davetiye tüketilir
    
    Güvenlik:
    - Token unique ve tahmin edilemez olmalı (secrets.token_urlsafe)
    - Süre sınırı olmalı (48 saat)
    - Tenant sadece kendi org'una davet edebilir
    - Tenant sadece user/device rolü atayabilir (admin değil)
    """
    __tablename__ = "invitation"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Davet edilen email
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Davet edilen kullanıcının email adresi",
    )
    
    # Güvenli token (URL'de kullanılacak)
    token: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
        comment="Davetiye doğrulama token'ı",
    )
    
    # Hangi organizasyona davet ediliyor?
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Hangi rol ile davet ediliyor?
    role_code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="user",
        comment="Atanacak rol: user, device (tenant sadece bunları atayabilir)",
    )
    
    # Kim davet etti?
    invited_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Daveti gönderen kullanıcı",
    )
    
    # Davetiye durumu
    is_used: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Davetiye kullanıldı mı?",
    )
    
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Davetiyenin kullanıldığı tarih",
    )
    
    # Süre sınırı
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Davetiye son geçerlilik tarihi",
    )
    
    # Opsiyonel mesaj
    message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Davetiye ile gönderilen kişisel mesaj",
    )
    
    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        foreign_keys=[organization_id],
    )
    
    invited_by: Mapped["User"] = relationship(
        "User",
        foreign_keys=[invited_by_id],
    )
