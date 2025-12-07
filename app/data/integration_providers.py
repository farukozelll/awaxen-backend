"""Integration provider metadata shared between API responses and UI."""

# Shelly model -> device_type mapping
SHELLY_DEVICE_TYPES = {
    # Röleler (Relay)
    "SHSW-1": "relay",           # Shelly 1
    "SNSW-001X16EU": "relay",    # Shelly Plus 1
    "SHSW-PM": "relay",          # Shelly 1PM
    "SNSW-001P16EU": "relay",    # Shelly Plus 1PM
    "SHSW-25": "relay",          # Shelly 2.5 (Panjur)
    "SNSW-002P16EU": "relay",    # Shelly Plus 2PM
    
    # Prizler (Plug)
    "SHPLG-1": "plug",           # Shelly Plug
    "SHPLG-S": "plug",           # Shelly Plug S
    "SHPLG-EU": "plug",          # Shelly Plug EU
    "SNPL-00112EU": "plug",      # Shelly Plus Plug S
    
    # Enerji Ölçerler (Energy Meter)
    "SHEM": "energy_meter",      # Shelly EM
    "SHEM-3": "energy_meter",    # Shelly 3EM
    "SPEM-003CEBEU": "energy_meter",  # Shelly Pro 3EM
    
    # Sensörler
    "SHHT-1": "sensor",          # Shelly H&T (Nem/Sıcaklık)
    "SHMOS-01": "sensor",        # Shelly Motion
    "SHWT-1": "sensor",          # Shelly Flood (Su)
    "SHDW-1": "sensor",          # Shelly Door/Window
    "SHGS-1": "sensor",          # Shelly Gas
    "SHSM-01": "sensor",         # Shelly Smoke
    
    # Dimmerler
    "SHDM-1": "dimmer",          # Shelly Dimmer
    "SHDM-2": "dimmer",          # Shelly Dimmer 2
    "SNDM-0013US": "dimmer",     # Shelly Plus Wall Dimmer
    
    # RGBW
    "SHRGBW2": "rgbw",           # Shelly RGBW2
    "SHCB-1": "rgbw",            # Shelly Color Bulb
}


def get_shelly_device_type(model: str) -> str:
    """Shelly model kodundan device_type belirle."""
    if not model:
        return "unknown"
    
    # Tam eşleşme
    if model in SHELLY_DEVICE_TYPES:
        return SHELLY_DEVICE_TYPES[model]
    
    # Kısmi eşleşme (model kodu prefix olabilir)
    model_upper = model.upper()
    for prefix, dtype in SHELLY_DEVICE_TYPES.items():
        if model_upper.startswith(prefix):
            return dtype
    
    # Varsayılan: model adından tahmin
    model_lower = model.lower()
    if "em" in model_lower or "meter" in model_lower:
        return "energy_meter"
    if "plug" in model_lower:
        return "plug"
    if "dimmer" in model_lower:
        return "dimmer"
    if any(x in model_lower for x in ["ht", "motion", "flood", "door", "gas", "smoke"]):
        return "sensor"
    
    return "relay"  # Varsayılan


PROVIDER_CATALOG = {
    "shelly": {
        "provider": "shelly",
        "display_name": "Shelly Cloud",
        "tagline": "Control Shelly plugs, relays and sensors via cloud API.",
        "badge": None,
        "status_text": "Connected via Auth Key",
        "docs_url": "https://shelly-api-docs.shelly.cloud",
        "category": "devices",
        "supported_devices": [
            {"type": "relay", "name": "Shelly 1/1PM", "description": "Akıllı röle, lamba/kombi kontrolü"},
            {"type": "plug", "name": "Shelly Plug", "description": "Akıllı priz, enerji ölçümlü"},
            {"type": "energy_meter", "name": "Shelly EM/3EM", "description": "Profesyonel enerji analizörü"},
            {"type": "sensor", "name": "Shelly H&T/Motion", "description": "Nem, sıcaklık, hareket sensörleri"},
        ],
    },
    "amazon_alexa": {
        "provider": "amazon_alexa",
        "display_name": "Amazon Alexa",
        "tagline": "Easily control your devices with voice commands.",
        "badge": None,
        "status_text": "Not connected",
        "cta_label": "Configure",
        "category": "voice",
    },
    "zendure": {
        "provider": "zendure",
        "display_name": "Zendure",
        "tagline": "PV consumption monitoring and device management.",
        "badge": "ALPHA",
        "status_text": "Connect to monitor batteries and PV.",
        "cta_label": "Configure",
        "category": "energy",
    },
    "loqed": {
        "provider": "loqed",
        "display_name": "LOQED",
        "tagline": "Integrate your LOQED smart lock devices seamlessly.",
        "badge": "NEW",
        "status_text": "Bring door locks into your automations.",
        "cta_label": "Configure",
        "category": "security",
    },
    "tapo": {
        "provider": "tapo",
        "display_name": "TP-Link Tapo",
        "tagline": "Smart plugs and energy monitoring.",
        "badge": None,
        "status_text": "Cloud control via email/password.",
        "category": "devices",
    },
    "tesla": {
        "provider": "tesla",
        "display_name": "Tesla Energy",
        "tagline": "EVs and Powerwall fleet API.",
        "badge": None,
        "status_text": "OAuth based connection.",
        "category": "energy",
    },
    "tuya": {
        "provider": "tuya",
        "display_name": "Tuya / Smart Life",
        "tagline": "Connect Tuya-based smart devices via cloud.",
        "badge": None,
        "status_text": "Cloud API integration.",
        "docs_url": "https://developer.tuya.com",
        "category": "devices",
    },
    "sonoff": {
        "provider": "sonoff",
        "display_name": "Sonoff eWeLink",
        "tagline": "Control Sonoff WiFi switches and sensors.",
        "badge": None,
        "status_text": "eWeLink cloud connection.",
        "category": "devices",
    },
    "aqara": {
        "provider": "aqara",
        "display_name": "Aqara Home",
        "tagline": "Zigbee sensors and smart home devices.",
        "badge": None,
        "status_text": "Aqara cloud or local hub.",
        "category": "devices",
    },
    "google_home": {
        "provider": "google_home",
        "display_name": "Google Home",
        "tagline": "Voice control via Google Assistant.",
        "badge": None,
        "status_text": "Not connected",
        "category": "voice",
    },
    "homeassistant": {
        "provider": "homeassistant",
        "display_name": "Home Assistant",
        "tagline": "Connect to your local Home Assistant instance.",
        "badge": "PRO",
        "status_text": "Local API connection.",
        "category": "hub",
    },
}


# Gateway tipi metadata
GATEWAY_TYPES = {
    "teltonika": {
        "type": "teltonika",
        "display_name": "Teltonika RUT956",
        "description": "Endüstriyel 4G router, MQTT ve Modbus desteği.",
        "connection_method": "mqtt",
        "setup_guide": "Teltonika cihazına Awaxen MQTT script'i yüklenmeli.",
    },
    "raspberry_pi": {
        "type": "raspberry_pi",
        "display_name": "Raspberry Pi",
        "description": "Awaxen Gateway OS ile çalışan mini bilgisayar.",
        "connection_method": "mqtt",
        "setup_guide": "Awaxen Gateway imajını SD karta yazın ve başlatın.",
    },
    "shelly_pro": {
        "type": "shelly_pro",
        "display_name": "Shelly Pro (DIN Rail)",
        "description": "Shelly Pro serisi, yerel MQTT gateway olarak kullanılabilir.",
        "connection_method": "mqtt",
        "setup_guide": "Shelly Pro cihazını MQTT moduna alın.",
    },
    "custom": {
        "type": "custom",
        "display_name": "Özel Gateway",
        "description": "Kendi geliştirdiğiniz MQTT uyumlu gateway.",
        "connection_method": "mqtt",
        "setup_guide": "MQTT broker bilgilerini girin.",
    },
}


def get_provider_meta(provider: str):
    """Return metadata for provider, if known."""
    return PROVIDER_CATALOG.get(provider, {})


def get_gateway_type_meta(gateway_type: str):
    """Return metadata for gateway type, if known."""
    return GATEWAY_TYPES.get(gateway_type, {})
