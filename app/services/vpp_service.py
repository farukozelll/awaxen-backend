"""VPP (Virtual Power Plant) iş mantığı."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from .. import db
from ..models import Device, DeviceStatus, Node, NodeType, Site, VppRule, VppRuleLog
from .node_service import _get_node_for_user


def create_vpp_rule_logic(user_id: int, data: Dict[str, Any]) -> VppRule:
    """Yeni VPP kuralı oluştur."""
    name = data.get("name", "").strip()
    if not name:
        raise ValueError("Kural adı zorunludur.")

    node_id = data.get("node_id")
    if not node_id:
        raise ValueError("Node ID zorunludur.")

    # Node'un kullanıcıya ait olduğunu ve Inverter olduğunu kontrol et
    node = _get_node_for_user(node_id, user_id)
    if not node:
        raise ValueError("Node bulunamadı veya yetkiniz yok.")

    if node.node_type != NodeType.INVERTER.value:
        raise ValueError("VPP kuralları sadece Inverter tipi node'lara uygulanabilir.")

    trigger = data.get("trigger")
    if not trigger:
        raise ValueError("Tetikleyici koşul (trigger) zorunludur.")

    action = data.get("action")
    if not action:
        raise ValueError("Aksiyon zorunludur.")

    rule = VppRule(
        user_id=user_id,
        node_id=node_id,
        name=name,
        description=data.get("description"),
        trigger=trigger,
        action=action,
        priority=data.get("priority", 1),
        is_active=data.get("is_active", True),
    )

    db.session.add(rule)
    db.session.commit()
    return rule


def update_vpp_rule_logic(user_id: int, rule_id: int, data: Dict[str, Any]) -> VppRule:
    """VPP kuralını güncelle."""
    rule = VppRule.query.filter_by(id=rule_id, user_id=user_id).first()
    if not rule:
        raise ValueError("Kural bulunamadı veya yetkiniz yok.")

    if "name" in data:
        rule.name = data["name"]
    if "description" in data:
        rule.description = data["description"]
    if "trigger" in data:
        rule.trigger = data["trigger"]
    if "action" in data:
        rule.action = data["action"]
    if "priority" in data:
        rule.priority = data["priority"]
    if "is_active" in data:
        rule.is_active = data["is_active"]

    db.session.commit()
    return rule


def delete_vpp_rule_logic(user_id: int, rule_id: int) -> None:
    """VPP kuralını sil."""
    rule = VppRule.query.filter_by(id=rule_id, user_id=user_id).first()
    if not rule:
        raise ValueError("Kural bulunamadı veya yetkiniz yok.")

    db.session.delete(rule)
    db.session.commit()


def get_vpp_rules_for_node(user_id: int, node_id: int) -> List[VppRule]:
    """Bir Node'a ait VPP kurallarını getir."""
    node = _get_node_for_user(node_id, user_id)
    if not node:
        raise ValueError("Node bulunamadı veya yetkiniz yok.")

    return VppRule.query.filter_by(node_id=node_id, user_id=user_id).order_by(VppRule.priority).all()


def log_vpp_rule_execution(
    rule_id: int,
    trigger_context: Dict[str, Any],
    action_sent: Dict[str, Any],
    status: str = "PENDING",
    command_id: Optional[int] = None,
    error_message: Optional[str] = None
) -> VppRuleLog:
    """VPP kural çalışmasını logla."""
    log = VppRuleLog(
        rule_id=rule_id,
        trigger_context=trigger_context,
        action_sent=action_sent,
        status=status,
        command_id=command_id,
        error_message=error_message,
    )

    # Kuralın istatistiklerini güncelle
    rule = VppRule.query.get(rule_id)
    if rule:
        rule.last_triggered_at = datetime.utcnow()
        rule.trigger_count = (rule.trigger_count or 0) + 1

    db.session.add(log)
    db.session.commit()
    return log


def get_vpp_rule_logs(user_id: int, rule_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """VPP kuralının çalışma geçmişini getir."""
    rule = VppRule.query.filter_by(id=rule_id, user_id=user_id).first()
    if not rule:
        raise ValueError("Kural bulunamadı veya yetkiniz yok.")

    logs = (
        VppRuleLog.query
        .filter_by(rule_id=rule_id)
        .order_by(VppRuleLog.triggered_at.desc())
        .limit(limit)
        .all()
    )
    return [log.to_dict() for log in logs]


def get_inverters_for_user(user_id: int) -> List[Node]:
    """Kullanıcının tüm inverter'larını getir."""
    return (
        Node.query
        .join(Device)
        .join(Site)
        .filter(
            Site.user_id == user_id,
            Node.node_type == NodeType.INVERTER.value
        )
        .all()
    )


def get_inverter_summary(user_id: int) -> Dict[str, Any]:
    """Kullanıcının inverter özetini getir (VPP Dashboard için)."""
    inverters = get_inverters_for_user(user_id)

    total_capacity_kw = 0
    total_battery_kwh = 0
    online_count = 0

    for inv in inverters:
        capacity = inv.capacity_info or {}
        total_capacity_kw += capacity.get("max_power_kw", 0)
        total_battery_kwh += capacity.get("battery_capacity_kwh", 0)

        # Device durumunu kontrol et
        if inv.device.status == DeviceStatus.ONLINE.value:
            online_count += 1

    return {
        "total_inverters": len(inverters),
        "online_inverters": online_count,
        "total_capacity_kw": total_capacity_kw,
        "total_battery_kwh": total_battery_kwh,
        "inverters": [
            {
                **inv.to_dict(),
                "site_name": inv.device.site.name,
                "device_name": inv.device.name,
                "device_status": inv.device.status,
            }
            for inv in inverters
        ]
    }
