"""Node (Uç Birim) iş mantığı."""
from datetime import datetime
from typing import Any, Dict

from .. import db
from ..models import Device, Node, NodeProtocol, Site


def _get_node_for_user(node_id: int, user_id: int) -> Node:
    """Kullanıcıya ait Node'u getir."""
    return (
        Node.query.join(Device)
        .join(Site)
        .filter(Node.id == node_id, Site.user_id == user_id)
        .first()
    )


def create_node_logic(user_id: int, data: Dict[str, Any]) -> Node:
    """Yeni node oluştur."""
    if not data:
        raise ValueError("Node verisi gereklidir.")

    from .device_service import _get_device_for_user

    device = _get_device_for_user(data.get("device_id"), user_id)
    if not device:
        raise ValueError("Cihaz bulunamadı veya yetkiniz yok.")

    node = Node(
        device_id=device.id,
        name=data.get("name"),
        node_type=data.get("node_type", "SENSOR"),
        protocol=data.get("protocol", NodeProtocol.LORA.value),
        node_address=data.get("node_address"),
        battery_level=data.get("battery_level"),
        signal_strength=data.get("signal_strength"),
        distance_estimate=data.get("distance_estimate"),
        configuration=data.get("configuration", {}),
    )
    db.session.add(node)
    db.session.commit()
    return node


def update_node_logic(user_id: int, node_id: int, data: Dict[str, Any]) -> Node:
    """Node bilgilerini güncelle."""
    node = _get_node_for_user(node_id, user_id)
    if not node:
        raise ValueError("Node bulunamadı veya yetkiniz yok.")

    if not data:
        return node

    updatable_fields = [
        "name",
        "node_type",
        "protocol",
        "node_address",
        "battery_level",
        "signal_strength",
        "distance_estimate",
        "configuration",
        "brand",
        "model_number",
        "capacity_info",
    ]

    for field in updatable_fields:
        if field in data:
            setattr(node, field, data[field])

    if "last_seen" in data:
        last_seen_val = data["last_seen"]
        if isinstance(last_seen_val, str):
            try:
                last_seen_val = datetime.fromisoformat(last_seen_val.replace("Z", "+00:00"))
            except ValueError:
                last_seen_val = None
        node.last_seen = last_seen_val

    db.session.commit()
    return node


def delete_node_logic(user_id: int, node_id: int) -> None:
    """Node'u sil."""
    node = _get_node_for_user(node_id, user_id)
    if not node:
        raise ValueError("Node bulunamadı veya yetkiniz yok.")

    db.session.delete(node)
    db.session.commit()
