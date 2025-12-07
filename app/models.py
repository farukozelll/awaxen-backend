"""
Awaxen Models - v6.0 SaaS Hybrid Schema.

Temizlenmiş ve sadeleştirilmiş model yapısı.
Eski Node, Site kavramları kaldırıldı.
"""
from datetime import datetime
from enum import Enum
import uuid

from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.extensions import db
from app.utils.encryption import encrypt_token, decrypt_token


# ==========================================
# 0. ENUM SINIFLARI
# ==========================================


class OrganizationType(str, Enum):
    """Organizasyon tipi - SaaS tenant türü."""
    HOME = "home"                # Ev kullanıcısı (B2C)
    AGRICULTURE = "agriculture"  # Tarım işletmesi
    INDUSTRIAL = "industrial"    # Endüstriyel tesis
    COMMERCIAL = "commercial"    # Ticari bina


class DeviceStatus(str, Enum):
    """Cihaz durumu."""
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"


class IntegrationProvider(str, Enum):
    """Bulut entegrasyon sağlayıcıları."""
    SHELLY = "shelly"
    TESLA = "tesla"
    TAPO = "tapo"
    TUYA = "tuya"
    HUAWEI_FUSIONSOLAR = "huawei_fusionsolar"
    SUNGROW = "sungrow"


class SubscriptionStatus(str, Enum):
    """Abonelik durumu."""
    ACTIVE = "active"
    TRIAL = "trial"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class NotificationStatus(str, Enum):
    """Bildirim durumu."""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    READ = "read"


class AssetType(str, Enum):
    """Varlık tipi."""
    HVAC = "hvac"              # Klima/Isıtma
    EV_CHARGER = "ev_charger"  # Elektrikli araç şarjı
    WATER_HEATER = "water_heater"  # Su ısıtıcı
    HEATER = "heater"          # Isıtıcı
    APPLIANCE = "appliance"    # Ev aleti
    LIGHTING = "lighting"      # Aydınlatma
    OTHER = "other"


# ==========================================
# 0.5 ROL VE YETKİ YÖNETİMİ (RBAC)
# ==========================================


# Rol-Yetki ara tablosu (Many-to-Many)
role_permissions = db.Table(
    'role_permissions',
    db.Column('role_id', UUID(as_uuid=True), db.ForeignKey('roles.id'), primary_key=True),
    db.Column('permission_id', UUID(as_uuid=True), db.ForeignKey('permissions.id'), primary_key=True),
    db.Column('created_at', db.DateTime, default=datetime.utcnow)
)


class Permission(db.Model):
    """
    Yetki Tanımı - Granüler izinler.
    
    Örnek: can_edit_device, can_delete_automation, can_view_wallet
    """
    __tablename__ = 'permissions'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Yetki kodu (unique, snake_case)
    code = db.Column(db.String(100), unique=True, nullable=False)  # can_edit_device
    
    # Görünen isim
    name = db.Column(db.String(100), nullable=False)  # "Cihaz Düzenleme"
    
    # Açıklama
    description = db.Column(db.String(255))
    
    # Kategori (gruplama için)
    category = db.Column(db.String(50))  # devices, automations, wallet, settings
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": str(self.id),
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "category": self.category,
        }


class Role(db.Model):
    """
    Rol Tanımı - Yetki grupları.
    
    Örnek: super_admin, admin, operator, viewer, farmer
    """
    __tablename__ = 'roles'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Rol kodu (unique, snake_case)
    code = db.Column(db.String(50), unique=True, nullable=False)  # super_admin
    
    # Görünen isim
    name = db.Column(db.String(100), nullable=False)  # "Süper Admin"
    
    # Açıklama
    description = db.Column(db.String(255))
    
    # Sistem rolü mü? (Silinemez)
    is_system = db.Column(db.Boolean, default=False)
    
    # Aktif mi?
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişkiler
    permissions = db.relationship(
        'Permission',
        secondary=role_permissions,
        backref=db.backref('roles', lazy='dynamic'),
        lazy='joined'
    )

    def to_dict(self, include_permissions=False):
        data = {
            "id": str(self.id),
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "is_system": self.is_system,
            "is_active": self.is_active,
        }
        if include_permissions:
            data["permissions"] = [p.to_dict() for p in self.permissions]
        return data
    
    def has_permission(self, permission_code: str) -> bool:
        """Bu rolde belirtilen yetki var mı?"""
        return any(p.code == permission_code for p in self.permissions)
    
    @classmethod
    def get_by_code(cls, code: str):
        """Rol koduna göre bul."""
        return cls.query.filter_by(code=code, is_active=True).first()
    
    @classmethod
    def seed_default_roles(cls):
        """Varsayılan rolleri ve yetkileri oluştur."""
        from app.extensions import db
        
        # Önce yetkileri oluştur
        default_permissions = [
            # Cihaz yetkileri
            ("can_view_devices", "Cihazları Görüntüle", "devices", "Cihaz listesini görüntüleme"),
            ("can_edit_devices", "Cihaz Düzenle", "devices", "Cihaz ekleme/düzenleme"),
            ("can_delete_devices", "Cihaz Sil", "devices", "Cihaz silme"),
            ("can_control_devices", "Cihaz Kontrol", "devices", "Cihazları aç/kapat"),
            
            # Otomasyon yetkileri
            ("can_view_automations", "Otomasyonları Görüntüle", "automations", "Otomasyon listesi"),
            ("can_edit_automations", "Otomasyon Düzenle", "automations", "Otomasyon ekleme/düzenleme"),
            ("can_delete_automations", "Otomasyon Sil", "automations", "Otomasyon silme"),
            
            # Cüzdan yetkileri
            ("can_view_wallet", "Cüzdan Görüntüle", "wallet", "Bakiye ve işlem geçmişi"),
            ("can_transfer_wallet", "Transfer Yap", "wallet", "Coin transferi"),
            
            # Bildirim yetkileri
            ("can_view_notifications", "Bildirimleri Görüntüle", "notifications", "Bildirim listesi"),
            ("can_manage_notifications", "Bildirim Yönet", "notifications", "Bildirim ayarları"),
            
            # Entegrasyon yetkileri
            ("can_view_integrations", "Entegrasyonları Görüntüle", "integrations", "Entegrasyon listesi"),
            ("can_manage_integrations", "Entegrasyon Yönet", "integrations", "Entegrasyon ekleme/silme"),
            
            # Market yetkileri
            ("can_view_market", "Piyasa Görüntüle", "market", "Fiyat verileri"),
            ("can_import_market", "Fiyat İçe Aktar", "market", "EPİAŞ fiyat yükleme"),
            
            # Ayar yetkileri
            ("can_view_settings", "Ayarları Görüntüle", "settings", "Sistem ayarları"),
            ("can_edit_settings", "Ayar Düzenle", "settings", "Ayar değiştirme"),
            
            # Kullanıcı yetkileri
            ("can_view_users", "Kullanıcıları Görüntüle", "users", "Kullanıcı listesi"),
            ("can_manage_users", "Kullanıcı Yönet", "users", "Kullanıcı ekleme/düzenleme"),
            
            # Rol yetkileri
            ("can_view_roles", "Rolleri Görüntüle", "roles", "Rol listesi"),
            ("can_manage_roles", "Rol Yönet", "roles", "Rol ekleme/düzenleme"),
            
            # Dashboard
            ("can_view_dashboard", "Dashboard Görüntüle", "dashboard", "Ana panel"),
            ("can_view_analytics", "Analitik Görüntüle", "analytics", "Raporlar ve grafikler"),
            
            # Tarife yetkileri
            ("can_view_tariffs", "Tarifeleri Görüntüle", "tariffs", "Elektrik tarifelerini görüntüleme"),
            ("can_manage_tariffs", "Tarife Yönet", "tariffs", "Tarife ekleme/düzenleme"),
            
            # Organizasyon yetkileri
            ("can_view_organizations", "Organizasyonları Görüntüle", "organizations", "Organizasyon listesi"),
            ("can_manage_organizations", "Organizasyon Yönet", "organizations", "Organizasyon ekleme/düzenleme"),
        ]
        
        permissions_map = {}
        for code, name, category, desc in default_permissions:
            perm = Permission.query.filter_by(code=code).first()
            if not perm:
                perm = Permission(code=code, name=name, category=category, description=desc)
                db.session.add(perm)
            permissions_map[code] = perm
        
        db.session.flush()
        
        # Rolleri oluştur
        default_roles = [
            {
                "code": "super_admin",
                "name": "Süper Admin",
                "description": "Tüm yetkilere sahip sistem yöneticisi",
                "is_system": True,
                "permissions": list(permissions_map.keys()),  # Tüm yetkiler
            },
            {
                "code": "admin",
                "name": "Admin",
                "description": "Organizasyon yöneticisi",
                "is_system": True,
                "permissions": [
                    "can_view_devices", "can_edit_devices", "can_delete_devices", "can_control_devices",
                    "can_view_automations", "can_edit_automations", "can_delete_automations",
                    "can_view_wallet", "can_transfer_wallet",
                    "can_view_notifications", "can_manage_notifications",
                    "can_view_integrations", "can_manage_integrations",
                    "can_view_market",
                    "can_view_settings", "can_edit_settings",
                    "can_view_users", "can_manage_users",
                    "can_view_dashboard", "can_view_analytics",
                    "can_view_tariffs", "can_manage_tariffs",
                    "can_view_organizations",
                ],
            },
            {
                "code": "operator",
                "name": "Operatör",
                "description": "Cihaz ve otomasyon yönetimi",
                "is_system": True,
                "permissions": [
                    "can_view_devices", "can_edit_devices", "can_control_devices",
                    "can_view_automations", "can_edit_automations",
                    "can_view_wallet",
                    "can_view_notifications",
                    "can_view_integrations",
                    "can_view_market",
                    "can_view_dashboard",
                ],
            },
            {
                "code": "viewer",
                "name": "İzleyici",
                "description": "Sadece görüntüleme yetkisi",
                "is_system": True,
                "permissions": [
                    "can_view_devices",
                    "can_view_automations",
                    "can_view_wallet",
                    "can_view_notifications",
                    "can_view_market",
                    "can_view_dashboard",
                ],
            },
            {
                "code": "farmer",
                "name": "Çiftçi",
                "description": "Tarım kullanıcısı - cihaz kontrolü ve izleme",
                "is_system": False,
                "permissions": [
                    "can_view_devices", "can_control_devices",
                    "can_view_automations", "can_edit_automations",
                    "can_view_wallet",
                    "can_view_notifications",
                    "can_view_market",
                    "can_view_dashboard", "can_view_analytics",
                ],
            },
        ]
        
        for role_data in default_roles:
            role = cls.query.filter_by(code=role_data["code"]).first()
            if not role:
                role = cls(
                    code=role_data["code"],
                    name=role_data["name"],
                    description=role_data["description"],
                    is_system=role_data["is_system"],
                )
                db.session.add(role)
                db.session.flush()
            
            # Yetkileri ekle
            for perm_code in role_data["permissions"]:
                if perm_code in permissions_map:
                    perm = permissions_map[perm_code]
                    if perm not in role.permissions:
                        role.permissions.append(perm)
        
        db.session.commit()
        return True


# ==========================================
# 1. ORGANİZASYON VE KULLANICI KATMANI
# ==========================================


class Organization(db.Model):
    """
    SaaS Tenant - Ev, Tarım İşletmesi veya Fabrika.
    
    Eski 'Site' tablosunun yeni hali.
    Tüm veriler organization_id ile izole edilir (Multi-tenancy).
    """
    __tablename__ = "organizations"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(100), unique=True)
    
    type = db.Column(db.String(50), default=OrganizationType.HOME.value)
    
    timezone = db.Column(db.String(50), default="Europe/Istanbul")
    location = db.Column(JSONB, default=dict)
    
    subscription_status = db.Column(db.String(20), default=SubscriptionStatus.ACTIVE.value)
    subscription_plan = db.Column(db.String(50), default="free")
    
    settings = db.Column(JSONB, default=dict)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişkiler
    users = db.relationship("User", backref="organization", lazy=True)
    gateways = db.relationship("Gateway", backref="organization", lazy=True)
    integrations = db.relationship("Integration", backref="organization", lazy=True)
    devices = db.relationship("SmartDevice", backref="organization", lazy=True)
    assets = db.relationship("SmartAsset", backref="organization", lazy=True)
    automations = db.relationship("Automation", backref="organization", lazy=True)
    #tariffs = db.relationship("ElectricityTariff", backref="organization", lazy=True)
    audit_logs = db.relationship("AuditLog", backref="organization", lazy=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "slug": self.slug,
            "type": self.type,
            "timezone": self.timezone,
            "location": self.location or {},
            "subscription_status": self.subscription_status,
            "subscription_plan": self.subscription_plan,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class User(db.Model):
    """
    Kullanıcı - Auth0 ile entegre.
    
    Her kullanıcı bir Organization'a bağlıdır.
    Rol, roles tablosundan gelir (RBAC).
    """
    __tablename__ = "users"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id"))
    
    auth0_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), nullable=False)
    full_name = db.Column(db.String(100))
    phone_number = db.Column(db.String(20))
    
    # Telegram entegrasyonu (Invisible App)
    telegram_chat_id = db.Column(db.String(50), unique=True)
    telegram_username = db.Column(db.String(100))
    
    # RBAC - Rol ilişkisi
    role_id = db.Column(UUID(as_uuid=True), db.ForeignKey("roles.id"))
    role = db.relationship("Role", backref="users", lazy="joined")
    
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişkiler
    notifications = db.relationship("Notification", backref="user", lazy=True)
    settings = db.relationship("UserSettings", backref="user", uselist=False, lazy=True)

    def to_dict(self, include_permissions=False):
        data = {
            "id": str(self.id),
            "organization_id": str(self.organization_id) if self.organization_id else None,
            "email": self.email,
            "full_name": self.full_name,
            "phone_number": self.phone_number,
            "telegram_username": self.telegram_username,
            "role": self.role.to_dict(include_permissions) if self.role else None,
            "role_code": self.role.code if self.role else None,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_permissions and self.role:
            data["permissions"] = [p.code for p in self.role.permissions]
        return data
    
    def has_permission(self, permission_code: str) -> bool:
        """Kullanıcının belirtilen yetkisi var mı?"""
        if not self.role:
            return False
        return self.role.has_permission(permission_code)
    
    def has_any_permission(self, *permission_codes) -> bool:
        """Kullanıcının belirtilen yetkilerden herhangi biri var mı?"""
        if not self.role:
            return False
        return any(self.role.has_permission(code) for code in permission_codes)
    
    def has_all_permissions(self, *permission_codes) -> bool:
        """Kullanıcının belirtilen tüm yetkileri var mı?"""
        if not self.role:
            return False
        return all(self.role.has_permission(code) for code in permission_codes)


class UserSettings(db.Model):
    """
    Kullanıcı Ayarları - Bildirim tercihleri, UI ayarları vb.
    
    Her kullanıcının bir ayar kaydı olur (1:1 ilişki).
    """
    __tablename__ = "user_settings"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), unique=True, nullable=False)
    
    # Bildirim Kanalları
    telegram_enabled = db.Column(db.Boolean, default=False)
    email_enabled = db.Column(db.Boolean, default=True)
    push_enabled = db.Column(db.Boolean, default=False)
    
    # Bildirim Türleri
    price_alerts = db.Column(db.Boolean, default=True)
    device_alerts = db.Column(db.Boolean, default=True)
    automation_alerts = db.Column(db.Boolean, default=True)
    security_alerts = db.Column(db.Boolean, default=True)
    weekly_report = db.Column(db.Boolean, default=True)
    
    # UI Tercihleri
    language = db.Column(db.String(10), default="tr")
    theme = db.Column(db.String(20), default="system")  # light, dark, system
    dashboard_layout = db.Column(JSONB, default=dict)
    
    # Fiyat Uyarı Eşikleri
    price_alert_threshold_low = db.Column(db.Numeric(10, 2))  # TL/kWh altında uyar
    price_alert_threshold_high = db.Column(db.Numeric(10, 2))  # TL/kWh üstünde uyar
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "telegram_enabled": self.telegram_enabled,
            "email_enabled": self.email_enabled,
            "push_enabled": self.push_enabled,
            "price_alerts": self.price_alerts,
            "device_alerts": self.device_alerts,
            "automation_alerts": self.automation_alerts,
            "security_alerts": self.security_alerts,
            "weekly_report": self.weekly_report,
            "language": self.language,
            "theme": self.theme,
            "price_alert_threshold_low": float(self.price_alert_threshold_low) if self.price_alert_threshold_low else None,
            "price_alert_threshold_high": float(self.price_alert_threshold_high) if self.price_alert_threshold_high else None,
        }
    
    @classmethod
    def get_or_create(cls, user_id):
        """Kullanıcı ayarlarını getir veya varsayılan oluştur."""
        settings = cls.query.filter_by(user_id=user_id).first()
        if not settings:
            settings = cls(user_id=user_id)
            db.session.add(settings)
            db.session.commit()
        return settings


# ==========================================
# 2. BAĞLANTI KATMANI (Gateway & Cloud)
# ==========================================


class Gateway(db.Model):
    """
    Fiziksel Bağlantı Merkezi - Teltonika RUT956, Raspberry Pi.
    
    Sahadaki internet kapısı. Yerel cihazlar buraya bağlanır.
    """
    __tablename__ = "gateways"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id"), nullable=False)
    
    serial_number = db.Column(db.String(100), unique=True)
    model = db.Column(db.String(50))
    gateway_type = db.Column(db.String(50))  # teltonika, raspberry_pi, shelly_pro, custom
    
    ip_address = db.Column(db.String(45))
    mac_address = db.Column(db.String(17))
    
    status = db.Column(db.String(20), default="offline")
    last_seen = db.Column(db.DateTime)
    
    settings = db.Column(JSONB, default=dict)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişkiler
    devices = db.relationship("SmartDevice", backref="gateway", lazy=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "serial_number": self.serial_number,
            "model": self.model,
            "gateway_type": self.gateway_type,
            "ip_address": self.ip_address,
            "status": self.status,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "settings": self.settings or {},
            "is_active": self.is_active,
        }


class Integration(db.Model):
    """
    Bulut Entegrasyonu - Shelly Cloud, Tesla, Tapo, Tuya.
    
    OAuth token'ları şifreli saklanır.
    """
    __tablename__ = "integrations"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id"), nullable=False)
    
    provider = db.Column(db.String(50), nullable=False)
    
    # Şifreli Tokenlar
    _access_token = db.Column("access_token", db.Text)
    _refresh_token = db.Column("refresh_token", db.Text)
    
    expires_at = db.Column(db.DateTime)
    provider_data = db.Column(JSONB, default=dict)
    
    status = db.Column(db.String(20), default="active")
    last_sync_at = db.Column(db.DateTime)
    
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişkiler
    devices = db.relationship("SmartDevice", backref="integration", lazy=True)

    # Token encryption properties
    @property
    def access_token(self):
        if self._access_token:
            try:
                return decrypt_token(self._access_token)
            except Exception:
                return None
        return None

    @access_token.setter
    def access_token(self, value):
        if value:
            self._access_token = encrypt_token(value)
        else:
            self._access_token = None

    @property
    def refresh_token(self):
        if self._refresh_token:
            try:
                return decrypt_token(self._refresh_token)
            except Exception:
                return None
        return None

    @refresh_token.setter
    def refresh_token(self, value):
        if value:
            self._refresh_token = encrypt_token(value)
        else:
            self._refresh_token = None

    def to_dict(self, include_tokens=False):
        data = {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "provider": self.provider,
            "status": self.status,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "provider_data": self.provider_data or {},
            "is_active": self.is_active,
        }
        if include_tokens:
            data["access_token"] = self.access_token
            data["refresh_token"] = self.refresh_token
            data["has_access_token"] = bool(self._access_token)
            data["has_refresh_token"] = bool(self._refresh_token)
        return data


# ==========================================
# 3. CİHAZ VE VARLIK KATMANI
# ==========================================


class SmartDevice(db.Model):
    """
    Akıllı Cihaz - Shelly Plug, Tapo P110, Sensör.
    
    Fiziksel donanım. Gateway veya Integration üzerinden bağlanır.
    Eski 'Node' tablosunun yeni hali.
    """
    __tablename__ = "smart_devices"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id"), nullable=False)
    
    # Bağlantı kaynağı (biri dolu olmalı)
    gateway_id = db.Column(UUID(as_uuid=True), db.ForeignKey("gateways.id"))
    integration_id = db.Column(UUID(as_uuid=True), db.ForeignKey("integrations.id"))
    
    external_id = db.Column(db.String(100))  # MAC veya Cloud ID
    name = db.Column(db.String(100))
    
    brand = db.Column(db.String(50))  # shelly, tapo, tuya
    model = db.Column(db.String(50))
    device_type = db.Column(db.String(50))  # relay, energy_meter, sensor, switch, plug, dimmer
    
    is_sensor = db.Column(db.Boolean, default=False)
    is_actuator = db.Column(db.Boolean, default=False)
    
    is_online = db.Column(db.Boolean, default=False)
    last_seen = db.Column(db.DateTime)
    
    settings = db.Column(JSONB, default=dict)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişkiler
    asset = db.relationship("SmartAsset", backref="device", uselist=False)
    telemetry_data = db.relationship("DeviceTelemetry", backref="device", lazy=True)
    vpp_rules = db.relationship("VppRule", backref="device", lazy=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "gateway_id": str(self.gateway_id) if self.gateway_id else None,
            "integration_id": str(self.integration_id) if self.integration_id else None,
            "external_id": self.external_id,
            "name": self.name,
            "brand": self.brand,
            "model": self.model,
            "device_type": self.device_type,
            "is_sensor": self.is_sensor,
            "is_actuator": self.is_actuator,
            "is_online": self.is_online,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "settings": self.settings or {},
            "is_active": self.is_active,
        }


class SmartAsset(db.Model):
    """
    Sanal Varlık - Klima, Isıtıcı, EV Charger.
    
    Kullanıcının gördüğü şey. Cihaz sadece araçtır.
    """
    __tablename__ = "smart_assets"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id"), nullable=False)
    device_id = db.Column(UUID(as_uuid=True), db.ForeignKey("smart_devices.id"), unique=True)
    
    name = db.Column(db.String(100))
    type = db.Column(db.String(50))  # hvac, ev_charger, heater
    
    # Sanal ölçüm için varsayılan güç (Watt)
    nominal_power_watt = db.Column(db.Integer, default=0)
    priority = db.Column(db.Integer, default=1)
    
    settings = db.Column(JSONB, default=dict)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişkiler
    automations = db.relationship("Automation", backref="asset", lazy=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "device_id": str(self.device_id) if self.device_id else None,
            "name": self.name,
            "type": self.type,
            "nominal_power_watt": self.nominal_power_watt,
            "priority": self.priority,
            "settings": self.settings or {},
            "is_active": self.is_active,
            "device": self.device.to_dict() if self.device else None,
        }


# ==========================================
# 4. OTOMASYON VE EKONOMİ KATMANI
# ==========================================


class MarketPrice(db.Model):
    """
    EPİAŞ Piyasa Fiyatları - Global tablo.
    
    Worker saatlik günceller, tüm müşteriler kullanır.
    """
    __tablename__ = "market_prices"

    time = db.Column(db.DateTime(timezone=True), primary_key=True)
    price = db.Column(db.Float, nullable=False)  # TL/kWh
    currency = db.Column(db.String(10), default="TRY")
    region = db.Column(db.String(10), default="TR")
    
    ptf = db.Column(db.Float)  # Piyasa Takas Fiyatı (TL/MWh)
    smf = db.Column(db.Float)  # Sistem Marjinal Fiyatı

    def to_dict(self):
        return {
            "time": self.time.isoformat() if self.time else None,
            "price": self.price,
            "currency": self.currency,
            "region": self.region,
            "ptf": self.ptf,
            "smf": self.smf,
        }


class Automation(db.Model):
    """
    Otomasyon Kuralı - Fiyat bazlı, zaman bazlı, sensör bazlı.
    """
    __tablename__ = "automations"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id"), nullable=False)
    asset_id = db.Column(UUID(as_uuid=True), db.ForeignKey("smart_assets.id"))
    created_by = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"))  # Row-level security için
    
    name = db.Column(db.String(100))
    description = db.Column(db.Text)
    
    is_active = db.Column(db.Boolean, default=True)
    rules = db.Column(JSONB, nullable=False)
    
    last_triggered_at = db.Column(db.DateTime)
    trigger_count = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişkiler
    logs = db.relationship("AutomationLog", backref="automation", lazy=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "asset_id": str(self.asset_id) if self.asset_id else None,
            "created_by": str(self.created_by) if self.created_by else None,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "rules": self.rules,
            "last_triggered_at": self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            "trigger_count": self.trigger_count,
        }


class AutomationLog(db.Model):
    """Otomasyon Çalışma Geçmişi."""
    __tablename__ = "automation_logs"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id"), nullable=False)
    automation_id = db.Column(UUID(as_uuid=True), db.ForeignKey("automations.id"), nullable=False)
    
    triggered_at = db.Column(db.DateTime, default=datetime.utcnow)
    action_taken = db.Column(db.String(100))
    reason = db.Column(db.Text)
    
    status = db.Column(db.String(20), default="success")
    error_message = db.Column(db.Text)

    def to_dict(self):
        return {
            "id": str(self.id),
            "automation_id": str(self.automation_id),
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "action_taken": self.action_taken,
            "reason": self.reason,
            "status": self.status,
            "error_message": self.error_message,
        }


# ==========================================
# 4.5 OYUNLAŞTIRMA (GAMIFICATION) KATMANI
# ==========================================


class Wallet(db.Model):
    """
    Kullanıcı Cüzdanı - Awaxen Coin (AWX) bakiyesi.
    
    Ledger mantığı: Bakiye her zaman transactions'dan hesaplanabilir.
    """
    __tablename__ = "wallets"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), unique=True, nullable=False)
    
    balance = db.Column(db.Numeric(12, 2), default=0.0)  # Güncel bakiye
    currency = db.Column(db.String(10), default="AWX")   # Awaxen Coin
    
    lifetime_earned = db.Column(db.Numeric(12, 2), default=0.0)   # Toplam kazanılan
    lifetime_spent = db.Column(db.Numeric(12, 2), default=0.0)    # Toplam harcanan
    
    level = db.Column(db.Integer, default=1)             # Kullanıcı seviyesi
    xp = db.Column(db.Integer, default=0)                # Deneyim puanı
    
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişkiler
    user = db.relationship("User", backref=db.backref("wallet", uselist=False))
    transactions = db.relationship("WalletTransaction", backref="wallet", lazy="dynamic")

    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "balance": float(self.balance) if self.balance else 0.0,
            "currency": self.currency,
            "lifetime_earned": float(self.lifetime_earned) if self.lifetime_earned else 0.0,
            "lifetime_spent": float(self.lifetime_spent) if self.lifetime_spent else 0.0,
            "level": self.level,
            "xp": self.xp,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class WalletTransaction(db.Model):
    """
    Cüzdan İşlem Geçmişi - Çift defter (Double Entry) mantığı.
    
    Her işlem burada kayıt altına alınır.
    """
    __tablename__ = "wallet_transactions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_id = db.Column(UUID(as_uuid=True), db.ForeignKey("wallets.id"), nullable=False)
    
    amount = db.Column(db.Numeric(12, 2), nullable=False)  # +10.00 veya -5.00
    balance_after = db.Column(db.Numeric(12, 2))           # İşlem sonrası bakiye
    
    transaction_type = db.Column(db.String(30), nullable=False)  # reward, penalty, withdrawal, bonus, referral
    category = db.Column(db.String(50))                          # energy_saving, automation, challenge, manual
    
    description = db.Column(db.String(255))
    reference_id = db.Column(db.String(100))  # İlişkili kayıt ID (automation_id, challenge_id vb.)
    reference_type = db.Column(db.String(50)) # automation, challenge, device, manual
    
    extra_data = db.Column(JSONB, default=dict)  # Ek bilgiler
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": str(self.id),
            "wallet_id": str(self.wallet_id),
            "amount": float(self.amount) if self.amount else 0.0,
            "balance_after": float(self.balance_after) if self.balance_after else 0.0,
            "transaction_type": self.transaction_type,
            "category": self.category,
            "description": self.description,
            "reference_id": self.reference_id,
            "reference_type": self.reference_type,
            "extra_data": self.extra_data or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class VppRule(db.Model):
    """VPP Otomasyon Kuralları - İleri seviye enerji yönetimi."""
    __tablename__ = "vpp_rules"
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id"), nullable=False)
    device_id = db.Column(UUID(as_uuid=True), db.ForeignKey("smart_devices.id"))
    
    name = db.Column(db.String(100))
    description = db.Column(db.String(255))
    
    is_active = db.Column(db.Boolean, default=True)
    trigger = db.Column(JSONB, nullable=False)
    action = db.Column(JSONB, nullable=False)
    priority = db.Column(db.Integer, default=1)
    
    last_triggered_at = db.Column(db.DateTime)
    trigger_count = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "device_id": str(self.device_id) if self.device_id else None,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "trigger": self.trigger,
            "action": self.action,
            "priority": self.priority,
            "last_triggered_at": self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            "trigger_count": self.trigger_count,
        }


# ==========================================
# 5. VERİ AMBARI (TimescaleDB)
# ==========================================


class DeviceTelemetry(db.Model):
    """
    Cihaz Telemetri Verisi - TimescaleDB Hypertable.
    
    Migration sonrası: SELECT create_hypertable('device_telemetry', 'time');
    """
    __tablename__ = "device_telemetry"

    time = db.Column(db.DateTime(timezone=True), primary_key=True, nullable=False)
    device_id = db.Column(UUID(as_uuid=True), db.ForeignKey("smart_devices.id"), primary_key=True)
    key = db.Column(db.String(50), primary_key=True)
    
    value = db.Column(db.Float)
    quality = db.Column(db.Integer, default=1)

    def to_dict(self):
        return {
            "time": self.time.isoformat() if self.time else None,
            "device_id": str(self.device_id),
            "key": self.key,
            "value": self.value,
            "quality": self.quality,
        }


class Notification(db.Model):
    """
    Kullanıcı Bildirimleri - Telegram, Push, Email, In-App.
    
    Her bildirim hem veritabanına kaydedilir hem de ilgili kanaldan gönderilir.
    """
    __tablename__ = "notifications"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id"))
    
    title = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    
    # Bildirim tipi: info, warning, error, success, price_alert, device_alert, automation
    type = db.Column(db.String(30), default="info")
    
    # Kanal: in_app, telegram, email, push, sms
    channel = db.Column(db.String(20), default="in_app")
    
    # Durum
    status = db.Column(db.String(20), default=NotificationStatus.PENDING.value)
    is_read = db.Column(db.Boolean, default=False)
    
    # İlişkili kayıt (opsiyonel)
    reference_id = db.Column(db.String(100))
    reference_type = db.Column(db.String(50))  # device, automation, market, system
    
    # Ek veri
    data = db.Column(JSONB, default=dict)
    
    sent_at = db.Column(db.DateTime)
    read_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "organization_id": str(self.organization_id) if self.organization_id else None,
            "title": self.title,
            "message": self.message,
            "type": self.type,
            "channel": self.channel,
            "status": self.status,
            "is_read": self.is_read,
            "reference_id": self.reference_id,
            "reference_type": self.reference_type,
            "data": self.data or {},
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ==========================================
# 6. DENETİM KAYITLARI (AUDIT LOG)
# ==========================================


class AuditLog(db.Model):
    """
    Denetim Kaydı - Kullanıcı işlemlerinin geçmişi.
    
    Row-level security: Admin tüm kayıtları görür, diğerleri sadece kendi işlemlerini.
    """
    __tablename__ = "audit_logs"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id"), nullable=False)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    
    action = db.Column(db.String(100), nullable=False)  # device.toggle, automation.create, etc.
    resource_type = db.Column(db.String(50))  # device, automation, integration, etc.
    resource_id = db.Column(db.String(100))   # İlgili kaynağın ID'si
    
    details = db.Column(JSONB, default=dict)  # Ek bilgiler (eski/yeni değerler vb.)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # İlişkiler
    user = db.relationship("User", backref="audit_logs", lazy=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "user_id": str(self.user_id),
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "details": self.details or {},
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
