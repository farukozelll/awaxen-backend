"""
Organization Routes - SaaS Tenant Yönetimi.

Eski 'Sites' yapısının yerine geçti.
Her Organization bir ev, tarım işletmesi veya fabrika olabilir.
"""
from flask import Blueprint, request, jsonify
from flasgger import swag_from

from app.extensions import db
from app.models import Organization, User
from app.api.helpers import get_current_user

organizations_bp = Blueprint("organizations", __name__)


@organizations_bp.route("/organizations", methods=["GET"])
@swag_from({
    "tags": ["Organizations"],
    "summary": "Kullanıcının organizasyonlarını listele",
    "responses": {
        200: {"description": "Organizasyon listesi"}
    }
})
def list_organizations():
    """Kullanıcının erişebildiği organizasyonları listele."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    # Admin tüm organizasyonları görebilir, diğerleri sadece kendininkileri
    if user.role == "superadmin":
        organizations = Organization.query.filter_by(is_active=True).all()
    else:
        organizations = Organization.query.filter_by(
            id=user.organization_id,
            is_active=True
        ).all()
    
    return jsonify([org.to_dict() for org in organizations])


@organizations_bp.route("/organizations/<uuid:org_id>", methods=["GET"])
@swag_from({
    "tags": ["Organizations"],
    "summary": "Organizasyon detayı",
    "parameters": [
        {"name": "org_id", "in": "path", "type": "string", "required": True}
    ]
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
                    "location": {"type": "object"}
                },
                "required": ["name"]
            }
        }
    ]
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
    "summary": "Organizasyonu güncelle"
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
    "summary": "Organizasyonu sil (soft delete)"
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
    "summary": "Organizasyondaki kullanıcıları listele"
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
    
    users = User.query.filter_by(organization_id=org.id, is_active=True).all()
    
    return jsonify([u.to_dict() for u in users])


@organizations_bp.route("/organizations/<uuid:org_id>/stats", methods=["GET"])
@swag_from({
    "tags": ["Organizations"],
    "summary": "Organizasyon istatistikleri"
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
