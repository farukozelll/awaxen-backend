"""Integration provider metadata shared between API responses and UI."""

PROVIDER_CATALOG = {
    "shelly": {
        "provider": "shelly",
        "display_name": "Shelly Cloud",
        "tagline": "Control Shelly plugs, relays and sensors via cloud API.",
        "badge": None,
        "status_text": "Connected via Auth Key",
        "docs_url": "https://shelly-api-docs.shelly.cloud",
        "category": "devices",
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
}


def get_provider_meta(provider: str):
    """Return metadata for provider, if known."""
    return PROVIDER_CATALOG.get(provider, {})
