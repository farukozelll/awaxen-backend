"""
Organization Routes - SaaS Tenant Yönetimi.

Eski 'Sites' yapısının yerine geçti.
Her Organization bir ev, tarım işletmesi veya fabrika olabilir.
"""
from flask import Blueprint, request, jsonify
from flasgger import swag_from

from app.extensions import db
from app.models import Organization, User
from app.api.helpers import (
    get_current_user,
    get_pagination_params,
    paginate_response,
    apply_sorting,
)
from app.auth import requires_auth

organizations_bp = Blueprint("organizations", __name__)


@organizations_bp.route("/organizations", methods=["GET"])
@requires_auth
@swag_from({
    "tags": ["Organizations"],
    "summary": "Kullanıcının organizasyonlarını listele",
    "parameters": [
        {
            "name": "page",
            "in": "query",
            "type": "integer",
            "default": 1,
            "description": "Sayfa numarası"
        },
        {
            "name": "pageSize",
            "in": "query",
            "type": "integer",
            "default": 20,
            "description": "Sayfa başına kayıt (max 100)"
        },
        {
            "name": "search",
            "in": "query",
            "type": "string",
            "description": "İsme göre arama"
        },
        {
            "name": "sortBy",
            "in": "query",
            "type": "string",
            "enum": ["name", "created_at", "subscription_plan"],
            "default": "created_at",
            "description": "Sıralama alanı"
        },
        {
            "name": "sortOrder",
            "in": "query",
            "type": "string",
            "enum": ["asc", "desc"],
            "default": "desc",
            "description": "Sıralama yönü"
        },
        {
            "name": "is_active",
            "in": "query",
            "type": "boolean",
            "description": "Aktif durumuna göre filtrele"
        },
    ],
    "responses": {
        200: {
            "description": "Organizasyon listesi",
            "schema": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "items": {"$ref": "#/definitions/Organization"}
                    },
                    "pagination": {"$ref": "#/definitions/Pagination"}
                }
            }
        },
        401: {"description": "Yetkisiz erişim"}
    }
})
def list_organizations():
    """Kullanıcının erişebildiği organizasyonları listele."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    page, page_size = get_pagination_params()
    search = request.args.get("search", "", type=str).strip()
    sort_by = request.args.get("sortBy", "created_at")
    sort_order = request.args.get("sortOrder", "desc").lower()
    is_active = request.args.get("is_active")
    
    query = Organization.query
    
    if user.role != "superadmin":
        query = query.filter_by(id=user.organization_id)
    
    if is_active is not None:
        query = query.filter_by(is_active=is_active.lower() == "true")
    else:
        query = query.filter_by(is_active=True)
    
    if search:
        query = query.filter(Organization.name.ilike(f"%{search}%"))
    
    query = apply_sorting(query, Organization, sort_by, sort_order, ["name", "created_at", "subscription_plan"])
    
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return jsonify(paginate_response([org.to_dict() for org in items], total, page, page_size))


@organizations_bp.route("/organizations/<uuid:org_id>", methods=["GET"])
@swag_from({
    "tags": ["Organizations"],
    "summary": "Organizasyon detayı",
    "parameters": [
        {"name": "org_id", "in": "path", "type": "string", "required": True}
    ],
    "responses": {
        200: {"description": "Organizasyon bilgileri"},
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetki yok"},
        404: {"description": "Organizasyon bulunamadı"}
    }
})
def get_organization(org_id):
    """Tek bir organizasyonun detaylarını getir."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    org = Organization.query.get_or_404(org_id)
    
    # Yetki kontrolü
    if user.role != "superadmin" and user.organization_id != org.id:
        return jsonify({"error": "Forbidden"}), 403
    
    return jsonify(org.to_dict())


@organizations_bp.route("/organizations", methods=["POST"])
@swag_from({
    "tags": ["Organizations"],
    "summary": "Yeni organizasyon oluştur",
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "example": "Ahmet'in Evi"},
                    "type": {"type": "string", "example": "home"},
                    "timezone": {"type": "string", "example": "Europe/Istanbul"},
                    "location": {"type": "object"},
                    "settings": {"type": "object"}
                },
                "required": ["name"]
            }
        }
    ],
    "responses": {
        201: {"description": "Organizasyon oluşturuldu"},
        400: {"description": "Geçersiz veri"},
        401: {"description": "Yetkisiz erişim"}
    }
})
def create_organization():
    """Yeni organizasyon oluştur."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    
    if not data.get("name"):
        return jsonify({"error": "Name is required"}), 400
    
    # Slug oluştur
    from slugify import slugify
    base_slug = slugify(data["name"])
    slug = base_slug
    counter = 1
    while Organization.query.filter_by(slug=slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1
    
    org = Organization(
        name=data["name"],
        slug=slug,
        type=data.get("type", "home"),
        timezone=data.get("timezone", "Europe/Istanbul"),
        location=data.get("location", {}),
        settings=data.get("settings", {})
    )
    
    db.session.add(org)
    
    # Kullanıcıyı bu organizasyona bağla (ilk organizasyonuysa)
    if not user.organization_id:
        user.organization_id = org.id
    
    db.session.commit()
    
    return jsonify(org.to_dict()), 201


@organizations_bp.route("/organizations/<uuid:org_id>", methods=["PUT"])
@swag_from({
    "tags": ["Organizations"],
    "summary": "Organizasyonu güncelle",
    "parameters": [
        {"name": "org_id", "in": "path", "type": "string", "required": True},
        {
            "name": "body",
            "in": "body",
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                    "timezone": {"type": "string"},
                    "location": {"type": "object"},
                    "settings": {"type": "object"},
                    "subscription_plan": {"type": "string"}
                }
            }
        }
    ],
    "responses": {
        200: {"description": "Organizasyon güncellendi"},
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetki yok"},
        404: {"description": "Organizasyon bulunamadı"}
    }
})
def update_organization(org_id):
    """Organizasyon bilgilerini güncelle."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    org = Organization.query.get_or_404(org_id)
    
    # Yetki kontrolü
    if user.role not in ["superadmin", "admin"] or (user.role == "admin" and user.organization_id != org.id):
        return jsonify({"error": "Forbidden"}), 403
    
    data = request.get_json()
    
    if "name" in data:
        org.name = data["name"]
    if "type" in data:
        org.type = data["type"]
    if "timezone" in data:
        org.timezone = data["timezone"]
    if "location" in data:
        org.location = data["location"]
    if "settings" in data:
        org.settings = data["settings"]
    if "subscription_plan" in data and user.role == "superadmin":
        org.subscription_plan = data["subscription_plan"]
    
    db.session.commit()
    
    return jsonify(org.to_dict())


@organizations_bp.route("/organizations/<uuid:org_id>", methods=["DELETE"])
@swag_from({
    "tags": ["Organizations"],
    "summary": "Organizasyonu sil (soft delete)",
    "parameters": [
        {"name": "org_id", "in": "path", "type": "string", "required": True}
    ],
    "responses": {
        200: {"description": "Organizasyon deaktive edildi"},
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetki yok"},
        404: {"description": "Organizasyon bulunamadı"}
    }
})
def delete_organization(org_id):
    """Organizasyonu deaktive et (soft delete)."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    org = Organization.query.get_or_404(org_id)
    
    # Sadece superadmin silebilir
    if user.role != "superadmin":
        return jsonify({"error": "Forbidden"}), 403
    
    org.is_active = False
    db.session.commit()
    
    return jsonify({"message": "Organization deactivated"}), 200


@organizations_bp.route("/organizations/<uuid:org_id>/users", methods=["GET"])
@swag_from({
    "tags": ["Organizations"],
    "summary": "Organizasyondaki kullanıcıları listele",
    "parameters": [
        {
            "name": "org_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "Organizasyon UUID"
        },
        {
            "name": "page",
            "in": "query",
            "type": "integer",
            "default": 1,
            "description": "Sayfa numarası"
        },
        {
            "name": "pageSize",
            "in": "query",
            "type": "integer",
            "default": 20,
            "description": "Sayfa başına kayıt (max 100)"
        },
        {
            "name": "search",
            "in": "query",
            "type": "string",
            "description": "İsme veya e-postaya göre arama"
        },
    ],
    "responses": {
        200: {
            "description": "Kullanıcı listesi",
            "schema": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "items": {"$ref": "#/definitions/User"}
                    },
                    "pagination": {"$ref": "#/definitions/Pagination"}
                }
            }
        },
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetki yok"},
        404: {"description": "Organizasyon bulunamadı"}
    }
})
def list_organization_users(org_id):
    """Organizasyona ait kullanıcıları listele."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    org = Organization.query.get_or_404(org_id)
    
    # Yetki kontrolü
    if user.role != "superadmin" and user.organization_id != org.id:
        return jsonify({"error": "Forbidden"}), 403
    
    page, page_size = get_pagination_params()
    search = request.args.get("search", "", type=str).strip()

    query = User.query.filter_by(organization_id=org.id, is_active=True)
    if search:
        like = f"%{search}%"
        query = query.filter((User.full_name.ilike(like)) | (User.email.ilike(like)))

    total = query.count()
    users = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return jsonify(paginate_response([u.to_dict() for u in users], total, page, page_size))


@organizations_bp.route("/organizations/<uuid:org_id>/stats", methods=["GET"])
@swag_from({
    "tags": ["Organizations"],
    "summary": "Organizasyon istatistikleri",
    "parameters": [
        {
            "name": "org_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "Organizasyon UUID"
        }
    ],
    "responses": {
        200: {"description": "Özet istatistikler"},
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetki yok"},
        404: {"description": "Organizasyon bulunamadı"}
    }
})
def get_organization_stats(org_id):
    """Organizasyonun özet istatistiklerini getir."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    org = Organization.query.get_or_404(org_id)
    
    # Yetki kontrolü
    if user.role != "superadmin" and user.organization_id != org.id:
        return jsonify({"error": "Forbidden"}), 403
    
    from app.models import SmartDevice, SmartAsset, Integration, Automation
    
    stats = {
        "organization_id": str(org.id),
        "name": org.name,
        "user_count": User.query.filter_by(organization_id=org.id, is_active=True).count(),
        "device_count": SmartDevice.query.filter_by(organization_id=org.id, is_active=True).count(),
        "asset_count": SmartAsset.query.filter_by(organization_id=org.id, is_active=True).count(),
        "integration_count": Integration.query.filter_by(organization_id=org.id, is_active=True).count(),
        "automation_count": Automation.query.filter_by(organization_id=org.id, is_active=True).count(),
        "online_devices": SmartDevice.query.filter_by(organization_id=org.id, is_active=True, is_online=True).count(),
    }
    
    return jsonify(stats)
