"""Telemetri endpoint'leri - v6.0 (TimescaleDB)."""
from datetime import datetime, timedelta
from flask import jsonify, request

from . import api_bp
from .helpers import get_current_user, parse_iso_datetime
from app.extensions import db
from app.models import SmartDevice, DeviceTelemetry
from app.auth import requires_auth


@api_bp.route('/telemetry', methods=['POST'])
def receive_telemetry():
    """
    Cihazlardan telemetri verisini kaydet.
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
            device_id:
              type: string
              format: uuid
            external_id:
              type: string
              example: shellyplus1pm-abc123
            data:
              type: object
              example: {"power": 1200.5, "voltage": 220, "temperature": 35.2}
    responses:
      201:
        description: Telemetri kaydedildi
      404:
        description: Cihaz bulunamadı
    """
    try:
        payload = request.json
        
        # device_id veya external_id ile cihaz bul
        device = None
        if payload.get('device_id'):
            device = SmartDevice.query.filter_by(id=payload['device_id']).first()
        elif payload.get('external_id'):
            device = SmartDevice.query.filter_by(external_id=payload['external_id']).first()
        
        if not device:
            return jsonify({"error": "Device not found"}), 404

        data = payload.get('data', {})
        
        telemetry = DeviceTelemetry(
            device_id=device.id,
            power_w=data.get('power'),
            voltage=data.get('voltage'),
            current=data.get('current'),
            energy_total_kwh=data.get('energy_total_kwh'),
            temperature=data.get('temperature'),
            humidity=data.get('humidity'),
            raw_data=data,
        )
        db.session.add(telemetry)

        # Cihaz durumunu güncelle
        device.is_online = True
        device.last_seen = datetime.utcnow()
        
        db.session.commit()

        return jsonify({"status": "success", "device_id": str(device.id)}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route('/telemetry/history', methods=['GET'])
@requires_auth
def get_telemetry_history():
    """
    Bir cihaz için tarih aralığındaki telemetri verilerini getir.
    ---
    tags:
      - Telemetry
    parameters:
      - in: query
        name: device_id
        required: true
        schema:
          type: string
          format: uuid
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
      - in: query
        name: limit
        required: false
        schema:
          type: integer
          default: 1000
    responses:
      200:
        description: Telemetri geçmişi
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401

    device_id = request.args.get('device_id')
    if not device_id:
        return jsonify({"error": "device_id is required"}), 400

    # Cihazın kullanıcının organizasyonuna ait olduğunu kontrol et
    device = SmartDevice.query.filter_by(
        id=device_id,
        organization_id=user.organization_id
    ).first()
    
    if not device:
        return jsonify({"error": "Device not found"}), 404

    start = parse_iso_datetime(request.args.get('start_date'))
    end = parse_iso_datetime(request.args.get('end_date'))
    limit = request.args.get('limit', 1000, type=int)

    # Varsayılan: son 24 saat
    if not start:
        start = datetime.utcnow() - timedelta(hours=24)
    if not end:
        end = datetime.utcnow()

    query = DeviceTelemetry.query.filter(
        DeviceTelemetry.device_id == device_id,
        DeviceTelemetry.time >= start,
        DeviceTelemetry.time <= end
    )

    records = query.order_by(DeviceTelemetry.time.asc()).limit(limit).all()

    return jsonify([r.to_dict() for r in records])


@api_bp.route('/telemetry/latest', methods=['GET'])
@requires_auth
def get_latest_telemetry():
    """
    Bir cihazın en son telemetri verisini getir.
    ---
    tags:
      - Telemetry
    parameters:
      - in: query
        name: device_id
        required: true
        schema:
          type: string
          format: uuid
    responses:
      200:
        description: En son telemetri verisi
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401

    device_id = request.args.get('device_id')
    if not device_id:
        return jsonify({"error": "device_id is required"}), 400

    device = SmartDevice.query.filter_by(
        id=device_id,
        organization_id=user.organization_id
    ).first()
    
    if not device:
        return jsonify({"error": "Device not found"}), 404

    latest = DeviceTelemetry.query.filter_by(
        device_id=device_id
    ).order_by(DeviceTelemetry.time.desc()).first()

    if not latest:
        return jsonify({"error": "No telemetry data found"}), 404

    return jsonify(latest.to_dict())
