"""
Services Package - v6.0 SaaS İş Mantığı Katmanı.

Bu paket, routes'tan çağrılan tüm iş mantığı fonksiyonlarını içerir.
"""

# v6.0 Core Services
from .shelly_service import ShellyService, get_shelly_service
from .automation_engine import AutomationEngine, automation_engine, check_all_automations
from .market_service import (
    save_market_prices,
    get_market_prices_for_date,
    get_current_market_price,
    get_latest_price,
)

# Device işlemleri
from .device_service import (
    get_device_for_org,
    create_device_logic,
    update_device_logic,
    delete_device_logic,
)

# Asset işlemleri
from .asset_service import (
    get_asset_for_org,
    create_asset_logic,
    update_asset_logic,
    delete_asset_logic,
    get_assets_by_organization,
)

# EPİAŞ Entegrasyonu
from .epias_service import EpiasService, epias_service

__all__ = [
    # v6.0 Core
    "ShellyService",
    "get_shelly_service",
    "AutomationEngine",
    "automation_engine",
    "check_all_automations",
    # Market
    "save_market_prices",
    "get_market_prices_for_date",
    "get_current_market_price",
    "get_latest_price",
    # Device
    "get_device_for_org",
    "create_device_logic",
    "update_device_logic",
    "delete_device_logic",
    # Asset
    "get_asset_for_org",
    "create_asset_logic",
    "update_asset_logic",
    "delete_asset_logic",
    "get_assets_by_organization",
    # EPİAŞ
    "EpiasService",
    "epias_service",
]
