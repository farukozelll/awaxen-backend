"""
Seed Data Script - Geliştirme ortamı için örnek veri oluşturur.

Kullanım:
    docker-compose exec backend python scripts/seed_data.py
    
    veya Flask CLI:
    flask seed
"""
import os
import sys
import random
from datetime import datetime, timedelta
from decimal import Decimal
import uuid

# Proje kök dizinini path'e ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models import (
    Organization, User, Gateway, Integration, SmartDevice, SmartAsset,
    Automation, MarketPrice, Notification, Wallet, WalletTransaction,
    OrganizationType, DeviceStatus, AssetType
)


# ==========================================
# SEED DATA CONFIGURATION
# ==========================================

DEMO_ORGANIZATION = {
    "name": "Awaxen Demo Ev",
    "slug": "awaxen-demo",
    "type": OrganizationType.HOME.value,
    "timezone": "Europe/Istanbul",
    "location": {
        "city": "İstanbul",
        "district": "Kadıköy",
        "lat": 40.9833,
        "lng": 29.0333
    },
    "subscription_plan": "premium"
}

DEMO_USER = {
    "auth0_id": "auth0|demo_user_001",
    "email": "demo@awaxen.com",
    "full_name": "Demo Kullanıcı",
    "phone_number": "+905551234567",
    "role": "admin"
}

DEVICE_TYPES = [
    {"type": "relay", "brand": "Shelly", "model": "Shelly 1PM", "is_actuator": True, "is_sensor": True},
    {"type": "plug", "brand": "Shelly", "model": "Shelly Plug S", "is_actuator": True, "is_sensor": True},
    {"type": "dimmer", "brand": "Shelly", "model": "Shelly Dimmer 2", "is_actuator": True, "is_sensor": False},
    {"type": "sensor", "brand": "Shelly", "model": "Shelly H&T", "is_actuator": False, "is_sensor": True},
    {"type": "meter", "brand": "Shelly", "model": "Shelly EM", "is_actuator": False, "is_sensor": True},
]

DEVICE_NAMES = [
    "Salon Lambası", "Mutfak Prizi", "Yatak Odası Klima", "Banyo Isıtıcı",
    "Garaj Kapısı", "Bahçe Sulama", "Havuz Pompası", "Güneş Paneli İnverter",
    "EV Şarj İstasyonu", "Buzdolabı", "Çamaşır Makinesi", "Bulaşık Makinesi"
]

ASSET_CONFIGS = [
    {"name": "Salon Kliması", "type": AssetType.HVAC.value, "power": 2500, "priority": 2},
    {"name": "EV Şarj", "type": AssetType.EV_CHARGER.value, "power": 7400, "priority": 3},
    {"name": "Elektrikli Şofben", "type": AssetType.WATER_HEATER.value, "power": 2000, "priority": 4},
    {"name": "Havuz Pompası", "type": "pool_pump", "power": 1500, "priority": 5},
]

AUTOMATION_TEMPLATES = [
    {
        "name": "Ucuz Saatte Şarj",
        "description": "Elektrik fiyatı 2 TL/kWh altına düşünce EV şarjını başlat",
        "rules": {
            "trigger": {"type": "price", "operator": "<", "value": 2.0},
            "action": {"type": "turn_on"},
            "conditions": [{"type": "time_range", "start": "22:00", "end": "06:00"}]
        }
    },
    {
        "name": "Puant Tasarrufu",
        "description": "17:00-22:00 arası klimayı kapat",
        "rules": {
            "trigger": {"type": "time_range", "start": "17:00", "end": "22:00"},
            "action": {"type": "turn_off"}
        }
    },
    {
        "name": "Gece Isıtma",
        "description": "Gece ucuz elektrikle şofbeni çalıştır",
        "rules": {
            "trigger": {"type": "time_range", "start": "02:00", "end": "06:00"},
            "action": {"type": "turn_on"}
        }
    }
]


# ==========================================
# SEED FUNCTIONS
# ==========================================

def seed_organization():
    """Demo organizasyon oluştur."""
    org = Organization.query.filter_by(slug=DEMO_ORGANIZATION["slug"]).first()
    if org:
        print(f"✓ Organizasyon zaten var: {org.name}")
        return org
    
    org = Organization(**DEMO_ORGANIZATION)
    db.session.add(org)
    db.session.commit()
    print(f"✓ Organizasyon oluşturuldu: {org.name}")
    return org


def seed_user(organization):
    """Demo kullanıcı oluştur."""
    user = User.query.filter_by(auth0_id=DEMO_USER["auth0_id"]).first()
    if user:
        print(f"✓ Kullanıcı zaten var: {user.email}")
        return user
    
    user = User(
        organization_id=organization.id,
        **DEMO_USER
    )
    db.session.add(user)
    db.session.commit()
    print(f"✓ Kullanıcı oluşturuldu: {user.email}")
    return user


def seed_gateway(organization):
    """Demo gateway oluştur."""
    gateway = Gateway.query.filter_by(serial_number="AWX-GW-DEMO-001").first()
    if gateway:
        print(f"✓ Gateway zaten var: {gateway.serial_number}")
        return gateway
    
    gateway = Gateway(
        organization_id=organization.id,
        serial_number="AWX-GW-DEMO-001",
        model="Teltonika RUT956",
        ip_address="192.168.1.1",
        mac_address="AA:BB:CC:DD:EE:FF",
        status="online",
        last_seen=datetime.utcnow(),
        settings={"mqtt_topic": "awaxen/demo/gateway"}
    )
    db.session.add(gateway)
    db.session.commit()
    print(f"✓ Gateway oluşturuldu: {gateway.serial_number}")
    return gateway


def seed_integration(organization):
    """Demo Shelly entegrasyonu oluştur."""
    integration = Integration.query.filter_by(
        organization_id=organization.id,
        provider="shelly"
    ).first()
    if integration:
        print(f"✓ Entegrasyon zaten var: {integration.provider}")
        return integration
    
    integration = Integration(
        organization_id=organization.id,
        provider="shelly",
        status="active",
        provider_data={"server": "shelly-eu-01"},
        last_sync_at=datetime.utcnow()
    )
    # Demo token (gerçek değil)
    integration.access_token = "demo_shelly_auth_key_12345"
    
    db.session.add(integration)
    db.session.commit()
    print(f"✓ Entegrasyon oluşturuldu: {integration.provider}")
    return integration


def seed_devices(organization, gateway, integration):
    """Demo cihazlar oluştur."""
    existing = SmartDevice.query.filter_by(organization_id=organization.id).count()
    if existing >= 5:
        print(f"✓ Cihazlar zaten var: {existing} adet")
        return SmartDevice.query.filter_by(organization_id=organization.id).all()
    
    devices = []
    for i, name in enumerate(DEVICE_NAMES[:8]):
        device_config = random.choice(DEVICE_TYPES)
        
        device = SmartDevice(
            organization_id=organization.id,
            gateway_id=gateway.id if random.random() > 0.5 else None,
            integration_id=integration.id if random.random() > 0.3 else None,
            external_id=f"shelly_{uuid.uuid4().hex[:8]}",
            name=name,
            brand=device_config["brand"],
            model=device_config["model"],
            is_actuator=device_config["is_actuator"],
            is_sensor=device_config["is_sensor"],
            is_online=random.random() > 0.2,
            last_seen=datetime.utcnow() - timedelta(minutes=random.randint(0, 60)),
            settings={
                "device_type": device_config["type"],
                "auto_off": random.choice([0, 1800, 3600]),
                "led_enabled": random.choice([True, False])
            }
        )
        devices.append(device)
        db.session.add(device)
    
    db.session.commit()
    print(f"✓ {len(devices)} cihaz oluşturuldu")
    return devices


def seed_assets(organization, devices):
    """Demo varlıklar oluştur."""
    existing = SmartAsset.query.filter_by(organization_id=organization.id).count()
    if existing >= 3:
        print(f"✓ Varlıklar zaten var: {existing} adet")
        return SmartAsset.query.filter_by(organization_id=organization.id).all()
    
    assets = []
    for i, config in enumerate(ASSET_CONFIGS):
        device = devices[i] if i < len(devices) else None
        
        asset = SmartAsset(
            organization_id=organization.id,
            device_id=device.id if device else None,
            name=config["name"],
            type=config["type"],
            nominal_power_watt=config["power"],
            priority=config["priority"],
            settings={"min_runtime": 30, "max_runtime": 240}
        )
        assets.append(asset)
        db.session.add(asset)
    
    db.session.commit()
    print(f"✓ {len(assets)} varlık oluşturuldu")
    return assets


def seed_automations(organization, assets):
    """Demo otomasyonlar oluştur."""
    existing = Automation.query.filter_by(organization_id=organization.id).count()
    if existing >= 2:
        print(f"✓ Otomasyonlar zaten var: {existing} adet")
        return
    
    for i, template in enumerate(AUTOMATION_TEMPLATES):
        asset = assets[i] if i < len(assets) else None
        
        automation = Automation(
            organization_id=organization.id,
            asset_id=asset.id if asset else None,
            name=template["name"],
            description=template["description"],
            rules=template["rules"],
            is_active=True
        )
        db.session.add(automation)
    
    db.session.commit()
    print(f"✓ {len(AUTOMATION_TEMPLATES)} otomasyon oluşturuldu")


def seed_market_prices():
    """Son 7 günlük piyasa fiyatları oluştur."""
    existing = MarketPrice.query.count()
    if existing >= 24 * 3:
        print(f"✓ Piyasa fiyatları zaten var: {existing} kayıt")
        return
    
    now = datetime.utcnow()
    prices_added = 0
    
    for day_offset in range(7):
        base_date = now - timedelta(days=day_offset)
        
        for hour in range(24):
            time = base_date.replace(hour=hour, minute=0, second=0, microsecond=0)
            
            # Gerçekçi fiyat simülasyonu
            if 22 <= hour or hour < 6:
                base_price = random.uniform(1.0, 1.8)  # Gece
            elif 17 <= hour < 22:
                base_price = random.uniform(3.5, 5.5)  # Puant
            else:
                base_price = random.uniform(2.0, 3.0)  # Gündüz
            
            existing = MarketPrice.query.filter_by(time=time).first()
            if not existing:
                price = MarketPrice(
                    time=time,
                    price=round(base_price, 2),
                    ptf=round(base_price * 1000, 2),
                    smf=round(base_price * 1000 * 1.05, 2),
                    currency="TRY",
                    region="TR"
                )
                db.session.add(price)
                prices_added += 1
    
    db.session.commit()
    print(f"✓ {prices_added} piyasa fiyatı oluşturuldu")


def seed_wallet(user):
    """Demo cüzdan ve işlemler oluştur."""
    wallet = Wallet.query.filter_by(user_id=user.id).first()
    if wallet:
        print(f"✓ Cüzdan zaten var: {float(wallet.balance)} AWX")
        return wallet
    
    wallet = Wallet(
        user_id=user.id,
        balance=Decimal("150.00"),
        lifetime_earned=Decimal("200.00"),
        lifetime_spent=Decimal("50.00"),
        level=3,
        xp=450
    )
    db.session.add(wallet)
    db.session.flush()
    
    # Örnek işlemler
    transactions = [
        {"amount": 50, "type": "reward", "category": "energy_saving", "desc": "Haftalık tasarruf ödülü"},
        {"amount": 25, "type": "reward", "category": "automation", "desc": "Otomasyon kurulum bonusu"},
        {"amount": 100, "type": "bonus", "category": "manual", "desc": "Hoş geldin bonusu"},
        {"amount": 25, "type": "reward", "category": "challenge", "desc": "Puant saati challenge tamamlandı"},
        {"amount": -50, "type": "withdrawal", "category": "manual", "desc": "Hediye kartı çekimi"},
    ]
    
    balance = Decimal("0")
    for tx in transactions:
        balance += Decimal(str(tx["amount"]))
        transaction = WalletTransaction(
            wallet_id=wallet.id,
            amount=Decimal(str(tx["amount"])),
            balance_after=balance,
            transaction_type=tx["type"],
            category=tx["category"],
            description=tx["desc"],
            created_at=datetime.utcnow() - timedelta(days=random.randint(1, 30))
        )
        db.session.add(transaction)
    
    db.session.commit()
    print(f"✓ Cüzdan oluşturuldu: {float(wallet.balance)} AWX, {len(transactions)} işlem")
    return wallet


def seed_notifications(user):
    """Demo bildirimler oluştur."""
    existing = Notification.query.filter_by(user_id=user.id).count()
    if existing >= 3:
        print(f"✓ Bildirimler zaten var: {existing} adet")
        return
    
    notifications = [
        {
            "title": "Fiyat Düştü! 🎉",
            "message": "Elektrik fiyatı 1.5 TL/kWh'e düştü. EV şarjınızı başlatmak için ideal zaman!",
            "type": "price_alert",
            "is_read": False
        },
        {
            "title": "Otomasyon Çalıştı",
            "message": "'Ucuz Saatte Şarj' otomasyonu tetiklendi ve EV şarjı başlatıldı.",
            "type": "automation",
            "is_read": True
        },
        {
            "title": "Cihaz Çevrimdışı",
            "message": "Salon Lambası cihazı 30 dakikadır çevrimdışı.",
            "type": "device_alert",
            "is_read": False
        },
        {
            "title": "Seviye Atladın! 🚀",
            "message": "Tebrikler! Seviye 3'e ulaştın. 50 AWX bonus kazandın!",
            "type": "success",
            "is_read": True
        }
    ]
    
    for notif in notifications:
        notification = Notification(
            user_id=user.id,
            title=notif["title"],
            message=notif["message"],
            type=notif["type"],
            channel="in_app",
            is_read=notif["is_read"],
            status="read" if notif["is_read"] else "sent",
            read_at=datetime.utcnow() if notif["is_read"] else None,
            created_at=datetime.utcnow() - timedelta(hours=random.randint(1, 48))
        )
        db.session.add(notification)
    
    db.session.commit()
    print(f"✓ {len(notifications)} bildirim oluşturuldu")


# ==========================================
# MAIN
# ==========================================

def run_seed():
    """Tüm seed işlemlerini çalıştır."""
    print("\n" + "="*50)
    print("🌱 AWAXEN SEED DATA")
    print("="*50 + "\n")
    
    # 1. Organizasyon
    org = seed_organization()
    
    # 2. Kullanıcı
    user = seed_user(org)
    
    # 3. Gateway
    gateway = seed_gateway(org)
    
    # 4. Entegrasyon
    integration = seed_integration(org)
    
    # 5. Cihazlar
    devices = seed_devices(org, gateway, integration)
    
    # 6. Varlıklar
    assets = seed_assets(org, devices)
    
    # 7. Otomasyonlar
    seed_automations(org, assets)
    
    # 8. Piyasa Fiyatları
    seed_market_prices()
    
    # 9. Cüzdan
    seed_wallet(user)
    
    # 10. Bildirimler
    seed_notifications(user)
    
    print("\n" + "="*50)
    print("✅ SEED DATA TAMAMLANDI!")
    print("="*50 + "\n")
    
    print("Demo Kullanıcı Bilgileri:")
    print(f"  Email: {DEMO_USER['email']}")
    print(f"  Auth0 ID: {DEMO_USER['auth0_id']}")
    print(f"  Organizasyon: {DEMO_ORGANIZATION['name']}")
    print()


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        run_seed()
