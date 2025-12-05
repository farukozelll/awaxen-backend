"""
Services Package - İş mantığı katmanı.

Bu paket, routes'tan çağrılan tüm iş mantığı fonksiyonlarını içerir.
Her modül kendi alanına ait işlemleri barındırır.
"""

# Site işlemleri
from .site_service import (
    create_site_logic,
    update_site_logic,
)

# Device işlemleri
from .device_service import (
    create_device_logic,
    update_device_logic,
    delete_device_logic,
    _get_device_for_user,
)

# Node işlemleri
from .node_service import (
    create_node_logic,
    update_node_logic,
    delete_node_logic,
    _get_node_for_user,
)

# Asset işlemleri
from .asset_service import (
    create_asset_logic,
    update_asset_logic,
    delete_asset_logic,
    get_assets_by_node,
    get_assets_by_site,
    get_site_hierarchy,
    _get_asset_for_user,
)

# Enum yardımcıları
from .enum_service import (
    get_site_types,
    get_device_statuses,
    get_node_protocols,
    get_asset_types,
    get_asset_categories,
    get_node_types,
    get_inverter_brands,
    get_tariff_types,
    get_vpp_trigger_types,
    get_vpp_action_types,
)

# Tarife işlemleri
from .tariff_service import (
    create_tariff_logic,
    update_tariff_logic,
    delete_tariff_logic,
    get_current_tariff_price,
)

# Piyasa fiyatları
from .market_service import (
    save_market_prices,
    get_market_prices_for_date,
    get_current_market_price,
)

# VPP işlemleri
from .vpp_service import (
    create_vpp_rule_logic,
    update_vpp_rule_logic,
    delete_vpp_rule_logic,
    get_vpp_rules_for_node,
    get_vpp_rule_logs,
    log_vpp_rule_execution,
    get_inverters_for_user,
    get_inverter_summary,
)

__all__ = [
    # Site
    "create_site_logic",
    "update_site_logic",
    # Device
    "create_device_logic",
    "update_device_logic",
    "delete_device_logic",
    "_get_device_for_user",
    # Node
    "create_node_logic",
    "update_node_logic",
    "delete_node_logic",
    "_get_node_for_user",
    # Asset
    "create_asset_logic",
    "update_asset_logic",
    "delete_asset_logic",
    "get_assets_by_node",
    "get_assets_by_site",
    "get_site_hierarchy",
    "_get_asset_for_user",
    # Enums
    "get_site_types",
    "get_device_statuses",
    "get_node_protocols",
    "get_asset_types",
    "get_asset_categories",
    "get_node_types",
    "get_inverter_brands",
    "get_tariff_types",
    "get_vpp_trigger_types",
    "get_vpp_action_types",
    # Tariff
    "create_tariff_logic",
    "update_tariff_logic",
    "delete_tariff_logic",
    "get_current_tariff_price",
    # Market
    "save_market_prices",
    "get_market_prices_for_date",
    "get_current_market_price",
    # VPP
    "create_vpp_rule_logic",
    "update_vpp_rule_logic",
    "delete_vpp_rule_logic",
    "get_vpp_rules_for_node",
    "get_vpp_rule_logs",
    "log_vpp_rule_execution",
    "get_inverters_for_user",
    "get_inverter_summary",
]
