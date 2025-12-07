"""
User management routes (super admin only).
"""
from flask import jsonify, request
from flasgger import swag_from
from sqlalchemy import or_

from . import api_bp
from .helpers import get_current_user, get_pagination_params, paginate_response
from app.auth import requires_auth
from app.models import Organization, Role, User


@api_bp.route("/users", methods=["GET"])
@requires_auth
@swag_from({
    "tags": ["Users"],
    "summary": "Tüm kullanıcıları listele (Super Admin)",
    "security": [{"bearerAuth": []}],
    "parameters": [
        {
            "name": "page",
            "in": "query",
            "type": "integer",
            "default": 1,
            "description": "Sayfa numarası",
        },
        {
            "name": "pageSize",
            "in": "query",
            "type": "integer",
            "default": 20,
            "description": "Sayfa başına kayıt (max 100)",
        },
        {
            "name": "search",
            "in": "query",
            "type": "string",
            "description": "İsim veya e-postaya göre arama",
        },
        {
            "name": "organization_id",
            "in": "query",
            "type": "string",
            "description": "Belirli bir organizasyona göre filtrele",
        },
        {
            "name": "role_code",
            "in": "query",
            "type": "string",
            "description": "Rol koduna göre filtrele (super_admin, admin, vb.)",
        },
        {
            "name": "include_inactive",
            "in": "query",
            "type": "boolean",
            "default": False,
            "description": "Pasif kullanıcıları dahil et",
        },
    ],
    "responses": {
        200: {
            "description": "Kullanıcı listesi",
            "schema": {
                "type": "object",
                "properties": {
                    "data": {"type": "array", "items": {"$ref": "#/definitions/User"}},
                    "pagination": {"$ref": "#/definitions/Pagination"},
                },
            },
        },
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetki yok"},
    },
})
def list_users():
    """Sistemdeki tüm kullanıcıları listele (super admin)."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Unauthorized"}), 401

    role_code = current_user.role.code if current_user.role else None
    if role_code != "super_admin":
        return jsonify({"error": "Forbidden"}), 403

    page, page_size = get_pagination_params()
    search = request.args.get("search", "", type=str).strip()
    org_id = request.args.get("organization_id")
    role_filter = request.args.get("role_code")
    include_inactive = request.args.get("include_inactive", "false").lower() == "true"

    query = User.query

    if not include_inactive:
        query = query.filter_by(is_active=True)

    if org_id:
        query = query.filter_by(organization_id=org_id)

    if role_filter:
        query = query.join(Role).filter(Role.code == role_filter)

    if search:
        like = f"%{search}%"
        query = query.filter(or_(User.full_name.ilike(like), User.email.ilike(like)))

    query = query.order_by(User.created_at.desc())

    total = query.count()
    users = query.offset((page - 1) * page_size).limit(page_size).all()

    data = []
    for user in users:
        user_dict = user.to_dict(include_permissions=True)
        if user.organization_id:
            org = Organization.query.get(user.organization_id)
            if org:
                user_dict["organization"] = {
                    "id": str(org.id),
                    "name": org.name,
                }
        data.append(user_dict)

    return jsonify(paginate_response(data, total, page, page_size))
