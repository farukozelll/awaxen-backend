"""Telemetri endpoint'leri - v6.0 (TimescaleDB + Real-Time)."""
from datetime import datetime, timedelta
from flask import jsonify, request
from sqlalchemy import func

from . import api_bp
from .helpers import get_current_user, parse_iso_datetime
from app.extensions import db
from app.models import SmartDevice, DeviceTelemetry
from app.auth import requires_auth
from app.realtime import emit_telemetry, emit_device_status, redis_pubsub


def _prepare_single(payload: dict):
    """
    Tek bir telemetri kaydını hazırla.
    
    Raspberry Pi / Edge Agent formatını destekler:
    - device_id: UUID veya external_id (string) olabilir
    - Veriler doğrudan payload içinde veya 'data' objesi içinde olabilir
    
    DeviceTelemetry key-value yapısında çalışır:
    - Her ölçüm (power, voltage, vb.) ayrı bir satır olarak kaydedilir
    """
    device = None
    device_identifier = payload.get('device_id') or payload.get('external_id')
    
    if device_identifier:
        # Önce UUID olarak dene
        try:
            from uuid import UUID
            UUID(str(device_identifier))
            device = SmartDevice.query.filter_by(id=device_identifier).first()
        except (ValueError, AttributeError):
            pass
        
        # UUID değilse external_id olarak ara
        if not device:
            device = SmartDevice.query.filter_by(external_id=str(device_identifier)).first()
    
    if not device:
        raise ValueError(f"Device not found: {device_identifier}")

    # Veri 'data' objesi içinde veya doğrudan payload'da olabilir
    data = payload.get('data', {}) or {}
    
    # Eğer data boşsa, payload'dan direkt oku (Pi formatı)
    if not data:
        data = {
            'power': payload.get('power'),
            'voltage': payload.get('voltage'),
            'current': payload.get('current'),
            'energy': payload.get('energy_total_kwh') or payload.get('energy'),
            'temperature': payload.get('temperature') or payload.get('temp'),
            'humidity': payload.get('humidity'),
        }
    
    # None değerleri temizle
    data = {k: v for k, v in data.items() if v is not None}

    # Timestamp varsa kullan, yoksa şimdiki zaman
    timestamp = None
    if payload.get('timestamp'):
        timestamp = parse_iso_datetime(payload['timestamp'])
    if not timestamp:
        timestamp = datetime.utcnow()

    # DeviceTelemetry key-value yapısında: her ölçüm ayrı satır
    telemetry_records = []
    for key, value in data.items():
        if value is not None:
            telemetry = DeviceTelemetry(
                time=timestamp,
                device_id=device.id,
                key=key,
                value=float(value),
            )
            db.session.add(telemetry)
            telemetry_records.append(telemetry)

    was_offline = not device.is_online
    device.is_online = True
    device.last_seen = datetime.utcnow()

    return device, telemetry_records, data, was_offline


def _handle_telemetry_ingest(raw_payload):
    try:
        payload = raw_payload
        if payload is None:
            return jsonify({"error": "Invalid JSON payload"}), 400

        payload_list = payload if isinstance(payload, list) else [payload]
        if not payload_list:
            return jsonify({"error": "Telemetry payload is empty"}), 400

        processed = []

        for entry in payload_list:
            if not isinstance(entry, dict):
                raise ValueError("Each telemetry entry must be an object")
            processed.append(_prepare_single(entry))

        db.session.commit()

        # Real-time yayınları commit sonrası yap
        for device, telemetry_records, data, was_offline in processed:
            org_id = str(device.organization_id) if device.organization_id else None
            if not org_id:
                continue

            # İlk kaydın zamanını al
            first_time = telemetry_records[0].time if telemetry_records else None
            
            emit_telemetry(org_id, str(device.id), {
                **data,
                "time": first_time.isoformat() if first_time else None
            })

            if was_offline:
                emit_device_status(org_id, str(device.id), {
                    "is_online": True,
                    "last_seen": device.last_seen.isoformat(),
                    "event": "device_online"
                })

        if len(processed) == 1:
            device = processed[0][0]
            return jsonify({"status": "success", "device_id": str(device.id)}), 201

        return jsonify({
            "status": "success",
            "processed": len(processed),
            "device_ids": [str(device.id) for device, *_ in processed]
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@api_bp.route('/telemetry', methods=['POST'])
def receive_telemetry():
    """
    Cihazlardan telemetri verisini kaydet (legacy endpoint).
    """
    return _handle_telemetry_ingest(request.get_json(silent=True))


@api_bp.route('/v1/ingest', methods=['POST'])
def ingest_telemetry():
    """
    Edge cihazlarından (Raspberry Pi) gelen toplu telemetri verilerini kaydet.
    ---
    tags:
      - Telemetry
      - Edge
    consumes:
      - application/json
    parameters:
      - in: body
        name: telemetry
        required: true
        schema:
          type: array
          items:
            type: object
            properties:
              device_id:
                type: string
                description: Cihaz UUID veya external_id (örn. awaxen-pi-01)
                example: awaxen-pi-01
              timestamp:
                type: string
                format: date-time
                example: "2025-12-23T19:51:00Z"
              power:
                type: number
                description: Güç (Watt)
                example: 1200.5
              voltage:
                type: number
                description: Voltaj (V)
                example: 220
              current:
                type: number
                description: Akım (A)
                example: 5.4
              temperature:
                type: number
                description: Sıcaklık (°C)
                example: 35.2
              humidity:
                type: number
                description: Nem (%)
                example: 45
              energy_total_kwh:
                type: number
                description: Toplam enerji (kWh)
                example: 14.2
    responses:
      201:
        description: Telemetri başarıyla kaydedildi
        schema:
          type: object
          properties:
            status:
              type: string
              example: success
            processed:
              type: integer
              example: 50
            device_ids:
              type: array
              items:
                type: string
      400:
        description: Geçersiz payload
      404:
        description: Cihaz bulunamadı
    """
    return _handle_telemetry_ingest(request.get_json(silent=True))


@api_bp.route('/telemetry/history', methods=['GET'])
@requires_auth
def get_telemetry_history():
    """
    Bir cihaz için tarih aralığındaki telemetri verilerini getir.
    ---
    tags:
      - Telemetry
    security:
      - bearerAuth: []
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
        name: interval
        required: false
        schema:
          type: string
          enum: [raw, 5m, 15m, 1h, 6h, 1d]
          default: raw
        description: "Downsampling aralığı. raw seçilirse ham veriler döner, diğer değerlerde ortalama alınır."
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
    interval = request.args.get('interval', 'raw')

    # Varsayılan: son 24 saat
    if not start:
        start = datetime.utcnow() - timedelta(hours=24)
    if not end:
        end = datetime.utcnow()

    base_filters = [
        DeviceTelemetry.device_id == device_id,
        DeviceTelemetry.time >= start,
        DeviceTelemetry.time <= end
    ]

    interval_map = {
        "5m": "5 minutes",
        "15m": "15 minutes",
        "1h": "1 hour",
        "6h": "6 hours",
        "1d": "1 day",
    }

    if interval and interval.lower() in interval_map:
        bucket_interval = interval_map[interval.lower()]
        bucket = func.time_bucket(bucket_interval, DeviceTelemetry.time).label("bucket")

        agg_query = db.session.query(
            bucket,
            func.avg(DeviceTelemetry.power_w).label("power_w"),
            func.avg(DeviceTelemetry.voltage).label("voltage"),
            func.avg(DeviceTelemetry.current).label("current"),
            func.avg(DeviceTelemetry.energy_total_kwh).label("energy_total_kwh"),
            func.avg(DeviceTelemetry.temperature).label("temperature"),
            func.avg(DeviceTelemetry.humidity).label("humidity"),
        ).filter(*base_filters).group_by(bucket).order_by(bucket.asc())

        rows = agg_query.all()
        response = []
        for row in rows:
            response.append({
                "time": row.bucket.isoformat() if row.bucket else None,
                "power_w": float(row.power_w) if row.power_w is not None else None,
                "voltage": float(row.voltage) if row.voltage is not None else None,
                "current": float(row.current) if row.current is not None else None,
                "energy_total_kwh": float(row.energy_total_kwh) if row.energy_total_kwh is not None else None,
                "temperature": float(row.temperature) if row.temperature is not None else None,
                "humidity": float(row.humidity) if row.humidity is not None else None,
                "interval": interval.lower(),
                "aggregated": True,
            })
        return jsonify(response)

    query = DeviceTelemetry.query.filter(*base_filters)

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
