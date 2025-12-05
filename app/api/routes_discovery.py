"""Auto-Discovery (Otomatik Keşif) yönetimi endpoint'leri."""
from flask import jsonify, request

from . import api_bp
from .helpers import get_or_create_user
from .. import db
from ..models import Device, DiscoveryQueue, DiscoveryStatus, Node, Site
from ..auth import requires_auth


@api_bp.route('/discovery/pending', methods=['GET'])
@requires_auth
def get_pending_discoveries():
    """
    Kullanıcının Gateway'leri tarafından bulunan ama henüz eklenmemiş cihazları getir.
    ---
    tags:
      - Discovery
    security:
      - bearerAuth: []
    responses:
      200:
        description: Bekleyen keşifler listesi
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    user_gateways = Device.query.join(Site).filter(Site.user_id == user.id).all()
    gateway_ids = [d.id for d in user_gateways]

    if not gateway_ids:
        return jsonify([])

    pending = (
        DiscoveryQueue.query
        .filter(
            DiscoveryQueue.reported_by_device_id.in_(gateway_ids),
            DiscoveryQueue.status == DiscoveryStatus.PENDING.value
        )
        .order_by(DiscoveryQueue.last_seen_at.desc())
        .all()
    )

    return jsonify([d.to_dict() for d in pending])


@api_bp.route('/discovery/claim', methods=['POST'])
@requires_auth
def claim_discovered_device():
    """
    Keşfedilen bir cihazı "Gerçek Node" olarak kaydet (Sahiplen).
    ---
    tags:
      - Discovery
    security:
      - bearerAuth: []
    consumes:
      - application/json
    parameters:
      - in: body
        name: payload
        schema:
          type: object
          required:
            - discovery_id
            - name
          properties:
            discovery_id:
              type: integer
              description: Keşif kaydının ID'si
            name:
              type: string
              description: Cihaza verilecek isim
            node_type:
              type: string
              description: Cihaz tipi (SENSOR_NODE, INVERTER, vb.)
            protocol:
              type: string
              description: Haberleşme protokolü
    responses:
      201:
        description: Cihaz başarıyla eklendi
      404:
        description: Keşif bulunamadı
      403:
        description: Yetkisiz işlem
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    data = request.json or {}
    discovery_id = data.get("discovery_id")
    name = data.get("name", "").strip()

    if not discovery_id:
        return jsonify({"error": "discovery_id zorunludur"}), 400

    if not name:
        return jsonify({"error": "Cihaz adı zorunludur"}), 400

    discovery = DiscoveryQueue.query.get(discovery_id)
    if not discovery:
        return jsonify({"error": "Keşif kaydı bulunamadı"}), 404

    gateway = discovery.reporter
    if not gateway or not gateway.site or gateway.site.user_id != user.id:
        return jsonify({"error": "Bu cihazı ekleme yetkiniz yok"}), 403

    if discovery.status != DiscoveryStatus.PENDING.value:
        return jsonify({"error": f"Bu cihaz zaten işlenmiş (durum: {discovery.status})"}), 400

    node_type = data.get("node_type") or discovery.guessed_type or "SENSOR_NODE"
    protocol = data.get("protocol") or discovery.protocol or "UNKNOWN"

    new_node = Node(
        device_id=gateway.id,
        name=name,
        node_address=discovery.device_identifier,
        node_type=node_type,
        protocol=protocol,
        brand=discovery.guessed_brand,
        model_number=discovery.guessed_model,
        signal_strength=discovery.signal_strength,
        distance_estimate=discovery.distance_estimate,
        configuration=discovery.raw_data or {},
    )
    db.session.add(new_node)

    discovery.status = DiscoveryStatus.CLAIMED.value

    db.session.commit()

    return jsonify({
        "message": "Cihaz başarıyla eklendi",
        "node": new_node.to_dict(),
        "gateway": {
            "id": gateway.id,
            "name": gateway.name,
            "serial_number": gateway.serial_number,
        }
    }), 201


@api_bp.route('/discovery/<int:discovery_id>/ignore', methods=['POST'])
@requires_auth
def ignore_discovered_device(discovery_id):
    """
    Keşfedilen bir cihazı yoksay (Listeden kaldır).
    ---
    tags:
      - Discovery
    security:
      - bearerAuth: []
    parameters:
      - in: path
        name: discovery_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Cihaz yoksayıldı
      404:
        description: Keşif bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    discovery = DiscoveryQueue.query.get(discovery_id)
    if not discovery:
        return jsonify({"error": "Keşif kaydı bulunamadı"}), 404

    gateway = discovery.reporter
    if not gateway or not gateway.site or gateway.site.user_id != user.id:
        return jsonify({"error": "Bu işlem için yetkiniz yok"}), 403

    discovery.status = DiscoveryStatus.IGNORED.value
    db.session.commit()

    return jsonify({"message": "Cihaz yoksayıldı"})


@api_bp.route('/discovery/<int:discovery_id>', methods=['DELETE'])
@requires_auth
def delete_discovered_device(discovery_id):
    """
    Keşif kaydını tamamen sil.
    ---
    tags:
      - Discovery
    security:
      - bearerAuth: []
    parameters:
      - in: path
        name: discovery_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Keşif silindi
      404:
        description: Keşif bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    discovery = DiscoveryQueue.query.get(discovery_id)
    if not discovery:
        return jsonify({"error": "Keşif kaydı bulunamadı"}), 404

    gateway = discovery.reporter
    if not gateway or not gateway.site or gateway.site.user_id != user.id:
        return jsonify({"error": "Bu işlem için yetkiniz yok"}), 403

    db.session.delete(discovery)
    db.session.commit()

    return jsonify({"message": "Keşif kaydı silindi"})


@api_bp.route('/discovery/stats', methods=['GET'])
@requires_auth
def get_discovery_stats():
    """
    Keşif istatistiklerini getir.
    ---
    tags:
      - Discovery
    security:
      - bearerAuth: []
    responses:
      200:
        description: Keşif istatistikleri
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    user_gateways = Device.query.join(Site).filter(Site.user_id == user.id).all()
    gateway_ids = [d.id for d in user_gateways]

    if not gateway_ids:
        return jsonify({
            "pending_count": 0,
            "claimed_count": 0,
            "ignored_count": 0,
            "total_gateways": 0,
        })

    pending_count = DiscoveryQueue.query.filter(
        DiscoveryQueue.reported_by_device_id.in_(gateway_ids),
        DiscoveryQueue.status == DiscoveryStatus.PENDING.value
    ).count()

    claimed_count = DiscoveryQueue.query.filter(
        DiscoveryQueue.reported_by_device_id.in_(gateway_ids),
        DiscoveryQueue.status == DiscoveryStatus.CLAIMED.value
    ).count()

    ignored_count = DiscoveryQueue.query.filter(
        DiscoveryQueue.reported_by_device_id.in_(gateway_ids),
        DiscoveryQueue.status == DiscoveryStatus.IGNORED.value
    ).count()

    return jsonify({
        "pending_count": pending_count,
        "claimed_count": claimed_count,
        "ignored_count": ignored_count,
        "total_gateways": len(gateway_ids),
    })
