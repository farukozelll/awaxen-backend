"""Kullanıcı kimlik doğrulama ve profil endpoint'leri - v6.0."""
from flask import jsonify, request, current_app

from . import api_bp
from .helpers import get_current_user
from app.extensions import db
from app.models import User, Organization, Wallet
from app.auth import requires_auth


@api_bp.route('/auth/me', methods=['GET'])
@requires_auth
def get_my_profile():
    """
    Token'daki kullanıcının profil bilgisini döner.
    ---
    tags:
      - Auth
    security:
      - bearerAuth: []
    responses:
      200:
        description: Kullanıcı profili ve organizasyon bilgisi
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 401

    response = {
        "id": str(user.id),
        "auth0_id": user.auth0_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "organization_id": str(user.organization_id) if user.organization_id else None,
    }
    
    # Organizasyon bilgisini de ekle
    if user.organization:
        response["organization"] = {
            "id": str(user.organization.id),
            "name": user.organization.name,
            "type": user.organization.type,
            "subscription_plan": user.organization.subscription_plan,
        }
    
    return jsonify(response)


@api_bp.route('/auth/sync', methods=['POST'])
def sync_user():
    """
    Auth0 kullanıcısını Postgres ile senkronize et (Upsert).
    
    İlk girişte kullanıcı ve varsayılan organizasyon oluşturulur.
    ---
    tags:
      - Auth
    consumes:
      - application/json
    parameters:
      - in: header
        name: X-Auth0-Id
        required: false
        type: string
      - in: body
        name: payload
        required: true
        schema:
          type: object
          properties:
            auth0_id:
              type: string
              example: google-oauth2|123
            email:
              type: string
              example: user@awaxen.com
            name:
              type: string
              example: Awaxen User
            role:
              type: string
              example: super_admin
    responses:
      200:
        description: Kullanıcı bilgileri senkronize edildi
    """
    try:
        payload = request.get_json(silent=True) or {}

        auth0_id = request.headers.get('X-Auth0-Id') or payload.get('auth0_id')
        email = request.headers.get('X-Auth0-Email') or payload.get('email')
        full_name = request.headers.get('X-Auth0-Name') or payload.get('name')
        frontend_role = payload.get('role')

        if not auth0_id or not email:
            return jsonify({"error": "auth0_id ve email zorunludur"}), 400

        user = User.query.filter_by(auth0_id=auth0_id).first()

        if user:
            current_app.logger.info(f"[AuthSync] Kullanıcı güncelleniyor: {email}")
            user.email = email
            user.full_name = full_name or user.full_name

            if frontend_role == 'super_admin' and user.role != 'admin':
                user.role = 'admin'

            db.session.commit()

            return jsonify({
                "status": "synced",
                "message": "Kullanıcı güncellendi",
                "user": {
                    "id": str(user.id),
                    "auth0_id": user.auth0_id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role,
                    "organization_id": str(user.organization_id) if user.organization_id else None,
                },
                "organization": {
                    "id": str(user.organization.id),
                    "name": user.organization.name,
                    "type": user.organization.type,
                    "subscription_plan": user.organization.subscription_plan,
                } if user.organization else None,
            }), 200

        current_app.logger.info(f"[AuthSync] Yeni kullanıcı oluşturuluyor: {email}")

        user_count = User.query.count()
        final_role = 'admin' if user_count == 0 else 'viewer'
        if frontend_role == 'super_admin':
            final_role = 'admin'

        org = Organization(
            name=f"{full_name or email}'s Home",
            type="home",
            subscription_plan="free",
            is_active=True,
        )
        db.session.add(org)
        db.session.flush()

        user = User(
            auth0_id=auth0_id,
            email=email,
            full_name=full_name or 'New User',
            role=final_role,
            organization_id=org.id,
        )
        db.session.add(user)
        db.session.flush()

        try:
            wallet = Wallet(user_id=user.id, balance=0.0)
            db.session.add(wallet)
        except Exception as wallet_err:
            current_app.logger.warning(f"[AuthSync] Wallet oluşturulamadı: {wallet_err}")

        db.session.commit()

        return jsonify({
            "status": "created",
            "message": "Kullanıcı ve organizasyon oluşturuldu",
            "user": {
                "id": str(user.id),
                "auth0_id": user.auth0_id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "organization_id": str(user.organization_id),
            },
            "organization": {
                "id": str(org.id),
                "name": org.name,
                "type": org.type,
                "subscription_plan": org.subscription_plan,
            },
        }), 201

    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f"[AuthSync] Hata: {exc}")
        return jsonify({"error": "Sunucu hatası", "details": str(exc)}), 500
