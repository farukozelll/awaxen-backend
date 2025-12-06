"""SmartDevice (Akıllı Cihaz) yönetimi endpoint'leri - v6.0."""
from flask import jsonify, request

from . import api_bp
from .helpers import get_current_user, get_pagination_params, get_filter_params, paginate_response, apply_sorting
from app.models import SmartDevice
from app.extensions import db
from app.auth import requires_auth


@api_bp.route('/devices', methods=['GET'])
@requires_auth
def get_devices():
    """
    Organizasyonun tüm akıllı cihazlarını listele.
    ---
    tags:
      - Devices
    security:
      - bearerAuth: []
    parameters:
      - name: page
        in: query
        type: integer
        default: 1
        description: Sayfa numarası
      - name: pageSize
        in: query
        type: integer
        default: 20
        description: Sayfa başına kayıt (max 100)
      - name: search
        in: query
        type: string
        description: İsim veya external_id'de arama
      - name: sortBy
        in: query
        type: string
        enum: [name, device_type, brand, created_at, is_online]
        default: created_at
        description: Sıralama alanı
      - name: sortOrder
        in: query
        type: string
        enum: [asc, desc]
        default: desc
        description: Sıralama yönü
      - name: integration_id
        in: query
        type: string
        format: uuid
        description: Entegrasyon ID'sine göre filtrele
      - name: gateway_id
        in: query
        type: string
        format: uuid
        description: Gateway ID'sine göre filtrele
      - name: device_type
        in: query
        type: string
        enum: [relay, plug, dimmer, sensor, thermostat, meter, inverter, battery]
        description: Cihaz tipine göre filtrele
      - name: is_online
        in: query
        type: boolean
        description: Online durumuna göre filtrele
    responses:
      200:
        description: Cihaz listesi
        schema:
          type: object
          properties:
            data:
              type: array
              items:
                $ref: '#/definitions/SmartDevice'
            pagination:
              $ref: '#/definitions/Pagination'
      401:
        description: Yetkisiz erişim
    definitions:
      SmartDevice:
        type: object
        properties:
          id:
            type: string
            format: uuid
          name:
            type: string
          external_id:
            type: string
          device_type:
            type: string
          brand:
            type: string
          model:
            type: string
          is_online:
            type: boolean
          is_sensor:
            type: boolean
          is_actuator:
            type: boolean
          last_seen:
            type: string
            format: date-time
          settings:
            type: object
          created_at:
            type: string
            format: date-time
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401

    page, page_size = get_pagination_params()
    integration_id = request.args.get('integration_id')
    is_online = request.args.get('is_online')

    query = SmartDevice.query.filter_by(
        organization_id=user.organization_id,
        is_active=True
    )
    
    if integration_id:
        query = query.filter_by(integration_id=integration_id)
    if is_online is not None:
        query = query.filter_by(is_online=is_online.lower() == 'true')

    total = query.count()
    devices = query.offset((page - 1) * page_size).limit(page_size).all()

    items = [d.to_dict() for d in devices]
    return jsonify(paginate_response(items, total, page, page_size))


@api_bp.route('/devices/<uuid:device_id>', methods=['GET'])
@requires_auth
def get_device_detail(device_id):
    """
    Tek bir cihazın detaylarını getir.
    ---
    tags:
      - Devices
    security:
      - bearerAuth: []
    parameters:
      - name: device_id
        in: path
        type: string
        format: uuid
        required: true
        description: Cihaz UUID
    responses:
      200:
        description: Cihaz detayları
        schema:
          $ref: '#/definitions/SmartDevice'
      401:
        description: Yetkisiz erişim
      404:
        description: Cihaz bulunamadı
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401

    device = SmartDevice.query.filter_by(
        id=device_id,
        organization_id=user.organization_id
    ).first()

    if not device:
        return jsonify({"error": "Device not found"}), 404

    return jsonify(device.to_dict())


@api_bp.route('/devices/<uuid:device_id>', methods=['PUT'])
@requires_auth
def update_device(device_id):
    """
    Cihaz bilgilerini güncelle.
    ---
    tags:
      - Devices
    security:
      - bearerAuth: []
    consumes:
      - application/json
    parameters:
      - name: device_id
        in: path
        type: string
        format: uuid
        required: true
        description: Cihaz UUID
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
              example: Salon Lambası
              description: Cihaz adı
            device_type:
              type: string
              enum: [relay, plug, dimmer, sensor, thermostat, meter, inverter, battery]
              example: relay
            is_sensor:
              type: boolean
              example: false
            is_actuator:
              type: boolean
              example: true
            settings:
              type: object
              example: {"auto_off": 3600, "led_enabled": true}
              description: Cihaz ayarları (JSONB)
    responses:
      200:
        description: Cihaz güncellendi
        schema:
          type: object
          properties:
            message:
              type: string
              example: Device updated
            device:
              $ref: '#/definitions/SmartDevice'
      401:
        description: Yetkisiz erişim
      404:
        description: Cihaz bulunamadı
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401

    device = SmartDevice.query.filter_by(
        id=device_id,
        organization_id=user.organization_id
    ).first()

    if not device:
        return jsonify({"error": "Device not found"}), 404

    data = request.get_json() or {}
    
    if "name" in data:
        device.name = data["name"]
    if "settings" in data:
        device.settings = data["settings"]
    
    db.session.commit()
    
    return jsonify({
        "message": "Device updated",
        "device": device.to_dict()
    })


@api_bp.route('/devices/<uuid:device_id>', methods=['DELETE'])
@requires_auth
def delete_device(device_id):
    """
    Cihazı sil (soft delete).
    ---
    tags:
      - Devices
    security:
      - bearerAuth: []
    parameters:
      - name: device_id
        in: path
        type: string
        format: uuid
        required: true
        description: Cihaz UUID
    responses:
      200:
        description: Cihaz silindi
        schema:
          type: object
          properties:
            message:
              type: string
              example: Device deleted
      401:
        description: Yetkisiz erişim
      404:
        description: Cihaz bulunamadı
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401

    device = SmartDevice.query.filter_by(
        id=device_id,
        organization_id=user.organization_id
    ).first()

    if not device:
        return jsonify({"error": "Device not found"}), 404

    device.is_active = False
    db.session.commit()
    
    return jsonify({"message": "Device deleted"})
