"""Node (Uç Birim) yönetimi endpoint'leri."""
from flask import jsonify, request

from . import api_bp
from .helpers import get_or_create_user
from .. import db
from ..models import Device, Node, Site
from ..auth import requires_auth
from ..services import create_node_logic, update_node_logic


@api_bp.route('/nodes', methods=['POST'])
@requires_auth
def create_node():
    """
    Yeni bir node oluştur.
    ---
    tags:
      - Node
    consumes:
      - application/json
    parameters:
      - in: body
        name: node
        schema:
          type: object
          required:
            - device_id
          properties:
            device_id:
              type: integer
              description: Node'un bağlı olduğu Gateway/Device ID
            name:
              type: string
              example: Sulama Sensörü
            node_type:
              type: string
              enum: [SENSOR_NODE, INVERTER, BATTERY_STORAGE, ACTUATOR, METER]
              example: SENSOR_NODE
            protocol:
              type: string
              enum: [LORA, ZIGBEE, WIFI, WIRED, MODBUS, OTHER]
              example: LORA
            node_address:
              type: string
              example: ABC123DEF456
            battery_level:
              type: number
              example: 85.5
            signal_strength:
              type: number
              example: -72
            distance_estimate:
              type: number
              example: 150.5
            brand:
              type: string
              example: HUAWEI
            model_number:
              type: string
              example: SUN2000-100KTL
            capacity_info:
              type: object
            configuration:
              type: object
    responses:
      201:
        description: Node oluşturuldu
      400:
        description: Validasyon hatası
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        node = create_node_logic(user.id, request.json or {})
        return jsonify({
            "message": "Node oluşturuldu",
            "node": node.to_dict(),
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route('/nodes', methods=['GET'])
@requires_auth
def list_nodes():
    """
    Kullanıcıya ait tüm node'ları listele.
    ---
    tags:
      - Node
    parameters:
      - in: query
        name: device_id
        schema:
          type: integer
        description: Belirli bir cihaza bağlı node'ları filtreler
      - in: query
        name: node_type
        schema:
          type: string
        description: Node tipine göre filtrele (SENSOR_NODE, INVERTER vb.)
      - in: query
        name: include_assets
        schema:
          type: boolean
        description: Node'ların asset detaylarını dahil et
    responses:
      200:
        description: Node listesi
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    device_id = request.args.get("device_id", type=int)
    node_type = request.args.get("node_type", type=str)
    include_assets = request.args.get("include_assets", "false").lower() == "true"

    query = Node.query.join(Device).join(Site).filter(Site.user_id == user.id)

    if device_id:
        query = query.filter(Node.device_id == device_id)
    if node_type:
        query = query.filter(Node.node_type == node_type)

    nodes = query.order_by(Node.created_at.desc()).all()
    return jsonify([node.to_dict(include_assets=include_assets) for node in nodes])


@api_bp.route('/nodes/<int:node_id>', methods=['GET'])
@requires_auth
def get_node_detail(node_id):
    """
    Tek bir node'un detayını getir.
    ---
    tags:
      - Node
    parameters:
      - in: path
        name: node_id
        required: true
        schema:
          type: integer
      - in: query
        name: include_assets
        schema:
          type: boolean
        description: Node'un asset'lerini dahil et
    responses:
      200:
        description: Node detayları
      404:
        description: Node bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    include_assets = request.args.get("include_assets", "false").lower() == "true"

    node = Node.query.join(Device).join(Site).filter(
        Node.id == node_id,
        Site.user_id == user.id,
    ).first()

    if not node:
        return jsonify({"error": "Node bulunamadı"}), 404

    return jsonify(node.to_dict(include_assets=include_assets))


@api_bp.route('/nodes/<int:node_id>', methods=['PUT'])
@requires_auth
def update_node(node_id):
    """
    Bir node'un bilgilerini güncelle.
    ---
    tags:
      - Node
    parameters:
      - in: path
        name: node_id
        required: true
        schema:
          type: integer
      - in: body
        name: payload
        schema:
          type: object
          properties:
            name:
              type: string
            node_type:
              type: string
            protocol:
              type: string
            node_address:
              type: string
            battery_level:
              type: number
            signal_strength:
              type: number
            distance_estimate:
              type: number
            brand:
              type: string
            model_number:
              type: string
            capacity_info:
              type: object
            configuration:
              type: object
            last_seen:
              type: string
              example: 2025-01-01T12:00:00Z
    responses:
      200:
        description: Node güncellendi
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        node = update_node_logic(user.id, node_id, request.json or {})
        return jsonify({
            "message": "Node güncellendi",
            "node": node.to_dict()
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@api_bp.route('/nodes/<int:node_id>', methods=['DELETE'])
@requires_auth
def delete_node(node_id):
    """
    Bir node'u sil.
    ---
    tags:
      - Node
    parameters:
      - in: path
        name: node_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Node silindi
    """
    user = get_or_create_user()
    node = Node.query.join(Device).join(Site).filter(
        Node.id == node_id,
        Site.user_id == user.id,
    ).first()

    if not node:
        return jsonify({"error": "Node bulunamadı"}), 404

    db.session.delete(node)
    db.session.commit()

    return jsonify({"message": "Node silindi"})
