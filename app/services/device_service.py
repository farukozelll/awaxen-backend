"""Device (Cihaz/Gateway) iş mantığı."""
from datetime import datetime
from typing import Any, Dict

from .. import db
from ..models import Device, Site
from .helpers import _resolve_metadata


def _get_device_for_user(device_id: int, user_id: int) -> Device:
    """Kullanıcıya ait Device'ı getir."""
    return (
        Device.query.join(Site)
        .filter(Device.id == device_id, Site.user_id == user_id)
        .first()
    )


def create_device_logic(user_id: int, data: Dict[str, Any]) -> Device:
    """Yeni cihaz oluştur."""
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
    """Cihaz bilgilerini güncelle."""
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
    """Cihazı sil."""
    device = _get_device_for_user(device_id, user_id)
    if not device:
        raise ValueError("Cihaz bulunamadı veya yetkiniz yok.")

    db.session.delete(device)
    db.session.commit()
