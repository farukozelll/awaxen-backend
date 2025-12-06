"""Kullanıcı kimlik doğrulama ve profil endpoint'leri - v6.0."""
from flask import jsonify, request

from . import api_bp
from .helpers import get_current_user
from app.extensions import db
from app.models import User, Organization
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
    responses:
      200:
        description: Kullanıcı bilgileri senkronize edildi
    """
    payload = request.get_json(force=True, silent=True) or {}

    auth0_id = request.headers.get('X-Auth0-Id') or payload.get('auth0_id')
    email = request.headers.get('X-Auth0-Email') or payload.get('email')
    full_name = request.headers.get('X-Auth0-Name') or payload.get('name')

    if not auth0_id:
        return jsonify({"error": "auth0_id is required"}), 400

    user = User.query.filter_by(auth0_id=auth0_id).first()
    created = False
    org_created = False

    if not user:
        # Yeni kullanıcı - varsayılan organizasyon oluştur
        org = Organization(
            name=f"{full_name or email}'s Home",
            type="home",
        )
        db.session.add(org)
        db.session.flush()  # org.id almak için
        
        user = User(
            auth0_id=auth0_id,
            email=email,
            full_name=full_name or 'New User',
            role='admin',  # İlk kullanıcı admin olur
            organization_id=org.id,
        )
        db.session.add(user)
        created = True
        org_created = True
    else:
        # Mevcut kullanıcı - bilgileri güncelle
        if email:
            user.email = email
        if full_name:
            user.full_name = full_name

    db.session.commit()

    response = {
        "message": "User synced successfully",
        "created": created,
        "organization_created": org_created,
        "user": {
            "id": str(user.id),
            "auth0_id": user.auth0_id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "organization_id": str(user.organization_id) if user.organization_id else None,
        },
    }
    
    if user.organization:
        response["organization"] = {
            "id": str(user.organization.id),
            "name": user.organization.name,
            "type": user.organization.type,
        }
    
    return jsonify(response), 200
