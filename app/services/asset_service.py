"""SmartAsset iş mantığı - v6.0."""
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.extensions import db
from app.models import SmartAsset


def get_asset_for_org(asset_id: UUID, organization_id: UUID) -> Optional[SmartAsset]:
    """Organizasyona ait SmartAsset'i getir."""
    return SmartAsset.query.filter_by(
        id=asset_id,
        organization_id=organization_id,
        is_active=True
    ).first()


def create_asset_logic(organization_id: UUID, data: Dict[str, Any]) -> SmartAsset:
    """Yeni varlık oluştur."""
    if not data:
        raise ValueError("Asset data is required.")

    name = data.get("name")
    if not name:
        raise ValueError("Asset name is required.")

    asset = SmartAsset(
        organization_id=organization_id,
        device_id=data.get("device_id"),
        name=name,
        type=data.get("type", "other"),
        nominal_power_watt=data.get("nominal_power_watt", 0),
        priority=data.get("priority", 1),
        settings=data.get("settings", {}),
    )
    db.session.add(asset)
    db.session.commit()
    return asset


def update_asset_logic(organization_id: UUID, asset_id: UUID, data: Dict[str, Any]) -> SmartAsset:
    """Asset bilgilerini güncelle."""
    asset = get_asset_for_org(asset_id, organization_id)
    if not asset:
        raise ValueError("Asset not found or access denied.")

    if not data:
        return asset

    updatable_fields = [
        "name", "type", "nominal_power_watt", "priority", "device_id"
    ]

    for field in updatable_fields:
        if field in data:
            setattr(asset, field, data[field])

    if "settings" in data:
        asset.settings = data["settings"]

    db.session.commit()
    return asset


def delete_asset_logic(organization_id: UUID, asset_id: UUID) -> None:
    """Asset'i soft delete yap."""
    asset = get_asset_for_org(asset_id, organization_id)
    if not asset:
        raise ValueError("Asset not found or access denied.")

    asset.is_active = False
    db.session.commit()


def get_assets_by_organization(organization_id: UUID) -> List[SmartAsset]:
    """Organizasyona ait tüm asset'leri getir."""
    return SmartAsset.query.filter_by(
        organization_id=organization_id,
        is_active=True
    ).all()
