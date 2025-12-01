"""Business logic helpers to keep routes.py lean."""
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from . import db
from .models import (
    Asset,
    AssetCategory,
    AssetType,
    Device,
    DeviceStatus,
    Node,
    NodeProtocol,
    NodeType,
    InverterBrand,
    Site,
    SiteType,
    # VPP modelleri
    Tariff,
    TariffType,
    EnergyMarketPrice,
    VppRule,
    VppRuleLog,
    VppTriggerType,
    VppActionType,
)


# ==========================================
# YARDIMCI FONKSİYONLAR
# ==========================================


def _resolve_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    metadata = payload.get("metadata_info")
    if metadata is None:
        metadata = payload.get("metadata")
    return metadata or {}


def _get_device_for_user(device_id: int, user_id: int) -> Device:
    return (
        Device.query.join(Site)
        .filter(Device.id == device_id, Site.user_id == user_id)
        .first()
    )


def _get_node_for_user(node_id: int, user_id: int) -> Node:
    """Kullanıcıya ait Node'u getir."""
    return (
        Node.query.join(Device)
        .join(Site)
        .filter(Node.id == node_id, Site.user_id == user_id)
        .first()
    )


def _get_asset_for_user(asset_id: int, user_id: int) -> Asset:
    """Kullanıcıya ait Asset'i getir."""
    return (
        Asset.query.join(Node)
        .join(Device)
        .join(Site)
        .filter(Asset.id == asset_id, Site.user_id == user_id)
        .first()
    )


# ==========================================
# ENUM YARDIMCILARI
# ==========================================


def get_site_types() -> List[Dict[str, str]]:
    """Mevcut site tiplerini döndür."""
    return [
        {"value": t.value, "label": _get_site_type_label(t.value)}
        for t in SiteType
    ]


def _get_site_type_label(value: str) -> str:
    """Site tipi için Türkçe etiket."""
    labels = {
        "GREENHOUSE": "Sera",
        "FIELD": "Açık Tarla",
        "SOLAR_PLANT": "Güneş Santrali",
        "FACTORY": "Fabrika",
        "WAREHOUSE": "Depo",
        "OTHER": "Diğer",
    }
    return labels.get(value, value)


def get_device_statuses() -> List[Dict[str, str]]:
    """Mevcut cihaz durumlarını döndür."""
    labels = {
        "ONLINE": "Çevrimiçi",
        "OFFLINE": "Çevrimdışı",
        "MAINTENANCE": "Bakımda",
        "ERROR": "Arızalı",
        "UNKNOWN": "Bilinmiyor",
    }
    return [{"value": s.value, "label": labels.get(s.value, s.value)} for s in DeviceStatus]


def get_node_protocols() -> List[Dict[str, str]]:
    """Mevcut node protokollerini döndür."""
    labels = {
        "LORA": "LoRaWAN",
        "ZIGBEE": "ZigBee",
        "WIFI": "WiFi",
        "WIRED": "Kablolu",
        "MODBUS": "Modbus",
        "OTHER": "Diğer",
    }
    return [{"value": p.value, "label": labels.get(p.value, p.value)} for p in NodeProtocol]


def get_asset_types() -> List[Dict[str, str]]:
    """Mevcut asset tiplerini döndür."""
    labels = {
        "SENSOR": "Sensör",
        "ACTUATOR": "Aktüatör",
        "METER": "Sayaç",
        "CONTROLLER": "Kontrolcü",
    }
    return [{"value": t.value, "label": labels.get(t.value, t.value)} for t in AssetType]


def get_asset_categories() -> List[Dict[str, str]]:
    """Mevcut asset kategorilerini döndür."""
    labels = {
        "TEMPERATURE": "Sıcaklık",
        "HUMIDITY": "Nem",
        "SOIL_MOISTURE": "Toprak Nemi",
        "LIGHT": "Işık",
        "CO2": "Karbondioksit",
        "PH": "pH",
        "EC": "Elektriksel İletkenlik",
        "PRESSURE": "Basınç",
        "FLOW": "Akış",
        "LEVEL": "Seviye",
        "VALVE": "Vana",
        "PUMP": "Pompa",
        "RELAY": "Röle",
        "MOTOR": "Motor",
        "HEATER": "Isıtıcı",
        "FAN": "Fan",
        "LIGHT_CONTROL": "Aydınlatma",
        "ENERGY_METER": "Enerji Sayacı",
        "WATER_METER": "Su Sayacı",
        "OTHER": "Diğer",
    }
    return [{"value": c.value, "label": labels.get(c.value, c.value)} for c in AssetCategory]


# ==========================================
# SITE (SAHA) İŞLEMLERİ
# ==========================================


def create_site_logic(user_id: int, data: Dict[str, Any]) -> Site:
    """Yeni saha oluştur (tipli ve boyutlu)."""
    if not data:
        raise ValueError("Saha verisi gereklidir.")

    name = data.get("name")
    if not name:
        raise ValueError("Saha adı zorunludur.")

    site_type = data.get("site_type", SiteType.GREENHOUSE.value)
    dimensions = data.get("dimensions", {})

    # Validasyon: Sera seçildiyse boyut girmek zorunlu olsun
    if site_type == SiteType.GREENHOUSE.value:
        if dimensions and ("rows" in dimensions or "columns" in dimensions):
            # En az biri varsa ikisi de olmalı
            if "rows" not in dimensions or "columns" not in dimensions:
                raise ValueError("Sera tipi için hem satır hem sütun sayısı girilmelidir.")

    site = Site(
        user_id=user_id,
        name=name,
        city=data.get("city"),
        district=data.get("district"),
        location=data.get("location"),
        address=data.get("address"),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        site_type=site_type,
        dimensions=dimensions,
        image_url=data.get("image_url"),
        metadata_info=_resolve_metadata(data),
    )
    db.session.add(site)
    db.session.commit()
    return site


def update_site_logic(user_id: int, site_id: int, data: Dict[str, Any]) -> Site:
    """Saha bilgilerini güncelle."""
    site = Site.query.filter_by(id=site_id, user_id=user_id).first()
    if not site:
        raise ValueError("Saha bulunamadı veya yetkiniz yok.")

    if not data:
        return site

    # Güncellenebilir alanlar
    updatable_fields = [
        "name", "city", "district", "location", "address",
        "latitude", "longitude", "site_type", "dimensions", "image_url"
    ]

    for field in updatable_fields:
        if field in data and data[field] is not None:
            setattr(site, field, data[field])

    if "metadata" in data or "metadata_info" in data:
        site.metadata_info = _resolve_metadata(data)

    db.session.commit()
    return site


def create_device_logic(user_id: int, data: Dict[str, Any]) -> Device:
    if not data:
        raise ValueError("Cihaz verisi gereklidir.")

    site = Site.query.filter_by(id=data.get("site_id"), user_id=user_id).first()
    if not site:
        raise ValueError("Bu saha sizin değil veya bulunamadı.")

    device = Device(
        site_id=site.id,
        serial_number=data.get("serial_number"),
        name=data.get("name"),
        model=data.get("model"),
        firmware_version=data.get("firmware_version"),
        metadata_info=_resolve_metadata(data),
        is_online=data.get("is_online", False),
    )
    db.session.add(device)
    db.session.commit()
    return device


def update_device_logic(user_id: int, device_id: int, data: Dict[str, Any]) -> Device:
    device = _get_device_for_user(device_id, user_id)
    if not device:
        raise ValueError("Cihaz bulunamadı veya yetkiniz yok.")

    if not data:
        return device

    updatable_fields = (
        "name",
        "serial_number",
        "model",
        "firmware_version",
        "status",
        "ip_address",
        "mac_address",
    )

    for field in updatable_fields:
        if field in data and data[field] is not None:
            setattr(device, field, data[field])

    if "last_seen" in data:
        last_seen_val = data["last_seen"]
        if isinstance(last_seen_val, str):
            try:
                last_seen_val = datetime.fromisoformat(last_seen_val.replace("Z", "+00:00"))
            except ValueError:
                last_seen_val = None
        device.last_seen = last_seen_val

    if "is_online" in data:
        device.is_online = bool(data["is_online"])

    if "metadata" in data or "metadata_info" in data:
        device.metadata_info = _resolve_metadata(data)

    db.session.commit()
    return device


def delete_device_logic(user_id: int, device_id: int) -> None:
    device = _get_device_for_user(device_id, user_id)
    if not device:
        raise ValueError("Cihaz bulunamadı veya yetkiniz yok.")

    db.session.delete(device)
    db.session.commit()


# ==========================================
# NODE İŞLEMLERİ
# ==========================================


def create_node_logic(user_id: int, data: Dict[str, Any]) -> Node:
    """Yeni node oluştur."""
    if not data:
        raise ValueError("Node verisi gereklidir.")

    device = _get_device_for_user(data.get("device_id"), user_id)
    if not device:
        raise ValueError("Cihaz bulunamadı veya yetkiniz yok.")

    node = Node(
        device_id=device.id,
        name=data.get("name"),
        node_type=data.get("node_type", "SENSOR"),
        protocol=data.get("protocol", NodeProtocol.LORA.value),
        node_address=data.get("node_address"),
        battery_level=data.get("battery_level"),
        signal_strength=data.get("signal_strength"),
        configuration=data.get("configuration", {}),
    )
    db.session.add(node)
    db.session.commit()
    return node


def update_node_logic(user_id: int, node_id: int, data: Dict[str, Any]) -> Node:
    """Node bilgilerini güncelle."""
    node = _get_node_for_user(node_id, user_id)
    if not node:
        raise ValueError("Node bulunamadı veya yetkiniz yok.")

    if not data:
        return node

    updatable_fields = [
        "name",
        "node_type",
        "protocol",
        "node_address",
        "battery_level",
        "signal_strength",
        "configuration",
        "brand",
        "model_number",
        "capacity_info",
    ]

    for field in updatable_fields:
        if field in data:
            setattr(node, field, data[field])

    if "last_seen" in data:
        last_seen_val = data["last_seen"]
        if isinstance(last_seen_val, str):
            try:
                last_seen_val = datetime.fromisoformat(last_seen_val.replace("Z", "+00:00"))
            except ValueError:
                last_seen_val = None
        node.last_seen = last_seen_val

    db.session.commit()
    return node


def delete_node_logic(user_id: int, node_id: int) -> None:
    """Node'u sil."""
    node = _get_node_for_user(node_id, user_id)
    if not node:
        raise ValueError("Node bulunamadı veya yetkiniz yok.")

    db.session.delete(node)
    db.session.commit()


# ==========================================
# ASSET (INVENTORY) İŞLEMLERİ
# ==========================================


def create_asset_logic(user_id: int, data: Dict[str, Any]) -> Asset:
    """Bir Node'a sensör/vana (inventory) tanımla."""
    if not data:
        raise ValueError("Asset verisi gereklidir.")

    node = _get_node_for_user(data.get("node_id"), user_id)
    if not node:
        raise ValueError("Node bulunamadı veya yetkiniz yok.")

    # Zorunlu alan kontrolü
    variable_name = data.get("variable_name")
    if not variable_name:
        raise ValueError("variable_name (MQTT key) zorunludur.")

    name = data.get("name")
    if not name:
        raise ValueError("Asset adı zorunludur.")

    asset = Asset(
        node_id=node.id,
        name=name,
        description=data.get("description"),
        asset_type=data.get("asset_type", AssetType.SENSOR.value),
        category=data.get("category", AssetCategory.OTHER.value),
        variable_name=variable_name,
        port_number=data.get("port_number"),
        unit=data.get("unit"),
        min_value=data.get("min_value"),
        max_value=data.get("max_value"),
        calibration_offset=data.get("calibration_offset", 0),
        position=data.get("position", {}),
        configuration=data.get("configuration", {}),
        is_active=data.get("is_active", True),
    )
    db.session.add(asset)
    db.session.commit()
    return asset


def update_asset_logic(user_id: int, asset_id: int, data: Dict[str, Any]) -> Asset:
    """Asset bilgilerini güncelle."""
    asset = _get_asset_for_user(asset_id, user_id)
    if not asset:
        raise ValueError("Asset bulunamadı veya yetkiniz yok.")

    if not data:
        return asset

    updatable_fields = [
        "name", "description", "asset_type", "category", "variable_name",
        "port_number", "unit", "min_value", "max_value", "calibration_offset",
        "position", "configuration", "is_active"
    ]

    for field in updatable_fields:
        if field in data:
            setattr(asset, field, data[field])

    db.session.commit()
    return asset


def delete_asset_logic(user_id: int, asset_id: int) -> None:
    """Asset'i sil."""
    asset = _get_asset_for_user(asset_id, user_id)
    if not asset:
        raise ValueError("Asset bulunamadı veya yetkiniz yok.")

    db.session.delete(asset)
    db.session.commit()


def get_assets_by_node(user_id: int, node_id: int) -> List[Asset]:
    """Bir Node'a ait tüm asset'leri getir."""
    node = _get_node_for_user(node_id, user_id)
    if not node:
        raise ValueError("Node bulunamadı veya yetkiniz yok.")

    return Asset.query.filter_by(node_id=node_id).all()


def get_assets_by_site(user_id: int, site_id: int) -> List[Dict[str, Any]]:
    """Bir Site'a ait tüm asset'leri hiyerarşik olarak getir."""
    site = Site.query.filter_by(id=site_id, user_id=user_id).first()
    if not site:
        raise ValueError("Saha bulunamadı veya yetkiniz yok.")

    result = []
    for device in site.devices:
        for node in device.nodes:
            for asset in node.assets:
                result.append({
                    **asset.to_dict(),
                    "node_name": node.name,
                    "device_name": device.name,
                    "device_serial": device.serial_number,
                })
    return result


# ==========================================
# DASHBOARD VE DETAYLI VERİ İŞLEMLERİ
# ==========================================


def get_site_hierarchy(user_id: int, site_id: int) -> Dict[str, Any]:
    """Site'ın tam hiyerarşisini getir (Device -> Node -> Asset)."""
    site = Site.query.filter_by(id=site_id, user_id=user_id).first()
    if not site:
        raise ValueError("Saha bulunamadı veya yetkiniz yok.")

    return {
        **site.to_dict(),
        "devices": [
            {
                **device.to_dict(),
                "nodes": [
                    {
                        **node.to_dict(),
                        "assets": [asset.to_dict() for asset in node.assets]
                    }
                    for node in device.nodes
                ]
            }
            for device in site.devices
        ]
    }


# ==========================================
# ENUM YARDIMCILARI (VPP)
# ==========================================


def get_node_types() -> List[Dict[str, str]]:
    """Node tiplerini label ile döndür."""
    labels = {
        NodeType.SENSOR_NODE: "Sensör Kutusu",
        NodeType.INVERTER: "Solar Inverter",
        NodeType.PLC: "PLC Kontrolcü",
        NodeType.ENERGY_METER: "Enerji Sayacı",
        NodeType.EV_CHARGER: "EV Şarj İstasyonu",
        NodeType.BATTERY_STORAGE: "Batarya Depolama",
        NodeType.OTHER: "Diğer",
    }
    return [{"value": t.value, "label": labels.get(t, t.value)} for t in NodeType]


def get_inverter_brands() -> List[Dict[str, str]]:
    """Inverter markalarını döndür."""
    return [{"value": b.value, "label": b.value} for b in InverterBrand]


def get_tariff_types() -> List[Dict[str, str]]:
    """Tarife tiplerini label ile döndür."""
    labels = {
        TariffType.SINGLE_TIME: "Tek Zamanlı",
        TariffType.THREE_TIME: "Üç Zamanlı (Gündüz/Puant/Gece)",
        TariffType.HOURLY: "Saatlik (PTF/SMF)",
    }
    return [{"value": t.value, "label": labels.get(t, t.value)} for t in TariffType]


def get_vpp_trigger_types() -> List[Dict[str, str]]:
    """VPP tetikleyici tiplerini döndür."""
    labels = {
        VppTriggerType.PRICE_THRESHOLD: "Fiyat Eşiği",
        VppTriggerType.TIME_RANGE: "Zaman Aralığı",
        VppTriggerType.SOC_THRESHOLD: "Batarya Doluluk Eşiği",
        VppTriggerType.GRID_DEMAND: "Şebeke Talep Sinyali",
        VppTriggerType.WEATHER: "Hava Durumu",
    }
    return [{"value": t.value, "label": labels.get(t, t.value)} for t in VppTriggerType]


def get_vpp_action_types() -> List[Dict[str, str]]:
    """VPP aksiyon tiplerini döndür."""
    labels = {
        VppActionType.CHARGE_BATTERY: "Bataryayı Şarj Et",
        VppActionType.DISCHARGE_BATTERY: "Bataryayı Deşarj Et",
        VppActionType.LIMIT_EXPORT: "Şebekeye Vermeyi Sınırla",
        VppActionType.LIMIT_IMPORT: "Şebekeden Çekmeyi Sınırla",
        VppActionType.SET_POWER: "Güç Seviyesi Ayarla",
    }
    return [{"value": t.value, "label": labels.get(t, t.value)} for t in VppActionType]


# ==========================================
# TARİFE İŞLEMLERİ
# ==========================================


def create_tariff_logic(user_id: int, data: Dict[str, Any]) -> Tariff:
    """Yeni tarife oluştur."""
    name = data.get("name", "").strip()
    if not name:
        raise ValueError("Tarife adı zorunludur.")
    
    periods = data.get("periods")
    if not periods:
        raise ValueError("Tarife dilimleri (periods) zorunludur.")
    
    tariff = Tariff(
        user_id=user_id,
        name=name,
        tariff_type=data.get("tariff_type", TariffType.THREE_TIME.value),
        periods=periods,
        currency=data.get("currency", "TRY"),
        is_active=data.get("is_active", True),
    )
    
    db.session.add(tariff)
    db.session.commit()
    return tariff


def update_tariff_logic(user_id: int, tariff_id: int, data: Dict[str, Any]) -> Tariff:
    """Tarife güncelle."""
    tariff = Tariff.query.filter_by(id=tariff_id, user_id=user_id).first()
    if not tariff:
        raise ValueError("Tarife bulunamadı veya yetkiniz yok.")
    
    if "name" in data:
        tariff.name = data["name"]
    if "tariff_type" in data:
        tariff.tariff_type = data["tariff_type"]
    if "periods" in data:
        tariff.periods = data["periods"]
    if "currency" in data:
        tariff.currency = data["currency"]
    if "is_active" in data:
        tariff.is_active = data["is_active"]
    
    db.session.commit()
    return tariff


def delete_tariff_logic(user_id: int, tariff_id: int) -> None:
    """Tarife sil."""
    tariff = Tariff.query.filter_by(id=tariff_id, user_id=user_id).first()
    if not tariff:
        raise ValueError("Tarife bulunamadı veya yetkiniz yok.")
    
    db.session.delete(tariff)
    db.session.commit()


def get_current_tariff_price(user_id: int, tariff_id: int) -> Dict[str, Any]:
    """Şu anki tarife fiyatını hesapla."""
    tariff = Tariff.query.filter_by(id=tariff_id, user_id=user_id, is_active=True).first()
    if not tariff:
        raise ValueError("Aktif tarife bulunamadı.")
    
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    
    current_period = None
    current_price = None
    
    for period_key, period_data in tariff.periods.items():
        start = period_data.get("start", "00:00")
        end = period_data.get("end", "23:59")
        
        # Gece geçişi kontrolü (22:00 - 06:00 gibi)
        if start > end:
            if current_time >= start or current_time < end:
                current_period = period_key
                current_price = period_data.get("price")
                break
        else:
            if start <= current_time < end:
                current_period = period_key
                current_price = period_data.get("price")
                break
    
    return {
        "tariff_id": tariff.id,
        "tariff_name": tariff.name,
        "current_period": current_period,
        "current_price": current_price,
        "currency": tariff.currency,
        "checked_at": now.isoformat(),
    }


# ==========================================
# ENERJİ PİYASASI FİYATLARI (EPİAŞ)
# ==========================================


def save_market_prices(prices: List[Dict[str, Any]]) -> int:
    """EPİAŞ'tan çekilen fiyatları kaydet."""
    saved_count = 0
    
    for price_data in prices:
        price_date = price_data.get("date")
        hour = price_data.get("hour")
        
        if isinstance(price_date, str):
            price_date = datetime.strptime(price_date, "%Y-%m-%d").date()
        
        # Upsert mantığı
        existing = EnergyMarketPrice.query.filter_by(date=price_date, hour=hour).first()
        
        if existing:
            existing.ptf = price_data.get("ptf")
            existing.smf = price_data.get("smf")
            existing.positive_imbalance = price_data.get("positive_imbalance")
            existing.negative_imbalance = price_data.get("negative_imbalance")
        else:
            new_price = EnergyMarketPrice(
                date=price_date,
                hour=hour,
                ptf=price_data.get("ptf"),
                smf=price_data.get("smf"),
                positive_imbalance=price_data.get("positive_imbalance"),
                negative_imbalance=price_data.get("negative_imbalance"),
            )
            db.session.add(new_price)
            saved_count += 1
    
    db.session.commit()
    return saved_count


def get_market_prices_for_date(target_date: date) -> List[Dict[str, Any]]:
    """Belirli bir gün için piyasa fiyatlarını getir."""
    prices = EnergyMarketPrice.query.filter_by(date=target_date).order_by(EnergyMarketPrice.hour).all()
    return [p.to_dict() for p in prices]


def get_current_market_price() -> Optional[Dict[str, Any]]:
    """Şu anki saatin piyasa fiyatını getir."""
    now = datetime.now()
    price = EnergyMarketPrice.query.filter_by(date=now.date(), hour=now.hour).first()
    return price.to_dict() if price else None


# ==========================================
# VPP KURAL İŞLEMLERİ
# ==========================================


def create_vpp_rule_logic(user_id: int, data: Dict[str, Any]) -> VppRule:
    """Yeni VPP kuralı oluştur."""
    name = data.get("name", "").strip()
    if not name:
        raise ValueError("Kural adı zorunludur.")
    
    node_id = data.get("node_id")
    if not node_id:
        raise ValueError("Node ID zorunludur.")
    
    # Node'un kullanıcıya ait olduğunu ve Inverter olduğunu kontrol et
    node = _get_node_for_user(node_id, user_id)
    if not node:
        raise ValueError("Node bulunamadı veya yetkiniz yok.")
    
    if node.node_type != NodeType.INVERTER.value:
        raise ValueError("VPP kuralları sadece Inverter tipi node'lara uygulanabilir.")
    
    trigger = data.get("trigger")
    if not trigger:
        raise ValueError("Tetikleyici koşul (trigger) zorunludur.")
    
    action = data.get("action")
    if not action:
        raise ValueError("Aksiyon zorunludur.")
    
    rule = VppRule(
        user_id=user_id,
        node_id=node_id,
        name=name,
        description=data.get("description"),
        trigger=trigger,
        action=action,
        priority=data.get("priority", 1),
        is_active=data.get("is_active", True),
    )
    
    db.session.add(rule)
    db.session.commit()
    return rule


def update_vpp_rule_logic(user_id: int, rule_id: int, data: Dict[str, Any]) -> VppRule:
    """VPP kuralını güncelle."""
    rule = VppRule.query.filter_by(id=rule_id, user_id=user_id).first()
    if not rule:
        raise ValueError("Kural bulunamadı veya yetkiniz yok.")
    
    if "name" in data:
        rule.name = data["name"]
    if "description" in data:
        rule.description = data["description"]
    if "trigger" in data:
        rule.trigger = data["trigger"]
    if "action" in data:
        rule.action = data["action"]
    if "priority" in data:
        rule.priority = data["priority"]
    if "is_active" in data:
        rule.is_active = data["is_active"]
    
    db.session.commit()
    return rule


def delete_vpp_rule_logic(user_id: int, rule_id: int) -> None:
    """VPP kuralını sil."""
    rule = VppRule.query.filter_by(id=rule_id, user_id=user_id).first()
    if not rule:
        raise ValueError("Kural bulunamadı veya yetkiniz yok.")
    
    db.session.delete(rule)
    db.session.commit()


def get_vpp_rules_for_node(user_id: int, node_id: int) -> List[VppRule]:
    """Bir Node'a ait VPP kurallarını getir."""
    node = _get_node_for_user(node_id, user_id)
    if not node:
        raise ValueError("Node bulunamadı veya yetkiniz yok.")
    
    return VppRule.query.filter_by(node_id=node_id, user_id=user_id).order_by(VppRule.priority).all()


def log_vpp_rule_execution(
    rule_id: int,
    trigger_context: Dict[str, Any],
    action_sent: Dict[str, Any],
    status: str = "PENDING",
    command_id: Optional[int] = None,
    error_message: Optional[str] = None
) -> VppRuleLog:
    """VPP kural çalışmasını logla."""
    log = VppRuleLog(
        rule_id=rule_id,
        trigger_context=trigger_context,
        action_sent=action_sent,
        status=status,
        command_id=command_id,
        error_message=error_message,
    )
    
    # Kuralın istatistiklerini güncelle
    rule = VppRule.query.get(rule_id)
    if rule:
        rule.last_triggered_at = datetime.utcnow()
        rule.trigger_count = (rule.trigger_count or 0) + 1
    
    db.session.add(log)
    db.session.commit()
    return log


def get_vpp_rule_logs(user_id: int, rule_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """VPP kuralının çalışma geçmişini getir."""
    rule = VppRule.query.filter_by(id=rule_id, user_id=user_id).first()
    if not rule:
        raise ValueError("Kural bulunamadı veya yetkiniz yok.")
    
    logs = (
        VppRuleLog.query
        .filter_by(rule_id=rule_id)
        .order_by(VppRuleLog.triggered_at.desc())
        .limit(limit)
        .all()
    )
    return [log.to_dict() for log in logs]


# ==========================================
# INVERTER İŞLEMLERİ
# ==========================================


def get_inverters_for_user(user_id: int) -> List[Node]:
    """Kullanıcının tüm inverter'larını getir."""
    return (
        Node.query
        .join(Device)
        .join(Site)
        .filter(
            Site.user_id == user_id,
            Node.node_type == NodeType.INVERTER.value
        )
        .all()
    )


def get_inverter_summary(user_id: int) -> Dict[str, Any]:
    """Kullanıcının inverter özetini getir (VPP Dashboard için)."""
    inverters = get_inverters_for_user(user_id)
    
    total_capacity_kw = 0
    total_battery_kwh = 0
    online_count = 0
    
    for inv in inverters:
        capacity = inv.capacity_info or {}
        total_capacity_kw += capacity.get("max_power_kw", 0)
        total_battery_kwh += capacity.get("battery_capacity_kwh", 0)
        
        # Device durumunu kontrol et
        if inv.device.status == DeviceStatus.ONLINE.value:
            online_count += 1
    
    return {
        "total_inverters": len(inverters),
        "online_inverters": online_count,
        "total_capacity_kw": total_capacity_kw,
        "total_battery_kwh": total_battery_kwh,
        "inverters": [
            {
                **inv.to_dict(),
                "site_name": inv.device.site.name,
                "device_name": inv.device.name,
                "device_status": inv.device.status,
            }
            for inv in inverters
        ]
    }
