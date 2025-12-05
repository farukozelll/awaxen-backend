"""Asset (Envanter/Sensör) yönetimi endpoint'leri."""
from flask import jsonify, request

from . import api_bp
from .helpers import (
    get_or_create_user,
    get_pagination_params,
    get_filter_params,
    paginate_response,
    apply_sorting,
)
from .. import db
from ..models import Asset, Device, Node, Site
from ..auth import requires_auth
from ..services import (
    create_asset_logic,
    update_asset_logic,
    delete_asset_logic,
    get_assets_by_node,
    get_assets_by_site,
)


@api_bp.route('/assets', methods=['GET'])
@requires_auth
def get_all_assets():
    """
    Kullanıcının tüm asset'lerini getir (pagination + filtreleme).
    ---
    tags:
      - Asset
    security:
      - bearerAuth: []
    parameters:
      - in: query
        name: page
        schema:
          type: integer
          default: 1
      - in: query
        name: pageSize
        schema:
          type: integer
          default: 20
      - in: query
        name: search
        schema:
          type: string
        description: İsim veya variable_name içinde arama
      - in: query
        name: asset_type
        schema:
          type: string
        description: Asset tipine göre filtrele (SENSOR, ACTUATOR, vb.)
      - in: query
        name: category
        schema:
          type: string
        description: Kategoriye göre filtrele (TEMPERATURE, HUMIDITY, vb.)
    responses:
      200:
        description: Asset listesi (paginated)
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    page, page_size = get_pagination_params()
    filters = get_filter_params()

    user_site_ids = [s.id for s in user.sites]

    query = (
        Asset.query
        .join(Node)
        .join(Device)
        .filter(Device.site_id.in_(user_site_ids))
    )

    if filters["search"]:
        search_term = f"%{filters['search']}%"
        query = query.filter(
            db.or_(
                Asset.name.ilike(search_term),
                Asset.variable_name.ilike(search_term),
            )
        )

    asset_type = request.args.get("asset_type")
    if asset_type:
        query = query.filter(Asset.asset_type == asset_type)

    category = request.args.get("category")
    if category:
        query = query.filter(Asset.category == category)

    allowed_sort = ["id", "name", "asset_type", "category", "created_at"]
    query = apply_sorting(query, Asset, filters["sort_by"], filters["sort_order"], allowed_sort)

    total = query.count()
    assets_page = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for asset in assets_page:
        asset_dict = asset.to_dict()
        asset_dict["node_name"] = asset.node.name
        asset_dict["device_name"] = asset.node.device.name
        asset_dict["device_serial"] = asset.node.device.serial_number
        asset_dict["site_name"] = asset.node.device.site.name
        items.append(asset_dict)

    return jsonify(paginate_response(items, total, page, page_size))


@api_bp.route('/assets', methods=['POST'])
@requires_auth
def create_asset():
    """
    Bir Node'a yeni asset (sensör/vana) tanımla.
    ---
    tags:
      - Asset
    consumes:
      - application/json
    parameters:
      - in: body
        name: asset
        schema:
          type: object
          required:
            - node_id
            - name
            - variable_name
          properties:
            node_id:
              type: integer
              example: 1
            name:
              type: string
              example: Domates Nem Sensörü
            description:
              type: string
              example: Sıra 1'deki toprak nem sensörü
            asset_type:
              type: string
              enum: [SENSOR, ACTUATOR, METER, CONTROLLER]
              example: SENSOR
            category:
              type: string
              example: SOIL_MOISTURE
            variable_name:
              type: string
              example: soil_moisture_1
            port_number:
              type: integer
              example: 1
            unit:
              type: string
              example: "%"
            min_value:
              type: number
              example: 0
            max_value:
              type: number
              example: 100
            calibration_offset:
              type: number
              example: 0
            position:
              type: object
              example: {"row": 1, "column": 3}
            configuration:
              type: object
              example: {"alarm_low": 20, "alarm_high": 80}
    responses:
      201:
        description: Asset oluşturuldu
      400:
        description: Validasyon hatası
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        asset = create_asset_logic(user.id, request.json)
        return jsonify({
            "message": "Asset oluşturuldu",
            "asset_id": asset.id,
            "asset": asset.to_dict()
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route('/assets/<int:asset_id>', methods=['GET'])
@requires_auth
def get_asset_detail(asset_id):
    """
    Tek bir asset'in detaylarını getir.
    ---
    tags:
      - Asset
    parameters:
      - in: path
        name: asset_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Asset detayları
      404:
        description: Asset bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    asset = (
        Asset.query
        .join(Node)
        .join(Device)
        .join(Site)
        .filter(Asset.id == asset_id, Site.user_id == user.id)
        .first()
    )

    if not asset:
        return jsonify({"error": "Asset bulunamadı"}), 404

    asset_dict = asset.to_dict()
    asset_dict["node_name"] = asset.node.name
    asset_dict["device_name"] = asset.node.device.name
    asset_dict["device_serial"] = asset.node.device.serial_number
    asset_dict["site_name"] = asset.node.device.site.name
    asset_dict["site_id"] = asset.node.device.site.id

    return jsonify(asset_dict)


@api_bp.route('/assets/<int:asset_id>', methods=['PUT'])
@requires_auth
def update_asset(asset_id):
    """
    Asset bilgilerini güncelle.
    ---
    tags:
      - Asset
    parameters:
      - in: path
        name: asset_id
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
            description:
              type: string
            asset_type:
              type: string
            category:
              type: string
            variable_name:
              type: string
            unit:
              type: string
            min_value:
              type: number
            max_value:
              type: number
            calibration_offset:
              type: number
            position:
              type: object
            configuration:
              type: object
            is_active:
              type: boolean
    responses:
      200:
        description: Asset güncellendi
      404:
        description: Asset bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        asset = update_asset_logic(user.id, asset_id, request.json)
        return jsonify({
            "message": "Asset güncellendi",
            "asset": asset.to_dict()
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@api_bp.route('/assets/<int:asset_id>', methods=['DELETE'])
@requires_auth
def delete_asset(asset_id):
    """
    Asset'i sil.
    ---
    tags:
      - Asset
    parameters:
      - in: path
        name: asset_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Asset silindi
      404:
        description: Asset bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        delete_asset_logic(user.id, asset_id)
        return jsonify({"message": "Asset silindi"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@api_bp.route('/nodes/<int:node_id>/assets', methods=['GET'])
@requires_auth
def get_node_assets(node_id):
    """
    Bir Node'a ait tüm asset'leri listele.
    ---
    tags:
      - Asset
    parameters:
      - in: path
        name: node_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Node'a ait asset listesi
      404:
        description: Node bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        assets = get_assets_by_node(user.id, node_id)
        return jsonify([asset.to_dict() for asset in assets])
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@api_bp.route('/sites/<int:site_id>/assets', methods=['GET'])
@requires_auth
def get_site_assets(site_id):
    """
    Bir Site'a ait tüm asset'leri listele (hiyerarşik bilgiyle).
    ---
    tags:
      - Asset
    parameters:
      - in: path
        name: site_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Site'a ait asset listesi
      404:
        description: Site bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        assets = get_assets_by_site(user.id, site_id)
        return jsonify(assets)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
