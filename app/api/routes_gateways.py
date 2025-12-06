"""Gateway (Hub) yönetimi endpoint'leri - v6.0."""
from flask import jsonify, request

from . import api_bp
from .helpers import get_current_user, get_pagination_params, get_filter_params, paginate_response, apply_sorting
from app.extensions import db
from app.models import Gateway
from app.auth import requires_auth


@api_bp.route('/gateways', methods=['GET'])
@requires_auth
def list_gateways():
    """
    Organizasyona ait gateway'leri listele.
    ---
    tags:
      - Gateways
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
        description: Sayfa başına kayıt sayısı (max 100)
      - name: search
        in: query
        type: string
        description: İsim veya seri numarasında arama
      - name: sortBy
        in: query
        type: string
        enum: [name, serial_number, created_at, is_online]
        default: created_at
        description: Sıralama alanı
      - name: sortOrder
        in: query
        type: string
        enum: [asc, desc]
        default: desc
        description: Sıralama yönü
      - name: is_online
        in: query
        type: boolean
        description: Online durumuna göre filtrele
    responses:
      200:
        description: Gateway listesi
        schema:
          type: object
          properties:
            data:
              type: array
              items:
                $ref: '#/definitions/Gateway'
            pagination:
              $ref: '#/definitions/Pagination'
      401:
        description: Yetkisiz erişim
    definitions:
      Gateway:
        type: object
        properties:
          id:
            type: string
            format: uuid
          name:
            type: string
          serial_number:
            type: string
          model:
            type: string
          firmware_version:
            type: string
          is_online:
            type: boolean
          last_seen:
            type: string
            format: date-time
          ip_address:
            type: string
          created_at:
            type: string
            format: date-time
      Pagination:
        type: object
        properties:
          page:
            type: integer
          pageSize:
            type: integer
          total:
            type: integer
          totalPages:
            type: integer
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401

    page, page_size = get_pagination_params()
    filters = get_filter_params()

    query = Gateway.query.filter_by(
        organization_id=user.organization_id,
        is_active=True
    )

    # Arama
    if filters["search"]:
        search_term = f"%{filters['search']}%"
        query = query.filter(
            db.or_(
                Gateway.name.ilike(search_term),
                Gateway.serial_number.ilike(search_term),
                Gateway.model.ilike(search_term),
            )
        )

    # Online filtresi
    is_online = request.args.get('is_online')
    if is_online is not None:
        query = query.filter(Gateway.is_online == (is_online.lower() == 'true'))

    # Sıralama
    allowed_sort = ["name", "serial_number", "created_at", "is_online", "last_seen"]
    query = apply_sorting(query, Gateway, filters["sort_by"], filters["sort_order"], allowed_sort)

    # Toplam sayı
    total = query.count()

    # Sayfalama
    gateways = query.offset((page - 1) * page_size).limit(page_size).all()

    return jsonify(paginate_response(
        [g.to_dict() for g in gateways],
        total, page, page_size
    ))


@api_bp.route('/gateways/<uuid:gateway_id>', methods=['GET'])
@requires_auth
def get_gateway(gateway_id):
    """
    Tek bir gateway detayını getir.
    ---
    tags:
      - Gateways
    security:
      - bearerAuth: []
    parameters:
      - name: gateway_id
        in: path
        type: string
        format: uuid
        required: true
        description: Gateway UUID
    responses:
      200:
        description: Gateway detayı
        schema:
          $ref: '#/definitions/Gateway'
      404:
        description: Gateway bulunamadı
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401

    gateway = Gateway.query.filter_by(
        id=gateway_id,
        organization_id=user.organization_id,
        is_active=True
    ).first()

    if not gateway:
        return jsonify({"error": "Gateway not found"}), 404

    return jsonify(gateway.to_dict())


@api_bp.route('/gateways', methods=['POST'])
@requires_auth
def create_gateway():
    """
    Yeni gateway ekle.
    ---
    tags:
      - Gateways
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
            - serial_number
          properties:
            name:
              type: string
              example: Ana Hub
              description: Gateway adı
            serial_number:
              type: string
              example: AWX-GW-001
              description: Benzersiz seri numarası
            model:
              type: string
              example: Awaxen Hub Pro
              description: Model adı
            firmware_version:
              type: string
              example: 1.2.3
              description: Firmware versiyonu
            ip_address:
              type: string
              example: 192.168.1.100
              description: IP adresi
            mac_address:
              type: string
              example: AA:BB:CC:DD:EE:FF
              description: MAC adresi
            settings:
              type: object
              example: {"mqtt_topic": "home/hub1"}
              description: Ek ayarlar (JSONB)
    responses:
      201:
        description: Gateway oluşturuldu
        schema:
          $ref: '#/definitions/Gateway'
      400:
        description: Geçersiz veri
      409:
        description: Seri numarası zaten mevcut
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}

    if not data.get("name"):
        return jsonify({"error": "name is required"}), 400
    if not data.get("serial_number"):
        return jsonify({"error": "serial_number is required"}), 400

    # Seri numarası kontrolü
    existing = Gateway.query.filter_by(serial_number=data["serial_number"]).first()
    if existing:
        return jsonify({"error": "Serial number already exists"}), 409

    settings = data.get("settings", {}).copy()
    settings["display_name"] = data["name"]
    if data.get("firmware_version"):
        settings["firmware_version"] = data["firmware_version"]

    gateway = Gateway(
        organization_id=user.organization_id,
        serial_number=data["serial_number"],
        model=data.get("model"),
        ip_address=data.get("ip_address"),
        mac_address=data.get("mac_address"),
        settings=settings,
    )
    db.session.add(gateway)
    db.session.commit()

    return jsonify(gateway.to_dict()), 201


@api_bp.route('/gateways/<uuid:gateway_id>', methods=['PUT'])
@requires_auth
def update_gateway(gateway_id):
    """
    Gateway bilgilerini güncelle.
    ---
    tags:
      - Gateways
    security:
      - bearerAuth: []
    consumes:
      - application/json
    parameters:
      - name: gateway_id
        in: path
        type: string
        format: uuid
        required: true
        description: Gateway UUID
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
              example: Ana Hub (Güncellendi)
            model:
              type: string
              example: Awaxen Hub Pro v2
            firmware_version:
              type: string
              example: 1.3.0
            ip_address:
              type: string
              example: 192.168.1.101
            mac_address:
              type: string
              example: AA:BB:CC:DD:EE:FF
            is_online:
              type: boolean
              example: true
            settings:
              type: object
              example: {"mqtt_topic": "home/hub1/updated"}
    responses:
      200:
        description: Gateway güncellendi
        schema:
          $ref: '#/definitions/Gateway'
      404:
        description: Gateway bulunamadı
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401

    gateway = Gateway.query.filter_by(
        id=gateway_id,
        organization_id=user.organization_id,
        is_active=True
    ).first()

    if not gateway:
        return jsonify({"error": "Gateway not found"}), 404

    data = request.get_json() or {}

    updatable = ["name", "model", "firmware_version", "ip_address", "mac_address", "is_online"]
    for field in updatable:
        if field in data:
            setattr(gateway, field, data[field])

    if "settings" in data:
        gateway.settings = data["settings"]

    db.session.commit()

    return jsonify(gateway.to_dict())


@api_bp.route('/gateways/<uuid:gateway_id>', methods=['DELETE'])
@requires_auth
def delete_gateway(gateway_id):
    """
    Gateway'i sil (soft delete).
    ---
    tags:
      - Gateways
    security:
      - bearerAuth: []
    parameters:
      - name: gateway_id
        in: path
        type: string
        format: uuid
        required: true
        description: Gateway UUID
    responses:
      200:
        description: Gateway silindi
        schema:
          type: object
          properties:
            message:
              type: string
              example: Gateway deleted successfully
      404:
        description: Gateway bulunamadı
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401

    gateway = Gateway.query.filter_by(
        id=gateway_id,
        organization_id=user.organization_id,
        is_active=True
    ).first()

    if not gateway:
        return jsonify({"error": "Gateway not found"}), 404

    gateway.is_active = False
    db.session.commit()

    return jsonify({"message": "Gateway deleted successfully"})


@api_bp.route('/gateways/<uuid:gateway_id>/devices', methods=['GET'])
@requires_auth
def get_gateway_devices(gateway_id):
    """
    Gateway'e bağlı cihazları listele.
    ---
    tags:
      - Gateways
    security:
      - bearerAuth: []
    parameters:
      - name: gateway_id
        in: path
        type: string
        format: uuid
        required: true
        description: Gateway UUID
      - name: page
        in: query
        type: integer
        default: 1
      - name: pageSize
        in: query
        type: integer
        default: 20
    responses:
      200:
        description: Gateway'e bağlı cihaz listesi
        schema:
          type: object
          properties:
            data:
              type: array
              items:
                $ref: '#/definitions/SmartDevice'
            pagination:
              $ref: '#/definitions/Pagination'
      404:
        description: Gateway bulunamadı
    """
    from app.models import SmartDevice

    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401

    gateway = Gateway.query.filter_by(
        id=gateway_id,
        organization_id=user.organization_id,
        is_active=True
    ).first()

    if not gateway:
        return jsonify({"error": "Gateway not found"}), 404

    page, page_size = get_pagination_params()

    query = SmartDevice.query.filter_by(
        gateway_id=gateway_id,
        is_active=True
    )

    total = query.count()
    devices = query.offset((page - 1) * page_size).limit(page_size).all()

    return jsonify(paginate_response(
        [d.to_dict() for d in devices],
        total, page, page_size
    ))
