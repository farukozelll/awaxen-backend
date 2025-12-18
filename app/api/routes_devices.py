"""SmartDevice (Akıllı Cihaz) yönetimi endpoint'leri - v6.0."""
import logging
from datetime import datetime, timezone
from typing import List

from flask import jsonify, request
from sqlalchemy.orm import joinedload

from . import api_bp
from .helpers import get_current_user, get_pagination_params, get_filter_params, paginate_response, apply_sorting
from app.models import SmartDevice, SmartAsset
from app.extensions import db
from app.auth import requires_auth
from app.services.shelly_service import get_shelly_service
from app.exceptions import (
    error_response, success_response, not_found_response, 
    unauthorized_response, ValidationError, DatabaseError
)
from app.constants import HttpStatus

logger = logging.getLogger(__name__)


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

    # Eager loading ile N+1 query problemini önle
    query = SmartDevice.query.options(
        joinedload(SmartDevice.gateway),
        joinedload(SmartDevice.integration),
        joinedload(SmartDevice.asset)
    ).filter_by(
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


@api_bp.route('/devices/bulk-action', methods=['POST'])
@requires_auth
def bulk_device_action():
    """
    Birden fazla cihazı tek istekte kontrol et (örn: tüm cihazları kapat).
    ---
    tags:
      - Devices
    security:
      - bearerAuth: []
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - device_ids
            - action
          properties:
            device_ids:
              type: array
              items:
                type: string
                format: uuid
              example:
                - "550e8400-e29b-41d4-a716-446655440000"
                - "550e8400-e29b-41d4-a716-446655440111"
            action:
              type: string
              enum: [on, off, toggle]
              example: "off"
            value:
              type: integer
              description: Dimmer gibi cihazlar için (opsiyonel)
              minimum: 0
              maximum: 100
    responses:
      200:
        description: Bulk aksiyon sonucu
      400:
        description: Geçersiz istek
      401:
        description: Yetkisiz erişim
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}
    device_ids: List[str] = data.get("device_ids") or []
    action = data.get("action")
    value = data.get("value")

    if not device_ids or not isinstance(device_ids, list):
        return jsonify({"error": "device_ids array is required"}), 400
    if action not in ["on", "off", "toggle"]:
        return jsonify({"error": "Invalid action"}), 400

    devices = SmartDevice.query.filter(
        SmartDevice.id.in_(device_ids),
        SmartDevice.organization_id == user.organization_id,
        SmartDevice.is_active == True,
    ).all()

    if not devices:
        return jsonify({"error": "No devices found or access denied"}), 404

    results = []
    for device in devices:
        success = True
        message = "OK"

        if device.brand == "shelly":
            service = get_shelly_service(str(device.organization_id))
            if not service:
                success = False
                message = "Shelly integration not configured"
            else:
                try:
                    if action == "on":
                        success = service.turn_on(device)
                    elif action == "off":
                        success = service.turn_off(device)
                    elif action == "toggle":
                        success = service.toggle(device)

                    if success and value is not None and device.device_type in ["dimmer", "rgbw"]:
                        success = service.set_power_limit(device, int(value))
                except Exception as exc:
                    success = False
                    message = str(exc)
        else:
            # Placeholder - farklı markalar için ileride eklenecek
            success = True
            message = f"{device.brand or 'device'} control not implemented, skipping"

        if success:
            device.last_seen = datetime.utcnow()
        results.append({
            "device_id": str(device.id),
            "name": device.name,
            "success": success,
            "message": message,
        })

    db.session.commit()
    return jsonify({
        "requested": len(device_ids),
        "processed": len(results),
        "results": results,
    })


@api_bp.route('/devices/<uuid:device_id>/health', methods=['GET'])
@requires_auth
def get_device_health(device_id):
    """
    Cihaz sağlığını ve bağlantı durumunu döndür.
    ---
    tags:
      - Devices
    security:
      - bearerAuth: []
    parameters:
      - name: device_id
        in: path
        required: true
        type: string
    responses:
      200:
        description: Sağlık bilgisi
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
        organization_id=user.organization_id,
        is_active=True,
    ).first()

    if not device:
        return jsonify({"error": "Device not found"}), 404

    health = {
        "device_id": str(device.id),
        "name": device.name,
        "brand": device.brand,
        "model": device.model,
        "is_online": device.is_online,
        "last_seen": device.last_seen.isoformat() if device.last_seen else None,
        "gateway_status": None,
        "integration_status": None,
        "issues": [],
    }

    if device.gateway:
        health["gateway_status"] = {
            "id": str(device.gateway.id),
            "status": device.gateway.status,
            "last_seen": device.gateway.last_seen.isoformat() if device.gateway.last_seen else None,
        }

    if device.integration:
        health["integration_status"] = {
            "id": str(device.integration.id),
            "provider": device.integration.provider,
            "status": device.integration.status,
            "last_sync_at": device.integration.last_sync_at.isoformat() if device.integration.last_sync_at else None,
        }

    if not device.is_online:
        health["issues"].append("Device is offline")
    if device.gateway and device.gateway.status != "online":
        health["issues"].append("Gateway offline")
    if device.integration and device.integration.status != "active":
        health["issues"].append("Integration not active")

    return jsonify(health)
