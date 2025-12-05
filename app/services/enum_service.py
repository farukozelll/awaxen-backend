"""Enum yardımcı fonksiyonları."""
from typing import Dict, List

from ..models import (
    AssetCategory,
    AssetType,
    DeviceStatus,
    InverterBrand,
    NodeProtocol,
    NodeType,
    SiteType,
    TariffType,
    VppActionType,
    VppTriggerType,
)


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
