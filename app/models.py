from datetime import datetime
from enum import Enum

from sqlalchemy.dialects.postgresql import JSON

from . import db


# ==========================================
# 0. ENUM SINIFLARI (Standartlaşma İçin)
# ==========================================


class SiteType(str, Enum):
    """Saha tipi - fiziksel mekan türü."""
    GREENHOUSE = "GREENHOUSE"      # Sera
    FIELD = "FIELD"                # Açık Tarla
    SOLAR_PLANT = "SOLAR_PLANT"    # Güneş Santrali
    FACTORY = "FACTORY"            # Fabrika
    WAREHOUSE = "WAREHOUSE"        # Depo
    OTHER = "OTHER"                # Diğer


class DeviceStatus(str, Enum):
    """Cihaz durumu - detaylı status bilgisi."""
    ONLINE = "ONLINE"              # Çevrimiçi, veri gönderiyor
    OFFLINE = "OFFLINE"            # Çevrimdışı
    MAINTENANCE = "MAINTENANCE"    # Bakımda
    ERROR = "ERROR"                # Arızalı
    UNKNOWN = "UNKNOWN"            # Bilinmiyor (ilk kayıt)


class NodeProtocol(str, Enum):
    """Node haberleşme protokolü."""
    LORA = "LORA"                  # LoRaWAN
    ZIGBEE = "ZIGBEE"              # ZigBee
    WIFI = "WIFI"                  # WiFi
    WIRED = "WIRED"                # Kablolu
    MODBUS = "MODBUS"              # Modbus RTU/TCP
    OTHER = "OTHER"                # Diğer


class AssetType(str, Enum):
    """Asset tipi - sensör mü aktüatör mü?"""
    SENSOR = "SENSOR"              # Veri okur (Sıcaklık, Nem, vb.)
    ACTUATOR = "ACTUATOR"          # İş yapar (Vana, Röle, Motor)
    METER = "METER"                # Sayaç (Enerji, Su)
    CONTROLLER = "CONTROLLER"      # Kontrol cihazı


class AssetCategory(str, Enum):
    """Asset kategorisi - ne ölçüyor/yapıyor?"""
    # Sensörler
    TEMPERATURE = "TEMPERATURE"    # Sıcaklık
    HUMIDITY = "HUMIDITY"          # Nem
    SOIL_MOISTURE = "SOIL_MOISTURE"  # Toprak Nemi
    LIGHT = "LIGHT"                # Işık
    CO2 = "CO2"                    # Karbondioksit
    PH = "PH"                      # pH
    EC = "EC"                      # Elektriksel İletkenlik
    PRESSURE = "PRESSURE"          # Basınç
    FLOW = "FLOW"                  # Akış
    LEVEL = "LEVEL"                # Seviye
    # Aktüatörler
    VALVE = "VALVE"                # Vana
    PUMP = "PUMP"                  # Pompa
    RELAY = "RELAY"                # Röle
    MOTOR = "MOTOR"                # Motor
    HEATER = "HEATER"              # Isıtıcı
    FAN = "FAN"                    # Fan
    LIGHT_CONTROL = "LIGHT_CONTROL"  # Aydınlatma
    # Sayaçlar
    ENERGY_METER = "ENERGY_METER"  # Enerji Sayacı
    WATER_METER = "WATER_METER"    # Su Sayacı
    # Enerji/Solar Asset'leri
    BATTERY = "BATTERY"            # Batarya Ünitesi
    PV_STRING = "PV_STRING"        # Güneş Paneli Dizisi
    GRID = "GRID"                  # Şebeke Bağlantı Noktası
    ACTIVE_POWER = "ACTIVE_POWER"  # Anlık Üretim/Tüketim
    # Diğer
    OTHER = "OTHER"


class NodeType(str, Enum):
    """Node tipi - cihazın türü."""
    SENSOR_NODE = "SENSOR_NODE"    # LoRa Sensör Kutusu
    INVERTER = "INVERTER"          # Solar Inverter (Huawei, Sungrow vb.)
    PLC = "PLC"                    # Endüstriyel Kontrolcü
    ENERGY_METER = "ENERGY_METER"  # Ana Sayaç
    EV_CHARGER = "EV_CHARGER"      # Elektrikli Araç Şarj İstasyonu
    BATTERY_STORAGE = "BATTERY_STORAGE"  # Batarya Depolama Sistemi
    OTHER = "OTHER"


class InverterBrand(str, Enum):
    """Inverter markası - Modbus haritası için."""
    HUAWEI = "HUAWEI"
    SUNGROW = "SUNGROW"
    SMA = "SMA"
    FRONIUS = "FRONIUS"
    GOODWE = "GOODWE"
    GROWATT = "GROWATT"
    SOLAREDGE = "SOLAREDGE"
    ABB = "ABB"
    SCHNEIDER = "SCHNEIDER"
    OTHER = "OTHER"


class TariffType(str, Enum):
    """Elektrik tarife tipi."""
    SINGLE_TIME = "SINGLE_TIME"    # Tek zamanlı
    THREE_TIME = "THREE_TIME"      # Üç zamanlı (Gündüz, Puant, Gece)
    HOURLY = "HOURLY"              # Saatlik (PTF/SMF - Spot Piyasa)


class VppTriggerType(str, Enum):
    """VPP kural tetikleyici tipi."""
    PRICE_THRESHOLD = "PRICE_THRESHOLD"  # Fiyat eşiği
    TIME_RANGE = "TIME_RANGE"            # Zaman aralığı
    SOC_THRESHOLD = "SOC_THRESHOLD"      # Batarya doluluk eşiği
    GRID_DEMAND = "GRID_DEMAND"          # Şebeke talep sinyali
    WEATHER = "WEATHER"                  # Hava durumu bazlı


class VppActionType(str, Enum):
    """VPP kural aksiyon tipi."""
    CHARGE_BATTERY = "CHARGE_BATTERY"        # Bataryayı şarj et
    DISCHARGE_BATTERY = "DISCHARGE_BATTERY"  # Bataryayı deşarj et
    LIMIT_EXPORT = "LIMIT_EXPORT"            # Şebekeye vermeyi sınırla
    LIMIT_IMPORT = "LIMIT_IMPORT"            # Şebekeden çekmeyi sınırla
    SET_POWER = "SET_POWER"                  # Güç seviyesi ayarla


# ==========================================
# 1. KULLANICI VE YETKİ KATMANI (Auth0)
# ==========================================


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    auth0_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    full_name = db.Column(db.String(100))
    role = db.Column(db.String(20), default="viewer")  # admin, operator, viewer
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sites = db.relationship("Site", backref="owner", lazy=True)

    def to_dict(self):
        return {"id": self.id, "email": self.email, "role": self.role}


# ==========================================
# 2. FİZİKSEL YERLEŞİM KATMANI
# ==========================================


class Site(db.Model):
    """Fiziksel saha/mekan - Sera, Tarla, Fabrika vb."""
    __tablename__ = "sites"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    
    # Konum bilgileri
    city = db.Column(db.String(50))
    district = db.Column(db.String(50))  # İlçe
    location = db.Column(db.String(50))  # Eski format uyumluluğu
    address = db.Column(db.String(200))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    
    # Saha tipi ve özellikleri
    site_type = db.Column(
        db.String(50), 
        default=SiteType.GREENHOUSE.value,
        index=True
    )
    
    # Polymorphic Storage - Her tipin özelliği farklıdır
    # Sera için: {"rows": 10, "columns": 5, "width_m": 100, "length_m": 200}
    # Tarla için: {"area_m2": 5000, "crop": "Bugday"}
    # Solar için: {"panel_count": 100, "capacity_kw": 50}
    dimensions = db.Column(JSON, default=dict)
    
    # Görsel ve metadata
    image_url = db.Column(db.String(300))
    metadata_info = db.Column(JSON, default=dict)
    
    # Zaman damgaları
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    devices = db.relationship(
        "Device",
        backref="site",
        lazy=True,
        cascade="all, delete-orphan",
    )

    def to_dict(self, include_devices=False):
        """Site nesnesini dictionary'e çevir."""
        data = {
            "id": self.id,
            "name": self.name,
            "city": self.city,
            "district": self.district,
            "location": self.location,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "site_type": self.site_type,
            "dimensions": self.dimensions or {},
            "image_url": self.image_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "device_count": len(self.devices),
        }
        if include_devices:
            data["devices"] = [d.to_dict() for d in self.devices]
        return data


# ==========================================
# 3. DONANIM KATMANI (Core & Nodes)
# ==========================================


class Device(db.Model):
    """Core/Gateway cihazı - Sahadaki internet kapısı (Teltonika/RPi)."""
    __tablename__ = "devices"

    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False)
    serial_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100))
    
    # Detaylı durum bilgisi (boolean yerine enum)
    status = db.Column(
        db.String(20), 
        default=DeviceStatus.UNKNOWN.value,
        index=True
    )
    last_seen = db.Column(db.DateTime)
    
    # Cihaz bilgileri
    model = db.Column(db.String(50))
    firmware_version = db.Column(db.String(20))
    ip_address = db.Column(db.String(45))  # IPv4 veya IPv6
    mac_address = db.Column(db.String(17))  # AA:BB:CC:DD:EE:FF
    
    # Metadata
    metadata_info = db.Column(JSON, default=dict)
    
    # Zaman damgaları
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    nodes = db.relationship(
        "Node",
        backref="device",
        lazy=True,
        cascade="all, delete-orphan",
    )

    @property
    def is_online(self):
        """Geriye uyumluluk için is_online property."""
        return self.status == DeviceStatus.ONLINE.value

    @is_online.setter
    def is_online(self, value):
        """Geriye uyumluluk için is_online setter."""
        if value:
            self.status = DeviceStatus.ONLINE.value
        else:
            self.status = DeviceStatus.OFFLINE.value

    def to_dict(self, include_nodes=False):
        """Device nesnesini dictionary'e çevir."""
        data = {
            "id": self.id,
            "site_id": self.site_id,
            "serial_number": self.serial_number,
            "name": self.name,
            "status": self.status,
            "is_online": self.is_online,  # Geriye uyumluluk
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "model": self.model,
            "firmware_version": self.firmware_version,
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "node_count": len(self.nodes),
        }
        if include_nodes:
            data["nodes"] = [n.to_dict() for n in self.nodes]
        return data


class Node(db.Model):
    """Postacı/Taşıyıcı - Sahada kablosuz haberleşen kutu veya Inverter."""
    __tablename__ = "nodes"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("devices.id"), nullable=False)
    name = db.Column(db.String(100))
    node_type = db.Column(db.String(50), nullable=False, default=NodeType.SENSOR_NODE.value)
    
    # Haberleşme protokolü
    protocol = db.Column(
        db.String(50), 
        default=NodeProtocol.LORA.value
    )
    
    # Node adresi (LoRa DevEUI, Modbus ID, vb.)
    node_address = db.Column(db.String(50))
    
    # Pil durumu (Solar node için önemli, 0-100 arası yüzde)
    battery_level = db.Column(db.Float)
    
    # Sinyal gücü (RSSI, dBm cinsinden)
    signal_strength = db.Column(db.Float)
    
    # Gateway'e olan tahmini mesafe (metre)
    distance_estimate = db.Column(db.Float)
    
    # Son görülme zamanı
    last_seen = db.Column(db.DateTime)
    
    # --- INVERTER ÖZEL ALANLARI ---
    # Marka (Modbus haritası seçimi için)
    brand = db.Column(db.String(50), default=InverterBrand.OTHER.value)
    
    # Model numarası (Örn: SUN2000-100KTL, SG110CX)
    model_number = db.Column(db.String(100))
    
    # Kapasite bilgileri (VPP için kritik)
    # Örn: {"max_power_kw": 100, "battery_capacity_kwh": 20, "pv_capacity_kwp": 120}
    capacity_info = db.Column(JSON, default=dict)
    
    # Konfigürasyon (Haberleşme ayarları)
    # Örn: {"protocol": "MODBUS_TCP", "ip": "192.168.1.10", "port": 502, "slave_id": 1}
    configuration = db.Column(JSON, default=dict)
    
    # Zaman damgaları
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişki: Bir Node'un birden fazla ucu (Asset) olabilir
    assets = db.relationship(
        "Asset",
        backref="node",
        lazy=True,
        cascade="all, delete-orphan",
    )

    def to_dict(self, include_assets=False):
        """Node nesnesini dictionary'e çevir."""
        data = {
            "id": self.id,
            "device_id": self.device_id,
            "name": self.name,
            "node_type": self.node_type,
            "protocol": self.protocol,
            "node_address": self.node_address,
            "battery_level": self.battery_level,
            "signal_strength": self.signal_strength,
            "distance_estimate": self.distance_estimate,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            # Inverter alanları
            "brand": self.brand,
            "model_number": self.model_number,
            "capacity_info": self.capacity_info or {},
            "configuration": self.configuration or {},
            "asset_count": len(self.assets),
        }
        if include_assets:
            data["assets"] = [a.to_dict() for a in self.assets]
        return data


# ==========================================
# 4. INVENTORY / ASSET KATMANI (Enstrümanlar)
# ==========================================


class Asset(db.Model):
    """Inventory/Enstrüman - Node'a bağlı fiziksel uç birimler (Sensör, Vana, vb.)."""
    __tablename__ = "assets"

    id = db.Column(db.Integer, primary_key=True)
    node_id = db.Column(db.Integer, db.ForeignKey("nodes.id"), nullable=False)
    
    # Tanımlayıcı bilgiler
    name = db.Column(db.String(100), nullable=False)  # Örn: "Sıra 1 Nem Sensörü"
    description = db.Column(db.String(255))
    
    # Tip ve kategori
    asset_type = db.Column(
        db.String(50), 
        default=AssetType.SENSOR.value,
        index=True
    )
    category = db.Column(
        db.String(50), 
        default=AssetCategory.OTHER.value
    )
    
    # MQTT/Telemetri Mapping - Gelen veride bu sensör hangi key ile geliyor?
    # Örn: "temp_01", "soil_moisture_1", "valve_status"
    variable_name = db.Column(db.String(50), nullable=False, index=True)
    
    # Port/Kanal bilgisi - Node'un hangi portuna bağlı?
    port_number = db.Column(db.Integer)  # 1, 2, 3...
    
    # Birim ve kalibrasyon
    unit = db.Column(db.String(20))  # "°C", "%", "kW", "m³/h"
    min_value = db.Column(db.Float)  # Minimum beklenen değer
    max_value = db.Column(db.Float)  # Maximum beklenen değer
    calibration_offset = db.Column(db.Float, default=0)  # Kalibrasyon düzeltmesi
    
    # Konum bilgisi (Sera içindeki pozisyon)
    # Örn: {"row": 1, "column": 3, "zone": "A"}
    position = db.Column(JSON, default=dict)
    
    # Ek konfigürasyon
    # Örn: {"alarm_low": 10, "alarm_high": 40, "precision": 2}
    configuration = db.Column(JSON, default=dict)
    
    # Durum
    is_active = db.Column(db.Boolean, default=True)
    
    # Zaman damgaları
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        """Asset nesnesini dictionary'e çevir."""
        return {
            "id": self.id,
            "node_id": self.node_id,
            "name": self.name,
            "description": self.description,
            "asset_type": self.asset_type,
            "category": self.category,
            "variable_name": self.variable_name,
            "port_number": self.port_number,
            "unit": self.unit,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "calibration_offset": self.calibration_offset,
            "position": self.position or {},
            "configuration": self.configuration or {},
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def apply_calibration(self, raw_value: float) -> float:
        """Ham değere kalibrasyon uygula."""
        return raw_value + (self.calibration_offset or 0)


# ==========================================
# 5. VERİ VE KOMUT KATMANI (Operasyon)
# ==========================================


class Telemetry(db.Model):
    __tablename__ = "telemetry"

    id = db.Column(db.Integer, primary_key=True)
    node_id = db.Column(db.Integer, db.ForeignKey("nodes.id"), nullable=False)
    key = db.Column(db.String(50), nullable=False)  # "temperature", "active_power"
    value = db.Column(db.Float, nullable=False)
    time = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {"time": self.time.isoformat(), "key": self.key, "val": self.value}


class Command(db.Model):
    __tablename__ = "commands"

    id = db.Column(db.Integer, primary_key=True)
    node_id = db.Column(db.Integer, db.ForeignKey("nodes.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    command_type = db.Column(db.String(50), nullable=False)  # SET_POWER, SET_MODE
    payload = db.Column(JSON)  # {"state": "ON"}
    status = db.Column(db.String(20), default="PENDING")  # PENDING, SENT, EXECUTED
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    executed_at = db.Column(db.DateTime)


# ==========================================
# 5. ESKİ UYUMLULUK (Basit sensör verisi)
# ==========================================


class SensorData(db.Model):
    """Basit sensör verisi tablosu (geriye uyumluluk için)."""

    __tablename__ = "sensor_data"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), nullable=False)
    sensor_type = db.Column(db.String(50), nullable=False)
    value = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    metadata_info = db.Column(JSON, default=dict)

    def to_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "sensor_type": self.sensor_type,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
        }


# ==========================================
# 6. ENERJİ VE VPP KATMANI (Sanal Güç Santrali)
# ==========================================


class Tariff(db.Model):
    """Elektrik Tarifeleri (EPDK/Şeffaf Platform)."""
    __tablename__ = "tariffs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    
    name = db.Column(db.String(100), nullable=False)  # Örn: "Sanayi AG - 3 Zamanlı"
    tariff_type = db.Column(db.String(50), default=TariffType.THREE_TIME.value)
    
    # Tarife Dilimleri (JSON)
    # Örn: {
    #   "T1": {"start": "06:00", "end": "17:00", "price": 2.50, "label": "Gündüz"},
    #   "T2": {"start": "17:00", "end": "22:00", "price": 4.80, "label": "Puant"},
    #   "T3": {"start": "22:00", "end": "06:00", "price": 1.10, "label": "Gece"}
    # }
    periods = db.Column(JSON, nullable=False)
    
    currency = db.Column(db.String(10), default="TRY")
    
    # Geçerlilik
    active_from = db.Column(db.DateTime, default=datetime.utcnow)
    active_until = db.Column(db.DateTime)  # NULL = süresiz
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişki
    user = db.relationship("User", backref="tariffs")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "tariff_type": self.tariff_type,
            "periods": self.periods,
            "currency": self.currency,
            "active_from": self.active_from.isoformat() if self.active_from else None,
            "active_until": self.active_until.isoformat() if self.active_until else None,
            "is_active": self.is_active,
        }


class EnergyMarketPrice(db.Model):
    """PTF/SMF Verileri (EPİAŞ Şeffaf Platform'dan çekilecek)."""
    __tablename__ = "energy_market_prices"
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Hangi gün ve saat?
    date = db.Column(db.Date, nullable=False, index=True)
    hour = db.Column(db.Integer, nullable=False)  # 0-23
    
    # Fiyatlar (TL/MWh)
    ptf = db.Column(db.Float)  # Piyasa Takas Fiyatı
    smf = db.Column(db.Float)  # Sistem Marjinal Fiyatı
    
    # Pozitif/Negatif Dengesizlik Fiyatları
    positive_imbalance = db.Column(db.Float)
    negative_imbalance = db.Column(db.Float)
    
    currency = db.Column(db.String(10), default="TRY")
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Unique constraint: Aynı gün+saat için tek kayıt
    __table_args__ = (
        db.UniqueConstraint('date', 'hour', name='unique_date_hour'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date.isoformat() if self.date else None,
            "hour": self.hour,
            "ptf": self.ptf,
            "smf": self.smf,
            "positive_imbalance": self.positive_imbalance,
            "negative_imbalance": self.negative_imbalance,
            "currency": self.currency,
        }


class VppRule(db.Model):
    """VPP Otomasyon Kuralları - Arbitraj ve Enerji Yönetimi."""
    __tablename__ = "vpp_rules"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    node_id = db.Column(db.Integer, db.ForeignKey("nodes.id"), nullable=False)  # Hangi Inverter?
    
    name = db.Column(db.String(100), nullable=False)  # Örn: "Puant Saatinde Deşarj Et"
    description = db.Column(db.String(255))
    
    is_active = db.Column(db.Boolean, default=True)
    
    # Tetikleyici Koşul (JSON)
    # Örn: {"type": "PRICE_THRESHOLD", "value": 4.0, "operator": ">", "source": "tariff"}
    # Örn: {"type": "TIME_RANGE", "start": "17:00", "end": "22:00", "days": [0,1,2,3,4]}
    # Örn: {"type": "SOC_THRESHOLD", "value": 80, "operator": "<"}
    trigger = db.Column(JSON, nullable=False)
    
    # Aksiyon (JSON)
    # Örn: {"type": "DISCHARGE_BATTERY", "power_limit_kw": 50, "target_soc": 20}
    # Örn: {"type": "CHARGE_BATTERY", "power_limit_kw": 30, "target_soc": 100}
    action = db.Column(JSON, nullable=False)
    
    # Öncelik (Çakışma olursa hangisi çalışsın?)
    priority = db.Column(db.Integer, default=1)
    
    # İstatistikler
    last_triggered_at = db.Column(db.DateTime)
    trigger_count = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişkiler
    user = db.relationship("User", backref="vpp_rules")
    node = db.relationship("Node", backref="vpp_rules")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "node_id": self.node_id,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "trigger": self.trigger,
            "action": self.action,
            "priority": self.priority,
            "last_triggered_at": self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            "trigger_count": self.trigger_count,
        }


class VppRuleLog(db.Model):
    """VPP Kural Çalışma Geçmişi - Audit Trail."""
    __tablename__ = "vpp_rule_logs"
    
    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey("vpp_rules.id"), nullable=False)
    
    # Ne zaman tetiklendi?
    triggered_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Tetikleme anındaki koşullar
    # Örn: {"price": 4.85, "soc": 85, "time": "17:30"}
    trigger_context = db.Column(JSON)
    
    # Gönderilen komut
    # Örn: {"command": "SET_BATTERY_MODE", "mode": "DISCHARGE", "power": 50}
    action_sent = db.Column(JSON)
    
    # Sonuç
    status = db.Column(db.String(20), default="PENDING")  # PENDING, SUCCESS, FAILED
    error_message = db.Column(db.String(255))
    
    # Komut ID (Command tablosuyla ilişki)
    command_id = db.Column(db.Integer, db.ForeignKey("commands.id"))

    # İlişki
    rule = db.relationship("VppRule", backref="logs")

    def to_dict(self):
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "trigger_context": self.trigger_context,
            "action_sent": self.action_sent,
            "status": self.status,
            "error_message": self.error_message,
        }


# ==========================================
# 7. AUTO-DISCOVERY (Otomatik Keşif) KATMANI
# ==========================================


class DiscoveryStatus(str, Enum):
    """Keşfedilen cihaz durumu."""
    PENDING = "PENDING"        # Onay bekliyor
    CLAIMED = "CLAIMED"        # Sahiplenildi (Node'a terfi etti)
    IGNORED = "IGNORED"        # Kullanıcı tarafından yoksayıldı
    EXPIRED = "EXPIRED"        # Zaman aşımına uğradı


class DiscoveryQueue(db.Model):
    """
    Henüz sahiplenilmemiş, başıboş cihazların havuzu (Araf Tablosu).
    
    Gateway bilinmeyen bir cihazdan sinyal aldığında buraya kaydeder.
    Kullanıcı onaylarsa Node tablosuna terfi eder.
    """
    __tablename__ = "discovery_queue"

    id = db.Column(db.Integer, primary_key=True)
    
    # Bu cihazı hangi Gateway (Device) duydu? 
    # Güvenlik için önemli: Sadece gateway sahibi görebilir
    reported_by_device_id = db.Column(
        db.Integer, 
        db.ForeignKey("devices.id"), 
        nullable=False,
        index=True
    )
    
    # Cihazın benzersiz kimliği (LoRa DevEUI, MAC, Modbus IP:SlaveID vb.)
    device_identifier = db.Column(db.String(100), nullable=False, index=True)
    
    # Haberleşme protokolü (LORA, MODBUS, ZIGBEE vb.)
    protocol = db.Column(db.String(30), default="UNKNOWN")
    
    # Tahmin edilen cihaz tipi (payload'dan çıkarılabilir)
    guessed_type = db.Column(db.String(50))  # SENSOR_NODE, INVERTER vb.
    
    # Tahmin edilen marka/model (Modbus cevabından)
    guessed_brand = db.Column(db.String(50))
    guessed_model = db.Column(db.String(100))
    
    # Ham veri (Cihazın ne olduğunu anlamak için ipucu)
    # Örn: {"rssi": -80, "payload": "temp=24", "ip": "192.168.1.50"}
    raw_data = db.Column(JSON, default=dict)
    
    # Sinyal gücü (varsa)
    signal_strength = db.Column(db.Float)
    # Gateway'e tahmini mesafe (metre)
    distance_estimate = db.Column(db.Float)
    
    # Durum
    status = db.Column(
        db.String(20), 
        default=DiscoveryStatus.PENDING.value,
        index=True
    )
    
    # Zaman damgaları
    first_seen_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Kaç kez görüldü (Güvenilirlik için)
    seen_count = db.Column(db.Integer, default=1)

    # İlişki
    reporter = db.relationship("Device", backref="discovered_devices")

    def to_dict(self):
        return {
            "id": self.id,
            "device_identifier": self.device_identifier,
            "protocol": self.protocol,
            "guessed_type": self.guessed_type,
            "guessed_brand": self.guessed_brand,
            "guessed_model": self.guessed_model,
            "signal_strength": self.signal_strength,
            "distance_estimate": self.distance_estimate,
            "status": self.status,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "seen_count": self.seen_count,
            "raw_data": self.raw_data or {},
            # Gateway bilgileri
            "gateway_id": self.reported_by_device_id,
            "gateway_name": self.reporter.name if self.reporter else None,
            "site_name": self.reporter.site.name if self.reporter and self.reporter.site else None,
        }
