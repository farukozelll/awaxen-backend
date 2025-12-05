"""Enum endpoint'leri (Frontend için seçenekler)."""
from flask import jsonify

from . import api_bp
from ..services import (
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


@api_bp.route('/enums/site-types', methods=['GET'])
def get_site_type_options():
    """
    Mevcut saha tiplerini listele.
    ---
    tags:
      - Enum
    responses:
      200:
        description: Saha tipleri listesi
    """
    return jsonify(get_site_types())


@api_bp.route('/enums/device-statuses', methods=['GET'])
def get_device_status_options():
    """
    Mevcut cihaz durumlarını listele.
    ---
    tags:
      - Enum
    responses:
      200:
        description: Cihaz durumları listesi
    """
    return jsonify(get_device_statuses())


@api_bp.route('/enums/node-protocols', methods=['GET'])
def get_node_protocol_options():
    """
    Mevcut node protokollerini listele.
    ---
    tags:
      - Enum
    responses:
      200:
        description: Node protokolleri listesi
    """
    return jsonify(get_node_protocols())


@api_bp.route('/enums/asset-types', methods=['GET'])
def get_asset_type_options():
    """
    Mevcut asset tiplerini listele.
    ---
    tags:
      - Enum
    responses:
      200:
        description: Asset tipleri listesi
    """
    return jsonify(get_asset_types())


@api_bp.route('/enums/asset-categories', methods=['GET'])
def get_asset_category_options():
    """
    Mevcut asset kategorilerini listele.
    ---
    tags:
      - Enum
    responses:
      200:
        description: Asset kategorileri listesi
    """
    return jsonify(get_asset_categories())


@api_bp.route('/enums', methods=['GET'])
def get_all_enums():
    """
    Tüm enum değerlerini tek seferde getir.
    ---
    tags:
      - Enum
    responses:
      200:
        description: Tüm enum değerleri
    """
    return jsonify({
        "site_types": get_site_types(),
        "device_statuses": get_device_statuses(),
        "node_protocols": get_node_protocols(),
        "asset_types": get_asset_types(),
        "asset_categories": get_asset_categories(),
    })


# VPP Enum'ları
@api_bp.route('/enums/node-types', methods=['GET'])
def get_node_type_options():
    """Node tiplerini listele."""
    return jsonify(get_node_types())


@api_bp.route('/enums/inverter-brands', methods=['GET'])
def get_inverter_brand_options():
    """Inverter markalarını listele."""
    return jsonify(get_inverter_brands())


@api_bp.route('/enums/tariff-types', methods=['GET'])
def get_tariff_type_options():
    """Tarife tiplerini listele."""
    return jsonify(get_tariff_types())


@api_bp.route('/enums/vpp-triggers', methods=['GET'])
def get_vpp_trigger_options():
    """VPP tetikleyici tiplerini listele."""
    return jsonify(get_vpp_trigger_types())


@api_bp.route('/enums/vpp-actions', methods=['GET'])
def get_vpp_action_options():
    """VPP aksiyon tiplerini listele."""
    return jsonify(get_vpp_action_types())
