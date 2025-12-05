"""Telemetri endpoint'leri."""
from flask import jsonify, request

from . import api_bp
from .helpers import get_or_create_user, parse_iso_datetime
from .. import db
from ..models import Device, Node, Site, Telemetry
from ..auth import requires_auth


@api_bp.route('/telemetry', methods=['POST'])
def receive_telemetry():
    """
    Core cihazlardan telemetri verisini kaydet.
    ---
    tags:
      - Telemetry
    consumes:
      - application/json
    parameters:
      - in: body
        name: telemetry
        required: true
        schema:
          type: object
          properties:
            serial_number:
              type: string
              example: AWX-CORE-0001
            node_name:
              type: string
              example: Solar Inverter
            data:
              type: object
              example: {"power": 4200.5, "voltage": 810}
    responses:
      201:
        description: Telemetri kaydedildi
      404:
        description: Cihaz veya node bulunamadı
    """
    try:
        payload = request.json

        device = Device.query.filter_by(serial_number=payload['serial_number']).first()
        if not device:
            return jsonify({"error": "Cihaz bulunamadı"}), 404

        node = Node.query.filter_by(device_id=device.id, name=payload['node_name']).first()
        if not node:
            return jsonify({"error": "Node tanimsiz"}), 404

        for key, value in payload['data'].items():
            new_telemetry = Telemetry(
                node_id=node.id,
                key=key,
                value=float(value)
            )
            db.session.add(new_telemetry)

        device.is_online = True
        db.session.commit()

        return jsonify({"status": "success"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route('/telemetry/history', methods=['GET'])
@requires_auth
def get_telemetry_history():
    """
    Bir node için tarih aralığındaki telemetri verilerini getir.
    ---
    tags:
      - Telemetry
    parameters:
      - in: query
        name: node_id
        required: true
        schema:
          type: integer
      - in: query
        name: start_date
        required: false
        schema:
          type: string
          format: date-time
      - in: query
        name: end_date
        required: false
        schema:
          type: string
          format: date-time
    responses:
      200:
        description: Telemetri geçmişi
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    node_id = request.args.get('node_id', type=int)
    if not node_id:
        return jsonify({"error": "node_id zorunlu"}), 400

    node = Node.query.join(Device).join(Site).filter(
        Node.id == node_id,
        Site.user_id == user.id,
    ).first()
    if not node:
        return jsonify({"error": "Node bulunamadı"}), 404

    start = parse_iso_datetime(request.args.get('start_date'))
    end = parse_iso_datetime(request.args.get('end_date'))

    query = Telemetry.query.filter(Telemetry.node_id == node_id)
    if start:
        query = query.filter(Telemetry.time >= start)
    if end:
        query = query.filter(Telemetry.time <= end)

    records = query.order_by(Telemetry.time.asc()).limit(5000).all()

    return jsonify([
        {
            "time": rec.time.isoformat(),
            "key": rec.key,
            "value": rec.value,
        }
        for rec in records
    ])
