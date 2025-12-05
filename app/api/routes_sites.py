"""Site (Saha) yönetimi endpoint'leri."""
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
from ..models import Site
from ..auth import requires_auth
from ..services import create_site_logic, update_site_logic, get_site_hierarchy


@api_bp.route('/sites', methods=['GET'])
@requires_auth
def get_my_sites():
    """
    Oturumdaki kullanıcının sahalarını listele (pagination + filtreleme).
    ---
    tags:
      - Saha
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
        description: İsim veya şehir içinde arama
      - in: query
        name: sortBy
        schema:
          type: string
          enum: [id, name, city, created_at]
          default: id
      - in: query
        name: sortOrder
        schema:
          type: string
          enum: [asc, desc]
          default: asc
    responses:
      200:
        description: Kullanıcının sahaları (paginated)
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    page, page_size = get_pagination_params()
    filters = get_filter_params()

    query = Site.query.filter_by(user_id=user.id)

    if filters["search"]:
        search_term = f"%{filters['search']}%"
        query = query.filter(
            db.or_(
                Site.name.ilike(search_term),
                Site.city.ilike(search_term),
            )
        )

    allowed_sort = ["id", "name", "city", "created_at"]
    query = apply_sorting(query, Site, filters["sort_by"], filters["sort_order"], allowed_sort)

    total = query.count()
    sites_page = query.offset((page - 1) * page_size).limit(page_size).all()

    items = [{
        "id": s.id,
        "name": s.name,
        "city": s.city,
        "location": s.location,
        "latitude": s.latitude,
        "longitude": s.longitude,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "device_count": len(s.devices),
    } for s in sites_page]

    return jsonify(paginate_response(items, total, page, page_size))


@api_bp.route('/sites', methods=['POST'])
@requires_auth
def create_site():
    """
    Yeni saha oluştur (tipli ve boyutlu).
    ---
    tags:
      - Saha
    consumes:
      - application/json
    parameters:
      - in: body
        name: site
        schema:
          type: object
          properties:
            name:
              type: string
              example: Bafra Serası
            site_type:
              type: string
              enum: [GREENHOUSE, FIELD, SOLAR_PLANT, FACTORY, WAREHOUSE, OTHER]
              example: GREENHOUSE
            dimensions:
              type: object
              example: {"rows": 10, "columns": 5, "width_m": 100}
            city:
              type: string
              example: Samsun
            district:
              type: string
              example: Bafra
            location:
              type: string
              example: 41.12, 36.11
            latitude:
              type: number
              example: 41.12
            longitude:
              type: number
              example: 36.11
    responses:
      201:
        description: Saha başarıyla oluşturuldu
      400:
        description: Validasyon hatası
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        site = create_site_logic(user.id, request.json)
        return jsonify({
            "message": "Saha oluşturuldu",
            "site_id": site.id,
            "site": site.to_dict()
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route('/sites/<int:site_id>', methods=['GET'])
@requires_auth
def get_site_detail(site_id):
    """
    Tek bir sahayı detaylarıyla getir.
    ---
    tags:
      - Saha
    parameters:
      - in: path
        name: site_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Saha detayları
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    site = Site.query.filter_by(id=site_id, user_id=user.id).first()
    if not site:
        return jsonify({"error": "Saha bulunamadı"}), 404

    site_payload = {
        "id": site.id,
        "name": site.name,
        "city": site.city,
        "location": site.location,
        "latitude": site.latitude,
        "longitude": site.longitude,
        "created_at": site.created_at.isoformat() if site.created_at else None,
        "device_count": len(site.devices),
        "devices": [
            {
                "id": d.id,
                "name": d.name,
                "serial_number": d.serial_number,
                "model": d.model,
                "firmware_version": d.firmware_version,
                "is_online": d.is_online,
                "last_seen": d.last_seen.isoformat() if d.last_seen else None,
                "node_count": len(d.nodes),
            }
            for d in site.devices
        ],
    }

    return jsonify(site_payload)


@api_bp.route('/sites/<int:site_id>', methods=['PUT'])
@requires_auth
def update_site(site_id):
    """
    Bir sahayı güncelle.
    ---
    tags:
      - Saha
    parameters:
      - in: path
        name: site_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Saha güncellendi
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        updated_site = update_site_logic(user.id, site_id, request.json or {})
        return jsonify({
            "message": "Saha güncellendi",
            "site": updated_site.to_dict()
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@api_bp.route('/sites/<int:site_id>/hierarchy', methods=['GET'])
@requires_auth
def get_site_full_hierarchy(site_id):
    """
    Site'ın tam hiyerarşisini getir (Device -> Node -> Asset).
    ---
    tags:
      - Saha
    parameters:
      - in: path
        name: site_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Site hiyerarşisi
      404:
        description: Site bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        hierarchy = get_site_hierarchy(user.id, site_id)
        return jsonify(hierarchy)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
