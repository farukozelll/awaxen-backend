"""SmartDevice iş mantığı - v6.0."""
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from app.extensions import db
from app.models import SmartDevice


def get_device_for_org(device_id: UUID, organization_id: UUID) -> Optional[SmartDevice]:
    """Organizasyona ait SmartDevice'ı getir."""
    return SmartDevice.query.filter_by(
        id=device_id,
        organization_id=organization_id,
        is_active=True
    ).first()


def create_device_logic(organization_id: UUID, data: Dict[str, Any]) -> SmartDevice:
    """Yeni akıllı cihaz oluştur."""
    if not data:
        raise ValueError("Device data is required.")

    device = SmartDevice(
        organization_id=organization_id,
        integration_id=data.get("integration_id"),
        gateway_id=data.get("gateway_id"),
        external_id=data.get("external_id"),
        name=data.get("name"),
        device_type=data.get("device_type", "relay"),
        brand=data.get("brand"),
        model=data.get("model"),
        is_sensor=data.get("is_sensor", False),
        is_actuator=data.get("is_actuator", True),
        settings=data.get("settings", {}),
    )
    db.session.add(device)
    db.session.commit()
    return device


def update_device_logic(organization_id: UUID, device_id: UUID, data: Dict[str, Any]) -> SmartDevice:
    """Cihaz bilgilerini güncelle."""
    device = get_device_for_org(device_id, organization_id)
    if not device:
        raise ValueError("Device not found or access denied.")

    if not data:
        return device

    updatable_fields = (
        "name",
        "device_type",
        "brand",
        "model",
        "is_sensor",
        "is_actuator",
    )

    for field in updatable_fields:
        if field in data and data[field] is not None:
            setattr(device, field, data[field])

    if "settings" in data:
        device.settings = data["settings"]

    if "is_online" in data:
        device.is_online = bool(data["is_online"])
        if device.is_online:
            device.last_seen = datetime.utcnow()

    db.session.commit()
    return device


def delete_device_logic(organization_id: UUID, device_id: UUID) -> None:
    """Cihazı soft delete yap."""
    device = get_device_for_org(device_id, organization_id)
    if not device:
        raise ValueError("Device not found or access denied.")

    device.is_active = False
    db.session.commit()
