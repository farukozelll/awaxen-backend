"""VPP (Virtual Power Plant) yönetimi endpoint'leri."""
from datetime import date

from flask import jsonify, request

from . import api_bp
from .helpers import get_or_create_user
from ..models import VppRule
from ..auth import requires_auth
from ..services import (
    create_vpp_rule_logic,
    update_vpp_rule_logic,
    delete_vpp_rule_logic,
    get_vpp_rules_for_node,
    get_vpp_rule_logs,
    get_inverters_for_user,
    get_inverter_summary,
)


@api_bp.route('/vpp/rules', methods=['GET'])
@requires_auth
def get_vpp_rules():
    """Kullanıcının tüm VPP kurallarını listele."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    rules = VppRule.query.filter_by(user_id=user.id).order_by(VppRule.priority).all()
    return jsonify([r.to_dict() for r in rules])


@api_bp.route('/vpp/rules', methods=['POST'])
@requires_auth
def create_vpp_rule():
    """
    Yeni VPP kuralı oluştur.
    ---
    tags:
      - VPP
    parameters:
      - in: body
        name: rule
        schema:
          type: object
          required:
            - node_id
            - name
            - trigger
            - action
          properties:
            node_id:
              type: integer
              example: 1
            name:
              type: string
              example: Puant Saatinde Deşarj Et
            trigger:
              type: object
              example: {"type": "TIME_RANGE", "start": "17:00", "end": "22:00"}
            action:
              type: object
              example: {"type": "DISCHARGE_BATTERY", "power_limit_kw": 50}
    responses:
      201:
        description: Kural oluşturuldu
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        rule = create_vpp_rule_logic(user.id, request.json)
        return jsonify({
            "message": "VPP kuralı oluşturuldu",
            "rule": rule.to_dict()
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route('/vpp/rules/<int:rule_id>', methods=['GET'])
@requires_auth
def get_vpp_rule_detail(rule_id):
    """VPP kuralı detayını getir."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    rule = VppRule.query.filter_by(id=rule_id, user_id=user.id).first()
    if not rule:
        return jsonify({"error": "Kural bulunamadı"}), 404

    return jsonify(rule.to_dict())


@api_bp.route('/vpp/rules/<int:rule_id>', methods=['PUT'])
@requires_auth
def update_vpp_rule(rule_id):
    """VPP kuralını güncelle."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        rule = update_vpp_rule_logic(user.id, rule_id, request.json)
        return jsonify({
            "message": "VPP kuralı güncellendi",
            "rule": rule.to_dict()
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@api_bp.route('/vpp/rules/<int:rule_id>', methods=['DELETE'])
@requires_auth
def delete_vpp_rule(rule_id):
    """VPP kuralını sil."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        delete_vpp_rule_logic(user.id, rule_id)
        return jsonify({"message": "VPP kuralı silindi"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@api_bp.route('/vpp/rules/<int:rule_id>/logs', methods=['GET'])
@requires_auth
def get_rule_logs(rule_id):
    """VPP kuralının çalışma geçmişini getir."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    limit = request.args.get("limit", 50, type=int)

    try:
        logs = get_vpp_rule_logs(user.id, rule_id, limit)
        return jsonify(logs)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@api_bp.route('/nodes/<int:node_id>/vpp-rules', methods=['GET'])
@requires_auth
def get_node_vpp_rules(node_id):
    """Bir Node'a ait VPP kurallarını listele."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        rules = get_vpp_rules_for_node(user.id, node_id)
        return jsonify([r.to_dict() for r in rules])
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@api_bp.route('/vpp/inverters', methods=['GET'])
@requires_auth
def get_user_inverters():
    """Kullanıcının tüm inverter'larını listele."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    inverters = get_inverters_for_user(user.id)
    return jsonify([
        {
            **inv.to_dict(),
            "site_name": inv.device.site.name,
            "device_name": inv.device.name,
            "device_status": inv.device.status,
        }
        for inv in inverters
    ])


@api_bp.route('/vpp/summary', methods=['GET'])
@requires_auth
def get_vpp_summary():
    """
    VPP Dashboard özeti - Toplam kapasite, online inverter sayısı vb.
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    summary = get_inverter_summary(user.id)

    # Aktif kural sayısını ekle
    active_rules = VppRule.query.filter_by(user_id=user.id, is_active=True).count()
    summary["active_rules"] = active_rules

    return jsonify(summary)
