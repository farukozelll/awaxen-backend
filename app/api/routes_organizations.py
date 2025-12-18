"""
Organization Routes - SaaS Tenant Yönetimi.

Eski 'Sites' yapısının yerine geçti.
Her Organization bir ev, tarım işletmesi veya fabrika olabilir.
"""
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify
from flasgger import swag_from

from app.extensions import db
from app.models import Organization, User, Role, UserInvite
from app.api.helpers import (
    get_current_user,
    get_pagination_params,
    paginate_response,
    apply_sorting,
)
from app.auth import requires_auth

organizations_bp = Blueprint("organizations", __name__)

ORGANIZATION_SWAGGER_DEFINITIONS = {
    "Organization": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "uuid"},
            "name": {"type": "string"},
            "slug": {"type": "string"},
            "type": {"type": "string", "example": "home"},
            "timezone": {"type": "string", "example": "Europe/Istanbul"},
            "location": {"type": "object"},
            "subscription_status": {"type": "string", "example": "active"},
            "subscription_plan": {"type": "string", "example": "pro"},
            "is_active": {"type": "boolean"},
            "created_at": {"type": "string", "format": "date-time"},
        },
    },
    "User": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "uuid"},
            "organization_id": {"type": "string", "format": "uuid"},
            "email": {"type": "string", "format": "email"},
            "full_name": {"type": "string"},
            "phone_number": {"type": "string"},
            "telegram_username": {"type": "string"},
            "role": {
                "type": "string",
                "enum": ["superadmin", "admin", "operator", "viewer"],
                "description": "Kullanıcının platform içindeki rolü",
            },
            "is_active": {"type": "boolean"},
            "created_at": {"type": "string", "format": "date-time"},
        },
    },
    "Pagination": {
        "type": "object",
        "properties": {
            "page": {"type": "integer", "example": 1},
            "pageSize": {"type": "integer", "example": 20},
            "total": {"type": "integer", "example": 125},
            "totalPages": {"type": "integer", "example": 7},
        },
    },
}


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
    },
    "definitions": ORGANIZATION_SWAGGER_DEFINITIONS,
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
    
    user_role_code = user.role.code if user.role else None
    if user_role_code != "super_admin":
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
@requires_auth
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
    user_role_code = user.role.code if user.role else None
    if user_role_code != "super_admin" and user.organization_id != org.id:
        return jsonify({"error": "Forbidden"}), 403
    
    return jsonify(org.to_dict())


@organizations_bp.route("/organizations", methods=["POST"])
@requires_auth
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
@requires_auth
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
    user_role_code = user.role.code if user.role else None
    if user_role_code not in ["super_admin", "admin"] or (user_role_code == "admin" and user.organization_id != org.id):
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
    if "subscription_plan" in data and user_role_code == "super_admin":
        org.subscription_plan = data["subscription_plan"]
    
    db.session.commit()
    
    return jsonify(org.to_dict())


@organizations_bp.route("/organizations/<uuid:org_id>", methods=["DELETE"])
@requires_auth
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
    
    # Sadece super_admin silebilir
    user_role_code = user.role.code if user.role else None
    if user_role_code != "super_admin":
        return jsonify({"error": "Forbidden"}), 403
    
    org.is_active = False
    db.session.commit()
    
    return jsonify({"message": "Organization deactivated"}), 200


@organizations_bp.route("/organizations/<uuid:org_id>/users", methods=["GET"])
@requires_auth
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
    },
    "definitions": ORGANIZATION_SWAGGER_DEFINITIONS,
})
def list_organization_users(org_id):
    """Organizasyona ait kullanıcıları listele."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    org = Organization.query.get_or_404(org_id)
    
    # Yetki kontrolü
    user_role_code = user.role.code if user.role else None
    if user_role_code != "super_admin" and user.organization_id != org.id:
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
@requires_auth
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
    user_role_code = user.role.code if user.role else None
    if user_role_code != "super_admin" and user.organization_id != org.id:
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


@organizations_bp.route("/organizations/<uuid:org_id>/invite", methods=["POST"])
@requires_auth
@swag_from({
    "tags": ["Organizations"],
    "summary": "Yeni kullanıcı daveti oluştur",
    "security": [{"bearerAuth": []}],
    "consumes": ["application/json"],
    "parameters": [
        {"name": "org_id", "in": "path", "type": "string", "required": True},
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "required": ["email"],
                "properties": {
                    "email": {"type": "string", "format": "email", "example": "new.user@awaxen.com"},
                    "role_code": {
                        "type": "string",
                        "enum": ["super_admin", "admin", "operator", "viewer", "farmer"],
                        "default": "viewer",
                    },
                    "expires_in_days": {"type": "integer", "example": 7, "default": 7},
                },
            },
        },
    ],
    "responses": {
        201: {"description": "Davet oluşturuldu"},
        400: {"description": "Geçersiz veri"},
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetki yok"},
    },
})
def invite_user(org_id):
    """Organizasyona yeni kullanıcı daveti oluştur."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    org = Organization.query.get_or_404(org_id)

    user_role_code = user.role.code if user.role else None
    if user_role_code not in ["super_admin"] and (
        user_role_code not in ["admin", "operator"] or user.organization_id != org.id
    ):
        return jsonify({"error": "Forbidden"}), 403

    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    role_code = data.get("role_code", "viewer")
    expires_in_days = int(data.get("expires_in_days", 7))

    if not email:
        return jsonify({"error": "Email is required"}), 400

    role = Role.get_by_code(role_code)
    if not role:
        return jsonify({"error": "Invalid role_code"}), 400

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=max(1, expires_in_days))

    invite = UserInvite.query.filter_by(email=email, organization_id=org.id, status="pending").first()
    if invite:
        invite.role_code = role_code
        invite.token = token
        invite.expires_at = expires_at
        invite.invited_by = user.id
    else:
        invite = UserInvite(
            organization_id=org.id,
            invited_by=user.id,
            email=email,
            role_code=role_code,
            token=token,
            expires_at=expires_at,
        )
        db.session.add(invite)

    db.session.commit()

    # TODO: Email gönderimi burada tetiklenebilir

    return jsonify({"message": "Invite created", "invite": invite.to_dict()}), 201


# ==========================================
# Location Yönetimi
# ==========================================

@organizations_bp.route("/organizations/<uuid:org_id>/location", methods=["GET", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Organizations"],
    "summary": "Organizasyon lokasyonunu getir",
    "description": "Hava durumu ve enerji hesaplamaları için kullanılan lokasyon bilgisi.",
    "parameters": [
        {"name": "org_id", "in": "path", "type": "string", "required": True}
    ],
    "responses": {
        200: {
            "description": "Lokasyon bilgisi",
            "schema": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number", "example": 41.0082},
                    "longitude": {"type": "number", "example": 28.9784},
                    "city": {"type": "string", "example": "Istanbul"},
                    "country": {"type": "string", "example": "TR"},
                    "timezone": {"type": "string", "example": "Europe/Istanbul"}
                }
            }
        },
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetki yok"},
        404: {"description": "Organizasyon bulunamadı"}
    }
})
def get_organization_location(org_id):
    """Organizasyon lokasyonunu getir."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    org = Organization.query.get_or_404(org_id)
    
    # Yetki kontrolü - kendi organizasyonu veya super_admin
    user_role_code = user.role.code if user.role else None
    if user_role_code != "super_admin" and user.organization_id != org.id:
        return jsonify({"error": "Forbidden"}), 403
    
    location = org.location or {}
    return jsonify({
        "latitude": location.get("latitude") or location.get("lat"),
        "longitude": location.get("longitude") or location.get("lon"),
        "city": location.get("city"),
        "country": location.get("country"),
        "timezone": org.timezone,
        "is_configured": bool(location.get("latitude") or location.get("lat"))
    })


@organizations_bp.route("/organizations/<uuid:org_id>/location", methods=["PUT", "PATCH", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Organizations"],
    "summary": "Organizasyon lokasyonunu güncelle",
    "description": "Hava durumu ve enerji hesaplamaları için lokasyon ayarla.",
    "parameters": [
        {"name": "org_id", "in": "path", "type": "string", "required": True},
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number", "example": 41.0082},
                    "longitude": {"type": "number", "example": 28.9784},
                    "city": {"type": "string", "example": "Istanbul"},
                    "country": {"type": "string", "example": "TR"}
                },
                "required": ["latitude", "longitude"]
            }
        }
    ],
    "responses": {
        200: {"description": "Lokasyon güncellendi"},
        400: {"description": "Geçersiz koordinatlar"},
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetki yok"},
        404: {"description": "Organizasyon bulunamadı"}
    }
})
def update_organization_location(org_id):
    """Organizasyon lokasyonunu güncelle."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    org = Organization.query.get_or_404(org_id)
    
    # Yetki kontrolü - admin veya super_admin
    user_role_code = user.role.code if user.role else None
    if user_role_code not in ["super_admin", "admin"]:
        return jsonify({"error": "Forbidden"}), 403
    if user_role_code == "admin" and user.organization_id != org.id:
        return jsonify({"error": "Forbidden"}), 403
    
    data = request.get_json()
    
    # Koordinat validasyonu
    lat = data.get("latitude") or data.get("lat")
    lon = data.get("longitude") or data.get("lon")
    
    if lat is None or lon is None:
        return jsonify({"error": "latitude and longitude are required"}), 400
    
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid coordinate format"}), 400
    
    if not (-90 <= lat <= 90):
        return jsonify({"error": "Latitude must be between -90 and 90"}), 400
    if not (-180 <= lon <= 180):
        return jsonify({"error": "Longitude must be between -180 and 180"}), 400
    
    # Lokasyonu güncelle
    org.location = {
        "latitude": lat,
        "longitude": lon,
        "city": data.get("city"),
        "country": data.get("country", "TR")
    }
    
    # Timezone da güncellenebilir
    if "timezone" in data:
        org.timezone = data["timezone"]
    
    db.session.commit()
    
    return jsonify({
        "message": "Location updated",
        "location": org.location,
        "timezone": org.timezone
    })
