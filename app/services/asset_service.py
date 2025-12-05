"""Asset (Envanter/Sensör) iş mantığı."""
from typing import Any, Dict, List

from .. import db
from ..models import Asset, AssetCategory, AssetType, Device, Node, Site
from .node_service import _get_node_for_user


def _get_asset_for_user(asset_id: int, user_id: int) -> Asset:
    """Kullanıcıya ait Asset'i getir."""
    return (
        Asset.query.join(Node)
        .join(Device)
        .join(Site)
        .filter(Asset.id == asset_id, Site.user_id == user_id)
        .first()
    )


def create_asset_logic(user_id: int, data: Dict[str, Any]) -> Asset:
    """Bir Node'a sensör/vana (inventory) tanımla."""
    if not data:
        raise ValueError("Asset verisi gereklidir.")

    node = _get_node_for_user(data.get("node_id"), user_id)
    if not node:
        raise ValueError("Node bulunamadı veya yetkiniz yok.")

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
