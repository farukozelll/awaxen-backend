"""
Awaxen Models - RBAC (Role-Based Access Control).

Rol ve yetki yönetimi modelleri.
"""
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from sqlalchemy.dialects.postgresql import UUID

from app.extensions import db


def utcnow() -> datetime:
    """Timezone-aware UTC datetime döndür."""
    return datetime.now(timezone.utc)


# Rol-Yetki ara tablosu (Many-to-Many)
role_permissions = db.Table(
    'role_permissions',
    db.Column('role_id', UUID(as_uuid=True), db.ForeignKey('roles.id'), primary_key=True),
    db.Column('permission_id', UUID(as_uuid=True), db.ForeignKey('permissions.id'), primary_key=True),
    db.Column('created_at', db.DateTime(timezone=True), default=utcnow)
)


class Permission(db.Model):
    """
    Yetki Tanımı - Granüler izinler.
    
    Örnek: can_edit_device, can_delete_automation, can_view_wallet
    """
    __tablename__ = 'permissions'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = db.Column(db.String(100), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    category = db.Column(db.String(50), index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    def to_dict(self) -> dict:
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
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    is_system = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # İlişkiler
    permissions = db.relationship(
        'Permission',
        secondary=role_permissions,
        backref=db.backref('roles', lazy='dynamic'),
        lazy='joined'
    )

    def to_dict(self, include_permissions: bool = False) -> dict:
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
    def get_by_code(cls, code: str) -> Optional["Role"]:
        """Rol koduna göre bul."""
        return cls.query.filter_by(code=code, is_active=True).first()
    
    @classmethod
    def seed_default_roles(cls) -> bool:
        """Varsayılan rolleri ve yetkileri oluştur."""
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
                "permissions": list(permissions_map.keys()),
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
