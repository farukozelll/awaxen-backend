"""SmartAsset (Varlık) yönetimi endpoint'leri - v6.0."""
import logging
from typing import Tuple

from flask import jsonify, request, Response
from sqlalchemy.orm import joinedload

from . import api_bp
from .helpers import get_current_user, get_pagination_params, get_filter_params, paginate_response, apply_sorting
from app.models import SmartAsset, SmartDevice
from app.extensions import db
from app.auth import requires_auth
from app.exceptions import error_response, success_response, not_found_response
from app.constants import HttpStatus

logger = logging.getLogger(__name__)


@api_bp.route('/assets', methods=['GET'])
@requires_auth
def get_all_assets():
    """
    Organizasyonun tüm varlıklarını listele.
    ---
    tags:
      - Assets
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
        description: İsimde arama
      - name: sortBy
        in: query
        type: string
        enum: [name, type, priority, nominal_power_watt, created_at]
        default: created_at
        description: Sıralama alanı
      - name: sortOrder
        in: query
        type: string
        enum: [asc, desc]
        default: desc
        description: Sıralama yönü
      - name: type
        in: query
        type: string
        enum: [hvac, ev_charger, heater, water_heater, pool_pump, lighting, appliance, other]
        description: Varlık tipine göre filtrele
      - name: device_id
        in: query
        type: string
        format: uuid
        description: Bağlı cihaza göre filtrele
    responses:
      200:
        description: Varlık listesi
        schema:
          type: object
          properties:
            data:
              type: array
              items:
                $ref: '#/definitions/SmartAsset'
            pagination:
              $ref: '#/definitions/Pagination'
      401:
        description: Yetkisiz erişim
    definitions:
      SmartAsset:
        type: object
        properties:
          id:
            type: string
            format: uuid
          name:
            type: string
          type:
            type: string
          device_id:
            type: string
            format: uuid
          nominal_power_watt:
            type: integer
          priority:
            type: integer
          settings:
            type: object
          is_active:
            type: boolean
          created_at:
            type: string
            format: date-time
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401

    page, page_size = get_pagination_params()
    asset_type = request.args.get('type')

    # Eager loading ile N+1 query önleme
    query = SmartAsset.query.options(
        joinedload(SmartAsset.device)
    ).filter_by(
        organization_id=user.organization_id,
        is_active=True
    )
    
    if asset_type:
        query = query.filter_by(type=asset_type)

    total = query.count()
    assets = query.offset((page - 1) * page_size).limit(page_size).all()

    items = [a.to_dict() for a in assets]
    return jsonify(paginate_response(items, total, page, page_size))


@api_bp.route('/assets', methods=['POST'])
@requires_auth
def create_asset():
    """
    Yeni varlık oluştur.
    ---
    tags:
      - Assets
    security:
      - bearerAuth: []
    consumes:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - name
            - type
          properties:
            name:
              type: string
              example: Salon Kliması
              description: Varlık adı
            type:
              type: string
              enum: [hvac, ev_charger, heater, water_heater, pool_pump, lighting, appliance, other]
              example: hvac
              description: Varlık tipi
            device_id:
              type: string
              format: uuid
              example: 550e8400-e29b-41d4-a716-446655440000
              description: Bağlı cihaz UUID (opsiyonel)
            nominal_power_watt:
              type: integer
              example: 2500
              description: Nominal güç (Watt)
            priority:
              type: integer
              example: 1
              minimum: 1
              maximum: 10
              description: Öncelik (1=en yüksek)
            settings:
              type: object
              example: {"min_temp": 18, "max_temp": 26}
              description: Ek ayarlar (JSONB)
    responses:
      201:
        description: Varlık oluşturuldu
        schema:
          type: object
          properties:
            message:
              type: string
              example: Asset created
            asset:
              $ref: '#/definitions/SmartAsset'
      400:
        description: Validasyon hatası
      401:
        description: Yetkisiz erişim
      404:
        description: Bağlı cihaz bulunamadı
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    
    if not data.get("name"):
        return jsonify({"error": "Name is required"}), 400
    if not data.get("type"):
        return jsonify({"error": "Type is required"}), 400

    # Device kontrolü
    device_id = data.get("device_id")
    if device_id:
        device = SmartDevice.query.filter_by(
            id=device_id,
            organization_id=user.organization_id
        ).first()
        if not device:
            return jsonify({"error": "Device not found"}), 404

    asset = SmartAsset(
        organization_id=user.organization_id,
        device_id=device_id,
        name=data["name"],
        type=data["type"],
        nominal_power_watt=data.get("nominal_power_watt", 0),
        priority=data.get("priority", 1),
        settings=data.get("settings", {})
    )
    
    db.session.add(asset)
    db.session.commit()
    
    return jsonify({
        "message": "Asset created",
        "asset": asset.to_dict()
    }), 201


@api_bp.route('/assets/<uuid:asset_id>', methods=['GET'])
@requires_auth
def get_asset_detail(asset_id):
    """
    Tek bir varlığın detaylarını getir.
    ---
    tags:
      - Assets
    parameters:
      - in: path
        name: asset_id
        required: true
        schema:
          type: string
          format: uuid
    responses:
      200:
        description: Varlık detayları
      404:
        description: Varlık bulunamadı
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401

    asset = SmartAsset.query.filter_by(
        id=asset_id,
        organization_id=user.organization_id
    ).first()

    if not asset:
        return jsonify({"error": "Asset not found"}), 404

    return jsonify(asset.to_dict())


@api_bp.route('/assets/<uuid:asset_id>', methods=['PUT'])
@requires_auth
def update_asset(asset_id):
    """
    Varlık bilgilerini güncelle.
    ---
    tags:
      - Assets
    parameters:
      - in: path
        name: asset_id
        required: true
        schema:
          type: string
          format: uuid
    responses:
      200:
        description: Varlık güncellendi
      404:
        description: Varlık bulunamadı
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401

    asset = SmartAsset.query.filter_by(
        id=asset_id,
        organization_id=user.organization_id
    ).first()

    if not asset:
        return jsonify({"error": "Asset not found"}), 404

    data = request.get_json() or {}
    
    if "name" in data:
        asset.name = data["name"]
    if "type" in data:
        asset.type = data["type"]
    if "nominal_power_watt" in data:
        asset.nominal_power_watt = data["nominal_power_watt"]
    if "priority" in data:
        asset.priority = data["priority"]
    if "settings" in data:
        asset.settings = data["settings"]
    if "device_id" in data:
        asset.device_id = data["device_id"]
    
    db.session.commit()
    
    return jsonify({
        "message": "Asset updated",
        "asset": asset.to_dict()
    })


@api_bp.route('/assets/<uuid:asset_id>', methods=['DELETE'])
@requires_auth
def delete_asset(asset_id):
    """
    Varlığı sil (soft delete).
    ---
    tags:
      - Assets
    parameters:
      - in: path
        name: asset_id
        required: true
        schema:
          type: string
          format: uuid
    responses:
      200:
        description: Varlık silindi
      404:
        description: Varlık bulunamadı
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401

    asset = SmartAsset.query.filter_by(
        id=asset_id,
        organization_id=user.organization_id
    ).first()

    if not asset:
        return jsonify({"error": "Asset not found"}), 404

    asset.is_active = False
    db.session.commit()
    
    return jsonify({"message": "Asset deleted"})
